/**
 * Etape 2 — Decoupe et recadrage.
 *
 * Chaque plan est ramene a 1080x1920 : on agrandit jusqu'a couvrir le cadre
 * (`force_original_aspect_ratio=increase`) puis on rogne au centre. Une source
 * 16:9 perd donc beaucoup sur les cotes, ce qui est le comportement attendu
 * pour du vertical.
 *
 * L'audio sort en WAV : pas de delai d'amorcage AAC, donc pas de decalage
 * d'une poignee de millisecondes entre le son et les paroles.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Config } from "./config.ts";
import type { DownloadManifest } from "./1-download.ts";
import {
  configPathFromArgv,
  ensureDir,
  hasFlag,
  info,
  loadConfig,
  ok,
  paths,
  probeDuration,
  sh,
  step,
  toHms,
} from "./util.ts";

export type CutManifest = {
  audio: { file: string; staticSrc: string; durationSec: number };
  clips: {
    file: string;
    staticSrc: string;
    durationSec: number;
    label?: string;
  }[];
  totalDurationSec: number;
};

const VIDEO_FILTER = (fps: number) =>
  [
    "scale=1080:1920:force_original_aspect_ratio=increase",
    "crop=1080:1920",
    `fps=${fps}`,
    "setsar=1",
  ].join(",");

export const cut = (config: Config, force = false): CutManifest => {
  const p = paths(config.slug);
  ensureDir(p.segment);

  const downloadManifestPath = path.join(p.downloads, "manifest.json");
  if (!existsSync(downloadManifestPath)) {
    throw new Error("Etape 1 non executee : downloads/manifest.json manquant");
  }
  const dl: DownloadManifest = JSON.parse(
    readFileSync(downloadManifestPath, "utf8"),
  );

  // ---- bande-son ------------------------------------------------------
  const musicDuration = dl.music.windowEnd - dl.music.windowStart;
  if (!existsSync(p.segmentAudio) || force) {
    info(`audio : ${musicDuration.toFixed(2)} s a partir de ${toHms(dl.music.trimOffset)}`);
    sh(
      "ffmpeg",
      [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        toHms(dl.music.trimOffset),
        "-i",
        dl.music.file,
        "-t",
        String(musicDuration),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
        p.segmentAudio,
      ],
      true,
    );
  }
  const audioDuration = probeDuration(p.segmentAudio);
  ok(`audio.wav — ${audioDuration.toFixed(2)} s`);

  // ---- plans visuels ---------------------------------------------------
  const clips: CutManifest["clips"] = [];
  dl.clips.forEach((clip, i) => {
    const out = p.segmentClip(i);
    if (!existsSync(out) || force) {
      info(
        `clip ${i} : ${clip.duration} s a partir de ${toHms(clip.trimOffset)} -> 1080x1920`,
      );
      sh(
        "ffmpeg",
        [
          "-y",
          "-hide_banner",
          "-loglevel",
          "error",
          "-ss",
          toHms(clip.trimOffset),
          "-i",
          clip.file,
          "-t",
          String(clip.duration),
          // Le son de la source est jete ici, definitivement.
          "-an",
          "-vf",
          VIDEO_FILTER(config.fps),
          "-c:v",
          "libx264",
          "-preset",
          "veryfast",
          "-crf",
          "18",
          "-pix_fmt",
          "yuv420p",
          "-movflags",
          "+faststart",
          out,
        ],
        true,
      );
    }
    const duration = probeDuration(out);
    ok(`clip-${i}.mp4 — ${duration.toFixed(2)} s${clip.label ? ` (${clip.label})` : ""}`);
    clips.push({
      file: out,
      staticSrc: p.staticRel(`segment/clip-${i}.mp4`),
      durationSec: duration,
      label: clip.label,
    });
  });

  const totalClipDuration = clips.reduce((sum, c) => sum + c.durationSec, 0);
  if (Math.abs(totalClipDuration - audioDuration) > 0.5) {
    info(
      `note : ${totalClipDuration.toFixed(2)} s de visuel pour ${audioDuration.toFixed(2)} s de musique — ` +
        `la composition s'aligne sur le plus court`,
    );
  }

  const manifest: CutManifest = {
    audio: {
      file: p.segmentAudio,
      staticSrc: p.staticRel("segment/audio.wav"),
      durationSec: audioDuration,
    },
    clips,
    totalDurationSec: Math.min(totalClipDuration, audioDuration),
  };

  writeFileSync(
    path.join(p.segment, "manifest.json"),
    JSON.stringify(manifest, null, 2),
  );
  return manifest;
};

// Execution directe : npm run step:cut -- configs/mon-run.json
if (import.meta.url === `file://${process.argv[1]}`) {
  const config = loadConfig(configPathFromArgv());
  step(2, `Decoupe 1080x1920 — ${config.slug}`);
  cut(config, hasFlag("--force"));
}
