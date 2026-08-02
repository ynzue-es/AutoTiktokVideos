/**
 * Scrape les N derniers reels d'un compte Instagram via Apify,
 * puis télécharge chaque vidéo dans library/.
 *
 * Usage :
 *   APIFY_TOKEN=xxx npx tsx src/scrape-reels.ts sonotradehq 30
 *
 * Le token peut aussi vivre dans un fichier .env (APIFY_TOKEN=...).
 */
import { createWriteStream, existsSync, readFileSync } from "node:fs";
import { mkdir, readdir, unlink, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import path from "node:path";

const ACTOR = "apify~instagram-reel-scraper";
const LIBRARY = path.resolve("library");

// ---- token -----------------------------------------------------------
const loadToken = (): string => {
  if (process.env.APIFY_TOKEN) return process.env.APIFY_TOKEN;
  const envPath = path.resolve(".env");
  if (existsSync(envPath)) {
    const line = readFileSync(envPath, "utf8")
      .split("\n")
      .find((l) => l.startsWith("APIFY_TOKEN="));
    if (line) return line.slice("APIFY_TOKEN=".length).trim();
  }
  throw new Error(
    "APIFY_TOKEN manquant. Ajoute-le dans .env (APIFY_TOKEN=...) ou en variable d'env.",
  );
};

// ---- types (sous-ensemble utile du résultat Apify) -------------------
type Reel = {
  id?: string;
  shortCode?: string;
  url?: string;
  videoUrl?: string;
  caption?: string;
  videoViewCount?: number;
  videoPlayCount?: number;
  likesCount?: number;
  commentsCount?: number;
  timestamp?: string;
  videoDuration?: number;
};

type LibraryEntry = {
  shortCode: string;
  file: string;
  url?: string;
  caption?: string;
  views?: number;
  likes?: number;
  comments?: number;
  timestamp?: string;
  durationSec?: number;
};

// ---- appel Apify -----------------------------------------------------
const runActor = async (
  token: string,
  username: string,
  limit: number,
): Promise<Reel[]> => {
  const url =
    `https://api.apify.com/v2/acts/${ACTOR}/run-sync-get-dataset-items` +
    `?token=${encodeURIComponent(token)}`;

  const input = { username: [username], resultsLimit: limit };

  console.log(`→ Apify : ${limit} derniers reels de @${username}…`);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!res.ok) {
    throw new Error(`Apify a répondu ${res.status} : ${await res.text()}`);
  }
  const items = (await res.json()) as Reel[];
  console.log(`  ${items.length} reels reçus.`);
  return items;
};

// ---- téléchargement --------------------------------------------------
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const download = async (
  videoUrl: string,
  dest: string,
  tries = 3,
): Promise<void> => {
  for (let attempt = 1; attempt <= tries; attempt++) {
    try {
      const res = await fetch(videoUrl);
      if (!res.ok || !res.body) {
        throw new Error(`status ${res.status}`);
      }
      await pipeline(Readable.fromWeb(res.body as any), createWriteStream(dest));
      return;
    } catch (err) {
      if (attempt === tries) throw err;
      await sleep(attempt * 1500); // backoff sur les 502/timeout transitoires du CDN
    }
  }
};

/** Un flux audio est-il présent dans le fichier ? (via ffprobe) */
const hasAudio = (file: string): boolean => {
  const r = spawnSync("ffprobe", [
    "-v", "error", "-select_streams", "a",
    "-show_entries", "stream=codec_type", "-of", "csv=p=0", file,
  ], { encoding: "utf8" });
  return r.status === 0 && r.stdout.trim().length > 0;
};

/**
 * Certains videoUrl Apify sont video-only (DASH). Si pas d'audio, on
 * re-télécharge via yt-dlp depuis l'URL du reel (muxe video+audio).
 */
const redownloadWithAudio = (postUrl: string, dest: string): boolean => {
  const r = spawnSync("yt-dlp", [
    "-q", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
    "--force-overwrites", "-o", dest, postUrl,
  ], { stdio: "ignore" });
  return r.status === 0 && hasAudio(dest);
};

// ---- main ------------------------------------------------------------
const main = async () => {
  const username = process.argv[2] ?? "sonotradehq";
  const limit = Number(process.argv[3] ?? 30);
  const token = loadToken();

  await mkdir(LIBRARY, { recursive: true });

  const reels = await runActor(token, username, limit);
  const index: LibraryEntry[] = [];

  for (let i = 0; i < reels.length; i++) {
    const r = reels[i];
    const shortCode = r.shortCode ?? r.id ?? `reel-${i}`;
    if (!r.videoUrl) {
      console.warn(`  ! ${shortCode} : pas de videoUrl, sauté`);
      continue;
    }
    const rel = `${String(i).padStart(2, "0")}-${shortCode}.mp4`;
    const dest = path.join(LIBRARY, rel);
    process.stdout.write(`  ↓ ${rel} … `);
    try {
      await download(r.videoUrl, dest);
      // videoUrl parfois video-only -> fallback yt-dlp pour récupérer l'audio
      if (!hasAudio(dest) && r.url) {
        process.stdout.write("(sans audio, yt-dlp) ");
        redownloadWithAudio(r.url, dest);
      }
      console.log(hasAudio(dest) ? "ok" : "ok (muet)");
      index.push({
        shortCode,
        file: rel,
        url: r.url,
        caption: r.caption,
        views: r.videoPlayCount ?? r.videoViewCount,
        likes: r.likesCount,
        comments: r.commentsCount,
        timestamp: r.timestamp,
        durationSec: r.videoDuration,
      });
    } catch (err) {
      console.log(`échec (${(err as Error).message})`);
    }
  }

  await writeFile(
    path.join(LIBRARY, "index.json"),
    JSON.stringify(index, null, 2),
  );

  // Purge des mp4 orphelins d'un run précédent (nommage différent).
  const keep = new Set(index.map((e) => e.file));
  for (const f of await readdir(LIBRARY)) {
    if (f.endsWith(".mp4") && !keep.has(f)) {
      await unlink(path.join(LIBRARY, f));
    }
  }

  console.log(`\n✓ ${index.length} reels dans library/ (+ index.json)`);
};

main().catch((err) => {
  console.error(`\n✗ ${err.message}`);
  process.exit(1);
});
