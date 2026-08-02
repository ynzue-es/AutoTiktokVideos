/**
 * Helpers de montage réutilisables (ffmpeg / ffprobe).
 * Distillé depuis l'ancien pipeline — sans dépendance au reste du code.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";

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

/** Lance une commande (ffmpeg, yt-dlp…) et jette si le code de sortie != 0. */
export const sh = (cmd: string, args: string[], quiet = false): void => {
  const result = spawnSync(cmd, args, {
    stdio: quiet ? ["ignore", "pipe", "pipe"] : "inherit",
  });
  if (result.error) {
    throw new Error(`${cmd} introuvable : ${result.error.message}`);
  }
  if (result.status !== 0) {
    const stderr = result.stderr ? result.stderr.toString() : "";
    throw new Error(`${cmd} a échoué (code ${result.status})\n${stderr}`);
  }
};

export const shCapture = (cmd: string, args: string[]): string => {
  const result = spawnSync(cmd, args, { encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error(`${cmd} a échoué (code ${result.status})\n${result.stderr}`);
  }
  return result.stdout.trim();
};

/** Durée d'un média en secondes, via ffprobe. */
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

export const ensureDir = (dir: string): void => {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
};
