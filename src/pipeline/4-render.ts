/**
 * Etape 4 — Rendu MP4.
 *
 * Les props envoyees a la composition restent minimales : `calculateMetadata`
 * (voir src/remotion/Root.tsx) relit les manifestes des etapes precedentes
 * pour retrouver les plans, la bande-son, les paroles et la duree. On evite
 * ainsi de dupliquer ici une logique qui doit aussi fonctionner dans le Studio.
 */
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import path from "node:path";
import type { Config } from "./config.ts";
import {
  configPathFromArgv,
  ensureDir,
  info,
  loadConfig,
  ok,
  paths,
  ROOT,
  step,
} from "./util.ts";

export const buildInputProps = (config: Config) => ({
  slug: config.slug,
  fps: config.fps,
  fadeToBlackSec: config.transition.fadeToBlackSec,
  uppercase: config.lyrics.uppercase,
  style: config.style,
  rain: config.rain,
  // Remplis par calculateMetadata au moment du rendu.
  clips: [],
  audioSrc: null,
  pages: [],
});

export const render = async (config: Config): Promise<string> => {
  const p = paths(config.slug);
  ensureDir(path.dirname(p.finalMp4));

  info("compilation du bundle Remotion...");
  const serveUrl = await bundle({
    entryPoint: path.join(ROOT, "src", "remotion", "index.ts"),
    publicDir: path.join(ROOT, "public"),
    onProgress: () => undefined,
  });

  const inputProps = buildInputProps(config);

  const composition = await selectComposition({
    serveUrl,
    id: "NeonLyrics",
    inputProps,
  });

  info(
    `composition ${composition.width}x${composition.height} @ ${composition.fps} fps — ` +
      `${composition.durationInFrames} images (${(composition.durationInFrames / composition.fps).toFixed(2)} s)`,
  );

  let lastPercent = -1;
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    // Profil large : lu sans probleme par TikTok comme par les lecteurs
    // de bureau.
    pixelFormat: "yuv420p",
    crf: 18,
    audioCodec: "aac",
    audioBitrate: "192k",
    outputLocation: p.finalMp4,
    inputProps,
    onProgress: ({ progress }) => {
      const percent = Math.round(progress * 100);
      if (percent !== lastPercent && percent % 5 === 0) {
        lastPercent = percent;
        process.stdout.write(`\r    rendu ${percent}%   `);
      }
    },
  });
  process.stdout.write("\r");

  ok(`${path.relative(ROOT, p.finalMp4)}`);
  return p.finalMp4;
};

// Execution directe : npm run step:render -- configs/mon-run.json
if (import.meta.url === `file://${process.argv[1]}`) {
  const config = loadConfig(configPathFromArgv());
  step(4, `Rendu — ${config.slug}`);
  await render(config);
}
