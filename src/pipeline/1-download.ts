/**
 * Etape 1 — Telechargement.
 *
 * Recupere l'audio du morceau (version studio) et chaque plan visuel.
 * On ne telecharge JAMAIS la video entiere : `--download-sections` ne tire
 * que la fenetre utile plus une marge de PAD_SEC de chaque cote. Sur un
 * concert d'une heure cela fait quelques Mo au lieu de plusieurs Go.
 *
 * Le son des clips visuels n'est meme pas telecharge (`-f bv*`) : la seule
 * bande-son de la video finale est celle du morceau.
 */
import { readdirSync, rmSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import type { Config } from "./config.ts";
import {
  PAD_SEC,
  configPathFromArgv,
  ensureDir,
  hasFlag,
  info,
  loadConfig,
  ok,
  parseTime,
  paths,
  probeDuration,
  sh,
  step,
  toHms,
  warn,
} from "./util.ts";

export type DownloadedItem = {
  /** Fichier reellement produit par yt-dlp. */
  file: string;
  /** Instant de la source auquel le fichier telecharge commence. */
  sectionStart: number;
  /** Combien couper au debut du fichier pour tomber sur la fenetre utile. */
  trimOffset: number;
};

export type DownloadManifest = {
  music: DownloadedItem & { windowStart: number; windowEnd: number };
  clips: (DownloadedItem & { duration: number; label?: string })[];
};

/**
 * Selecteurs de format essayes dans l'ordre, du plus a moins bon.
 *
 * Deux raisons de descendre progressivement :
 *
 * 1. Qualite. Le recadrage vertical prend le tiers central d'une source 16:9
 *    et l'etire sur 1920 px de haut. Une source 1080p subit donc un
 *    agrandissement de 1,8x, alors qu'une source 1440p ou 4K est simplement
 *    reduite. Plus la source est haute, plus le rendu est net.
 *
 * 2. Robustesse. YouTube refuse regulierement ses formats les plus lourds
 *    (403 sur le VP9 4K, constate et reproductible). Comme `-f "a/b/c"`
 *    choisit le premier format DISPONIBLE et non le premier qui se telecharge,
 *    un refus interrompt tout : il faut donc reessayer nous-memes avec un
 *    plafond de hauteur plus bas.
 */
const CLIP_FORMATS = [
  "bv*[height<=2160][height>=1440]",
  "bv*[height<=1440]",
  "bv*[height<=1080]",
  "bv*",
  "b",
];

const findByPrefix = (dir: string, prefix: string): string | null => {
  if (!existsSync(dir)) return null;
  const match = readdirSync(dir).find(
    (f) => f.startsWith(prefix) && !f.endsWith(".part"),
  );
  return match ? path.join(dir, match) : null;
};

/**
 * Fenetre a telecharger, marge comprise. Si la fenetre commence avant
 * PAD_SEC, on part de 0 et le decalage a couper est reduit d'autant.
 */
const section = (start: number, end: number) => {
  const sectionStart = Math.max(0, start - PAD_SEC);
  return {
    sectionStart,
    sectionEnd: end + PAD_SEC,
    trimOffset: start - sectionStart,
  };
};

export const download = (config: Config, force = false): DownloadManifest => {
  const p = paths(config.slug);
  ensureDir(p.downloads);

  // ---- bande-son ----------------------------------------------------
  const musicStart = parseTime(config.music.start);
  const musicEnd = parseTime(config.music.end);
  if (musicEnd <= musicStart) {
    throw new Error("music.end doit etre posterieur a music.start");
  }
  const musicSection = section(musicStart, musicEnd);

  let musicFile = findByPrefix(p.downloads, "music.");
  if (musicFile && !force) {
    info(`audio deja present, on garde ${path.basename(musicFile)}`);
  } else {
    info(
      `audio ${toHms(musicSection.sectionStart)} -> ${toHms(musicSection.sectionEnd)}`,
    );
    sh("yt-dlp", [
      "-f",
      "bestaudio/best",
      "--extract-audio",
      "--audio-format",
      "m4a",
      "--audio-quality",
      "0",
      "--download-sections",
      `*${toHms(musicSection.sectionStart)}-${toHms(musicSection.sectionEnd)}`,
      "--force-keyframes-at-cuts",
      "--no-playlist",
      "--no-warnings",
      // yt-dlp delegue la coupe a ffmpeg, qui deverse des centaines de
      // lignes de statistiques d'encodage. On ne garde que la barre de
      // progression du telechargement.
      "--quiet",
      "--progress",
      "--downloader-args",
      "ffmpeg:-loglevel error",
      "-o",
      path.join(p.downloads, "music.%(ext)s"),
      config.music.url,
    ]);
    musicFile = findByPrefix(p.downloads, "music.");
  }
  if (!musicFile) {
    throw new Error("yt-dlp n'a produit aucun fichier audio");
  }
  ok(`${path.basename(musicFile)} (${probeDuration(musicFile).toFixed(2)} s)`);

  // ---- plans visuels -------------------------------------------------
  const clips: DownloadManifest["clips"] = [];
  config.clips.forEach((clip, i) => {
    const start = parseTime(clip.start);
    const sec = section(start, start + clip.duration);
    const prefix = `clip-${i}.`;

    let file = findByPrefix(p.downloads, prefix);
    if (file && !force) {
      info(`clip ${i} deja present, on garde ${path.basename(file)}`);
    } else {
      info(
        `clip ${i}${clip.label ? ` (${clip.label})` : ""} ${toHms(sec.sectionStart)} -> ${toHms(sec.sectionEnd)}`,
      );
      let lastError: Error | null = null;
      for (const format of CLIP_FORMATS) {
        try {
          sh("yt-dlp", [
            // Video seule : l'audio de ces plans est inutile, autant ne pas
            // depenser de bande passante ni de disque pour lui.
            "-f",
            format,
            "--download-sections",
            `*${toHms(sec.sectionStart)}-${toHms(sec.sectionEnd)}`,
            "--force-keyframes-at-cuts",
            "--no-playlist",
            "--no-warnings",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--quiet",
            "--progress",
            "--downloader-args",
            "ffmpeg:-loglevel error",
            "-o",
            path.join(p.downloads, `clip-${i}.%(ext)s`),
            clip.url,
          ]);
          lastError = null;
          break;
        } catch (e) {
          lastError = e as Error;
          warn(`format "${format}" refuse par YouTube, essai du suivant`);
          // Un essai interrompu laisse un fichier partiel derriere lui.
          const partial = findByPrefix(p.downloads, prefix);
          if (partial) rmSync(partial, { force: true });
        }
      }
      if (lastError) throw lastError;

      file = findByPrefix(p.downloads, prefix);
    }
    if (!file) {
      throw new Error(`yt-dlp n'a produit aucun fichier pour le clip ${i}`);
    }

    const got = probeDuration(file);
    if (got < clip.duration) {
      warn(
        `clip ${i} : ${got.toFixed(2)} s telechargees pour ${clip.duration} s demandees`,
      );
    }
    ok(`${path.basename(file)} (${got.toFixed(2)} s)`);

    clips.push({
      file,
      sectionStart: sec.sectionStart,
      trimOffset: sec.trimOffset,
      duration: clip.duration,
      label: clip.label,
    });
  });

  const manifest: DownloadManifest = {
    music: {
      file: musicFile,
      sectionStart: musicSection.sectionStart,
      trimOffset: musicSection.trimOffset,
      windowStart: musicStart,
      windowEnd: musicEnd,
    },
    clips,
  };

  ensureDir(p.runDir);
  writeFileSync(
    path.join(p.downloads, "manifest.json"),
    JSON.stringify(manifest, null, 2),
  );
  return manifest;
};

// Execution directe : npm run step:download -- configs/mon-run.json
if (import.meta.url === `file://${process.argv[1]}`) {
  const config = loadConfig(configPathFromArgv());
  step(1, `Telechargement — ${config.slug}`);
  download(config, hasFlag("--force"));
}
