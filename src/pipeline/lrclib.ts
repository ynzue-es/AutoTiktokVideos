/**
 * Client LRCLIB — API publique, gratuite, sans cle.
 *
 * Attention au classement de /api/search : il est purement textuel et remonte
 * volontiers des remixes de dix minutes avant la version originale. On ne s'y
 * fie donc jamais aveuglement, on rescore nous-memes (voir `scoreCandidate`),
 * et le config expose `track.lrclibId` pour epingler un resultat a la main
 * quand l'heuristique se trompe.
 */

const BASE = "https://lrclib.net/api";
const USER_AGENT = "AutoTiktokVideos/0.1 (https://github.com/local/auto-tiktok-videos)";

export type LrclibTrack = {
  id: number;
  trackName: string;
  artistName: string;
  albumName: string | null;
  duration: number | null;
  instrumental: boolean;
  plainLyrics: string | null;
  syncedLyrics: string | null;
};

const request = async (pathAndQuery: string): Promise<unknown | null> => {
  const res = await fetch(`${BASE}${pathAndQuery}`, {
    headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`LRCLIB ${pathAndQuery} -> HTTP ${res.status}`);
  }
  return res.json();
};

const normalize = (value: string): string =>
  value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

/** Variantes qu'on ne veut presque jamais quand on demande le morceau nu. */
const UNWANTED = [
  "remix",
  "live",
  "instrumental",
  "karaoke",
  "sped up",
  "slowed",
  "cover",
  "acoustic",
  "reverb",
  "edit",
  "version",
  "mix",
];

/**
 * Plus le score est haut, meilleur le candidat. On recompense la proximite
 * du titre demande et on penalise lourdement les variantes non demandees.
 */
const scoreCandidate = (
  candidate: LrclibTrack,
  wantedTitle: string,
  wantedArtist: string,
): number => {
  let score = 0;

  const title = normalize(candidate.trackName);
  const artist = normalize(candidate.artistName);
  const target = normalize(wantedTitle);
  const targetArtist = normalize(wantedArtist);

  if (title === target) score += 100;
  else if (title.startsWith(target)) score += 60;
  else if (title.includes(target)) score += 30;

  if (artist === targetArtist) score += 40;
  else if (artist.includes(targetArtist) || targetArtist.includes(artist)) score += 20;

  // Une variante n'est acceptable que si elle a ete demandee explicitement.
  for (const term of UNWANTED) {
    if (title.includes(term) && !target.includes(term)) score -= 50;
  }

  // Sans paroles synchronisees le candidat ne nous sert a rien.
  if (!candidate.syncedLyrics) score -= 500;
  if (candidate.instrumental) score -= 500;

  // A egalite, le titre le plus court est le plus proche de l'original.
  score -= Math.max(0, title.length - target.length) * 0.5;

  return score;
};

export const getById = async (id: number): Promise<LrclibTrack | null> =>
  (await request(`/get/${id}`)) as LrclibTrack | null;

/** Correspondance exacte. C'est le chemin rapide et le plus fiable. */
export const getExact = async (
  title: string,
  artist: string,
  album?: string,
): Promise<LrclibTrack | null> => {
  const params = new URLSearchParams({ track_name: title, artist_name: artist });
  if (album) params.set("album_name", album);
  return (await request(`/get?${params}`)) as LrclibTrack | null;
};

export const search = async (title: string, artist: string): Promise<LrclibTrack[]> => {
  const params = new URLSearchParams({ track_name: title, artist_name: artist });
  const results = (await request(`/search?${params}`)) as LrclibTrack[] | null;
  return results ?? [];
};

export type Resolution = {
  track: LrclibTrack;
  via: "id" | "exact" | "search";
  /** Les autres candidats plausibles, pour aider a corriger via lrclibId. */
  alternatives: { id: number; trackName: string; artistName: string; duration: number | null }[];
};

/**
 * Trouve la meilleure entree LRCLIB pour un morceau, ou null.
 * Ne renvoie que des entrees possedant des paroles synchronisees.
 */
export const resolve = async (
  title: string,
  artist: string,
  album: string | undefined,
  pinnedId: number | null,
): Promise<Resolution | null> => {
  if (pinnedId !== null) {
    const track = await getById(pinnedId);
    if (!track) throw new Error(`lrclibId ${pinnedId} introuvable sur LRCLIB`);
    if (!track.syncedLyrics) {
      throw new Error(`lrclibId ${pinnedId} n'a pas de paroles synchronisees`);
    }
    return { track, via: "id", alternatives: [] };
  }

  const exact = await getExact(title, artist, album);
  if (exact?.syncedLyrics) {
    return { track: exact, via: "exact", alternatives: [] };
  }

  const candidates = await search(title, artist);
  const withSynced = candidates.filter((c) => c.syncedLyrics && !c.instrumental);
  if (withSynced.length === 0) return null;

  const ranked = withSynced
    .map((c) => ({ c, score: scoreCandidate(c, title, artist) }))
    .sort((a, b) => b.score - a.score);

  return {
    track: ranked[0].c,
    via: "search",
    alternatives: ranked.slice(1, 5).map(({ c }) => ({
      id: c.id,
      trackName: c.trackName,
      artistName: c.artistName,
      duration: c.duration,
    })),
  };
};
