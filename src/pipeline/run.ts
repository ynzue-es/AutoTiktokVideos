/**
 * Orchestrateur.
 *
 *   npm run start -- configs/mon-run.json
 *   npm run start -- configs/mon-run.json --from 3        (reprend aux paroles)
 *   npm run start -- configs/mon-run.json --only 3
 *   npm run start -- configs/mon-run.json --force         (ignore le cache)
 *
 * Chaque etape est deja idempotente : elle detecte ses propres sorties et
 * passe son tour. `--from` et `--only` servent a iterer sur le style sans
 * retelecharger ni redecouper.
 */
import { statSync } from "node:fs";
import path from "node:path";
import { download } from "./1-download.ts";
import { cut } from "./2-cut.ts";
import { buildLyrics } from "./3-lyrics.ts";
import { render } from "./4-render.ts";
import {
  configPathFromArgv,
  hasFlag,
  loadConfig,
  ok,
  paths,
  ROOT,
  step,
} from "./util.ts";

const numericFlag = (name: string): number | null => {
  const i = process.argv.indexOf(name);
  if (i === -1) return null;
  const value = Number(process.argv[i + 1]);
  return Number.isFinite(value) ? value : null;
};

const main = async () => {
  const configPath = configPathFromArgv();
  const config = loadConfig(configPath);
  const force = hasFlag("--force");

  const only = numericFlag("--only");
  const from = only ?? numericFlag("--from") ?? 1;
  const to = only ?? 4;

  const shouldRun = (n: number) => n >= from && n <= to;

  console.log(`\n\x1b[1m${config.slug}\x1b[0m  —  ${path.relative(ROOT, configPath)}`);

  if (shouldRun(1)) {
    step(1, "Telechargement");
    download(config, force);
  }

  if (shouldRun(2)) {
    step(2, "Decoupe 1080x1920");
    cut(config, force);
  }

  if (shouldRun(3)) {
    step(3, `Paroles — ${config.track.artist} / ${config.track.title}`);
    await buildLyrics(config, force);
  }

  if (shouldRun(4)) {
    step(4, "Rendu");
    const output = await render(config);
    const sizeMb = statSync(output).size / 1024 / 1024;
    console.log();
    ok(`\x1b[1m${path.relative(ROOT, output)}\x1b[0m — ${sizeMb.toFixed(1)} Mo`);
  }

  console.log();
};

main().catch((err: unknown) => {
  console.error(`\n\x1b[31mEchec :\x1b[0m ${(err as Error).message}\n`);
  process.exit(1);
});
