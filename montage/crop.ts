/**
 * Recadrage vertical — ramène n'importe quelle source en 1080x1920.
 *
 * On agrandit jusqu'à couvrir le cadre (force_original_aspect_ratio=increase)
 * puis on rogne au centre. Une source 16:9 perd donc beaucoup sur les côtés :
 * c'est le comportement attendu pour du format vertical (TikTok / Reels).
 */
import { ensureDir, sh, toHms } from "./util.ts";
import path from "node:path";

export type CropOptions = {
  /** Fichier source. */
  input: string;
  /** Fichier de sortie (.mp4). */
  output: string;
  /** Début du plan dans la source, en secondes. Défaut 0. */
  startSec?: number;
  /** Durée du plan à garder, en secondes. Défaut : jusqu'à la fin. */
  durationSec?: number;
  /** Largeur cible. Défaut 1080. */
  width?: number;
  /** Hauteur cible. Défaut 1920. */
  height?: number;
  fps?: number;
  /** Garder l'audio de la source ? Défaut false (on jette). */
  keepAudio?: boolean;
};

const filter = (w: number, h: number, fps: number) =>
  [
    `scale=${w}:${h}:force_original_aspect_ratio=increase`,
    `crop=${w}:${h}`,
    `fps=${fps}`,
    "setsar=1",
  ].join(",");

/** Recadre + coupe un plan vers le format vertical. */
export const cropVertical = (opts: CropOptions): string => {
  const {
    input,
    output,
    startSec = 0,
    durationSec,
    width = 1080,
    height = 1920,
    fps = 30,
    keepAudio = false,
  } = opts;

  ensureDir(path.dirname(output));

  const args = [
    "-y",
    "-hide_banner",
    "-loglevel",
    "error",
    "-ss",
    toHms(startSec),
    "-i",
    input,
    ...(durationSec !== undefined ? ["-t", String(durationSec)] : []),
    ...(keepAudio ? [] : ["-an"]),
    "-vf",
    filter(width, height, fps),
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
    output,
  ];

  sh("ffmpeg", args, true);
  return output;
};
