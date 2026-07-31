import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { configSchema, type Config } from "./config.ts";

export const ROOT = process.cwd();

/** Marge telechargee de part et d'autre de la fenetre utile, en secondes. */
export const PAD_SEC = 2;

// ---------------------------------------------------------------- temps

/**
 * "1:32.5" | "00:01:32.500" | "92.5" | 92.5  ->  92.5
 */
export const parseTime = (value: string | number): number => {
  if (typeof value === "number") {
    return value;
  }
  const parts = value.trim().split(":");
  if (parts.some((p) => p === "" || Number.isNaN(Number(p)))) {
    throw new Error(`Temps illisible : "${value}"`);
  }
  return parts.reduce((acc, part) => acc * 60 + Number(part), 0);
};

/** Secondes -> "HH:MM:SS.mmm", le format que comprennent ffmpeg et yt-dlp. */
export const toHms = (seconds: number): string => {
  const clamped = Math.max(0, seconds);
  const h = Math.floor(clamped / 3600);
  const m = Math.floor((clamped % 3600) / 60);
  const s = clamped % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s
    .toFixed(3)
    .padStart(6, "0")}`;
};

// ---------------------------------------------------------------- process

export const sh = (cmd: string, args: string[], quiet = false): void => {
  const result = spawnSync(cmd, args, {
    stdio: quiet ? ["ignore", "pipe", "pipe"] : "inherit",
  });
  if (result.error) {
    throw new Error(`${cmd} introuvable : ${result.error.message}`);
  }
  if (result.status !== 0) {
    const stderr = result.stderr ? result.stderr.toString() : "";
    throw new Error(`${cmd} a echoue (code ${result.status})\n${stderr}`);
  }
};

export const shCapture = (cmd: string, args: string[]): string => {
  const result = spawnSync(cmd, args, { encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(`${cmd} a echoue (code ${result.status})\n${result.stderr}`);
  }
  return result.stdout.trim();
};

/** Duree d'un media, via ffprobe. */
export const probeDuration = (file: string): number =>
  Number(
    shCapture("ffprobe", [
      "-v",
      "error",
      "-show_entries",
      "format=duration",
      "-of",
      "default=noprint_wrappers=1:nokey=1",
      file,
    ]),
  );

// ---------------------------------------------------------------- chemins

export type Paths = ReturnType<typeof paths>;

/**
 * Le dossier de travail vit DANS public/ pour que Remotion puisse servir
 * les medias via staticFile() sans symlink ni copie supplementaire.
 */
export const paths = (slug: string) => {
  const runDir = path.join(ROOT, "public", "runs", slug);
  return {
    slug,
    runDir,
    downloads: path.join(runDir, "downloads"),
    segment: path.join(runDir, "segment"),
    lyrics: path.join(runDir, "lyrics"),
    manifest: path.join(runDir, "manifest.json"),
    wordsJson: path.join(runDir, "lyrics", "words.json"),
    lrclibJson: path.join(runDir, "lyrics", "lrclib.json"),
    segmentAudio: path.join(runDir, "segment", "audio.wav"),
    segmentClip: (i: number) => path.join(runDir, "segment", `clip-${i}.mp4`),
    /** Chemin relatif tel que staticFile() l'attend. */
    staticRel: (rel: string) => `runs/${slug}/${rel}`,
    finalMp4: path.join(ROOT, "out", `${slug}.mp4`),
  };
};

export const ensureDir = (dir: string): void => {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
};

// ---------------------------------------------------------------- config

export const loadConfig = (configPath: string): Config => {
  if (!existsSync(configPath)) {
    throw new Error(`Config introuvable : ${configPath}`);
  }
  const raw: unknown = JSON.parse(readFileSync(configPath, "utf8"));
  const parsed = configSchema.safeParse(raw);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `  - ${i.path.join(".") || "(racine)"} : ${i.message}`)
      .join("\n");
    throw new Error(`Config invalide (${configPath}) :\n${issues}`);
  }
  return parsed.data;
};

/** Recupere le chemin du config passe en argument de la commande. */
export const configPathFromArgv = (): string => {
  const arg = process.argv[2];
  if (!arg) {
    throw new Error(
      "Usage : npm run <commande> -- <chemin/vers/config.json> [--force]",
    );
  }
  return path.resolve(arg);
};

export const hasFlag = (flag: string): boolean => process.argv.includes(flag);

// ---------------------------------------------------------------- logs

export const step = (n: number | string, title: string): void => {
  console.log(`\n\x1b[1m\x1b[36m[${n}] ${title}\x1b[0m`);
};

export const info = (msg: string): void => console.log(`    ${msg}`);
export const ok = (msg: string): void => console.log(`    \x1b[32m✓\x1b[0m ${msg}`);
export const warn = (msg: string): void =>
  console.log(`    \x1b[33m!\x1b[0m ${msg}`);
