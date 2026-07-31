/**
 * Etape 3 — Paroles synchronisees mot par mot.
 *
 * On ne transcrit jamais : le texte affiche vient toujours de vraies paroles
 * (LRCLIB, ou `syncedlyrics` en secours). LRCLIB donne un timing par ligne,
 * cale sur l'enregistrement STUDIO — ce qui est exactement l'audio qu'on
 * utilise, donc ces timings sont directement exploitables. On descend ensuite
 * au mot par repartition syllabique (voir lrc.ts).
 */
import { existsSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import type { Config } from "./config.ts";
import {
  clipToWindow,
  distributeWords,
  paginate,
  parseLrc,
  type Line,
} from "./lrc.ts";
import { resolve as resolveLrclib, type Resolution } from "./lrclib.ts";
import {
  configPathFromArgv,
  ensureDir,
  hasFlag,
  info,
  loadConfig,
  ok,
  parseTime,
  paths,
  ROOT,
  step,
  warn,
} from "./util.ts";

/** Format @remotion/captions, conserve pour rester compatible avec le template. */
export type Caption = {
  text: string;
  startMs: number;
  endMs: number;
  timestampMs: number | null;
  confidence: number | null;
};

export type LyricsOutput = {
  windowStartSec: number;
  windowEndSec: number;
  durationSec: number;
  source: {
    provider: "lrclib" | "syncedlyrics";
    id: number | null;
    trackName: string;
    artistName: string;
    via: string;
  };
  /** Pages pretes a afficher : au plus `lyrics.wordsPerPage` mots chacune. */
  pages: Line[];
  captions: Caption[];
};

/**
 * Secours : la lib Python `syncedlyrics` (Musixmatch + LRCLIB + Netease).
 * Optionnelle — si le venv n'existe pas on le dit et on continue sans paroles.
 */
const fallbackSyncedLyrics = (title: string, artist: string): string | null => {
  const script = path.join(ROOT, "py", "fetch_fallback.py");
  const venvPython = path.join(ROOT, "py", ".venv", "bin", "python");
  if (!existsSync(script) || !existsSync(venvPython)) {
    warn("fallback syncedlyrics indisponible (voir py/README.md pour l'installer)");
    return null;
  }
  const res = spawnSync(venvPython, [script, "--title", title, "--artist", artist], {
    encoding: "utf8",
  });
  if (res.status !== 0 || !res.stdout.trim()) {
    warn(`syncedlyrics n'a rien trouve non plus`);
    return null;
  }
  return res.stdout;
};

export const buildLyrics = async (
  config: Config,
  force = false,
): Promise<LyricsOutput | null> => {
  const p = paths(config.slug);
  ensureDir(p.lyrics);

  if (!config.lyrics.enabled) {
    info("paroles desactivees dans le config");
    return null;
  }
  if (existsSync(p.wordsJson) && !force) {
    info("words.json deja present (--force pour regenerer)");
    return JSON.parse(await import("node:fs/promises").then((fs) => fs.readFile(p.wordsJson, "utf8")));
  }

  const { title, artist, album, lang, lrclibId } = config.track;
  const windowStart = parseTime(config.music.start);
  const windowEnd = parseTime(config.music.end);

  // ---- recuperation -----------------------------------------------------
  let synced: string | null = null;
  let source: LyricsOutput["source"] | null = null;
  let resolution: Resolution | null = null;

  try {
    resolution = await resolveLrclib(title, artist, album, lrclibId);
  } catch (e) {
    warn(`LRCLIB : ${(e as Error).message}`);
  }

  if (resolution) {
    synced = resolution.track.syncedLyrics;
    source = {
      provider: "lrclib",
      id: resolution.track.id,
      trackName: resolution.track.trackName,
      artistName: resolution.track.artistName,
      via: resolution.via,
    };
    ok(
      `LRCLIB #${resolution.track.id} — ${resolution.track.artistName} / ` +
        `${resolution.track.trackName} (${resolution.track.duration?.toFixed(0) ?? "?"} s, via ${resolution.via})`,
    );
    if (resolution.alternatives.length > 0) {
      info("autres candidats (a epingler via track.lrclibId si besoin) :");
      for (const alt of resolution.alternatives) {
        info(`    #${alt.id}  ${alt.artistName} / ${alt.trackName}  (${alt.duration?.toFixed(0) ?? "?"} s)`);
      }
    }
    writeFileSync(p.lrclibJson, JSON.stringify(resolution.track, null, 2));
  } else {
    warn("LRCLIB n'a rien de synchronise, essai du fallback");
    synced = fallbackSyncedLyrics(title, artist);
    if (synced) {
      source = {
        provider: "syncedlyrics",
        id: null,
        trackName: title,
        artistName: artist,
        via: "fallback",
      };
      ok("paroles recuperees via syncedlyrics");
    }
  }

  if (!synced || !source) {
    warn("aucune parole synchronisee trouvee — la video sera rendue sans texte");
    return null;
  }

  // ---- ligne -> mot -----------------------------------------------------
  const lrcLines = parseLrc(synced);
  info(`${lrcLines.length} lignes dans le LRC complet`);

  const timed: Line[] = [];
  lrcLines.forEach((line, i) => {
    const next = lrcLines[i + 1]?.startSec ?? null;
    const built = distributeWords(
      line,
      next,
      config.lyrics.maxLineDurationSec,
      lang,
      i,
    );
    if (built) timed.push(built);
  });

  const inWindow = clipToWindow(timed, windowStart, windowEnd);
  if (inWindow.length === 0) {
    warn(
      `aucune parole entre ${windowStart}s et ${windowEnd}s — ` +
        `verifie la fenetre music.start/music.end`,
    );
  }

  const pages = paginate(inWindow, config.lyrics.wordsPerPage);
  const wordCount = inWindow.reduce((n, l) => n + l.words.length, 0);
  ok(`${inWindow.length} lignes / ${wordCount} mots dans la fenetre, ${pages.length} pages`);

  const captions: Caption[] = inWindow.flatMap((line) =>
    line.words.map((w, i) => ({
      // La convention @remotion/captions veut une espace en tete de mot
      // pour marquer les frontieres.
      text: i === 0 ? w.text : ` ${w.text}`,
      startMs: w.startMs,
      endMs: w.endMs,
      timestampMs: w.startMs,
      confidence: null,
    })),
  );

  const output: LyricsOutput = {
    windowStartSec: windowStart,
    windowEndSec: windowEnd,
    durationSec: windowEnd - windowStart,
    source,
    pages,
    captions,
  };

  writeFileSync(p.wordsJson, JSON.stringify(output, null, 2));
  return output;
};

// Execution directe : npm run step:lyrics -- configs/mon-run.json
if (import.meta.url === `file://${process.argv[1]}`) {
  const config = loadConfig(configPathFromArgv());
  step(3, `Paroles — ${config.track.artist} / ${config.track.title}`);
  await buildLyrics(config, hasFlag("--force"));
}
