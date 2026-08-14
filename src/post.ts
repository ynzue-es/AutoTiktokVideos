/**
 * Publie les vidéos de out/fr/ sur TikTok + Instagram via l'API Zernio.
 *
 * Flux par vidéo : presign -> upload (PUT) -> POST /posts (TikTok + IG).
 * Zernio héberge le média et gère l'auth des plateformes.
 *
 * SÉCURITÉ : par défaut = DRY-RUN (prépare et upload, mais NE POSTE PAS).
 *            Il faut le flag --go pour publier réellement.
 *
 * Usage :
 *   npx tsx src/post.ts                      # dry-run, toutes les vidéos
 *   npx tsx src/post.ts --only 01-...mp4     # une seule vidéo
 *   npx tsx src/post.ts --limit 1 --go --now # publie 1 vidéo maintenant
 *   npx tsx src/post.ts --go --schedule      # planifie 1/jour à 19h (Europe/Paris)
 *
 *   # pipeline B (rap.minute) sur la cle BOUTIQUE, 1/jour a 7h :
 *   npx tsx src/post.ts --project rapminute --key BOUTIQUE --schedule --slots 07:00
 *
 * --project : jeu de chemins (voir PROJECTS). Defaut "fr".
 * --key     : suffixe de cle .env. Defaut "" -> ZERNIO_API_KEY /
 *             ZERNIO_TIKTOK_ACCOUNT / ZERNIO_IG_ACCOUNT.
 *             "BOUTIQUE" -> ZERNIO_API_KEY_BOUTIQUE / ..._BOUTIQUE.
 *             Un workspace sans compte IG poste sur TikTok seulement.
 * --slots   : creneaux/jour, ex "07:00" ou "12:30,18:00,21:00" (heure de Paris).
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const API = "https://zernio.com/api/v1";
const TZ = "Europe/Paris";

/**
 * Un "projet" = une source de vidéos + son fichier de textes + son journal.
 * texts: "pairs"  -> [{file, fr}]        (translations.json, pipeline A)
 *        "map"    -> {file: "texte"}     (hooks_fr.json, pipeline B)
 */
const PROJECTS: Record<string, {
  out: string; texts: string; kind: "pairs" | "map";
  index: string; ledger: string; hashtags: string;
}> = {
  fr: {
    out: "out/fr",
    texts: "render/translations.json", kind: "pairs",
    index: "library/index.json",
    ledger: "render/posted.json",
    hashtags: "#musique #rap #hiphop #rapfr #lemursonore",
  },
  rapminute: {
    out: "out/rapminute",
    texts: "render/rapminute/hooks_fr.json", kind: "map",
    index: "library/rapminute/index.json",
    ledger: "render/rapminute/posted.json",
    hashtags: "#rap #rapfr #hiphop #musique #lemursonore",
  },
  skyrock: {
    out: "out/skyrock",
    texts: "render/skyrock/captions_fr.json", kind: "map",
    index: "library/skyrockfm-stock1/index.json",
    ledger: "render/skyrock/posted.json",
    hashtags: "#rap #rapfr #freestyle #musique #lemursonore",
  },
  // vague 2 : stock isolé (librairie, rendus et journal séparés) — cf.
  // render/skyrock/stock.py. Même compte que "skyrock" (clé NEXUS).
  skyrock2: {
    out: "out/skyrock2",
    texts: "render/skyrock/captions_fr2.json", kind: "map",
    index: "library/skyrockfm-stock2/index.json",
    ledger: "render/skyrock/posted2.json",
    hashtags: "#rap #rapfr #freestyle #musique #lemursonore",
  },
  rvpfr: {
    out: "out/rvpfr",
    texts: "render/rvpfr/captions_fr.json", kind: "map",
    index: "library/rvpfr/index.json",
    ledger: "render/rvpfr/posted.json",
    hashtags: "#rap #rapfr #hiphop #actu #lemursonore",
  },
};

// ---- args ------------------------------------------------------------
const args = process.argv.slice(2);
const has = (f: string) => args.includes(f);
const val = (f: string) => { const i = args.indexOf(f); return i >= 0 ? args[i + 1] : undefined; };

const PROJECT = val("--project") ?? "fr";
const P = PROJECTS[PROJECT];
if (!P) throw new Error(`--project inconnu : ${PROJECT} (dispo : ${Object.keys(PROJECTS).join(", ")})`);
const OUT = path.resolve(P.out);
const HASHTAGS = P.hashtags;
const SLOTS = (val("--slots") ?? "19:00").split(",").map((s) => s.trim()).filter(Boolean);

// ---- config / env ----------------------------------------------------
const env = (k: string, optional = false): string => {
  if (process.env[k]) return process.env[k]!;
  const p = path.resolve(".env");
  if (existsSync(p)) {
    const line = readFileSync(p, "utf8").split("\n").find((l) => l.startsWith(k + "="));
    if (line) return line.slice(k.length + 1).trim();
  }
  if (optional) return "";
  throw new Error(`${k} manquant dans .env`);
};

// --key BOUTIQUE -> ZERNIO_API_KEY_BOUTIQUE, ZERNIO_TIKTOK_ACCOUNT_BOUTIQUE, ...
const SUF = val("--key") ? `_${val("--key")}` : "";
const KEY = env(`ZERNIO_API_KEY${SUF}`);
const TT = env(`ZERNIO_TIKTOK_ACCOUNT${SUF}`);
const IG = env(`ZERNIO_IG_ACCOUNT${SUF}`, true);   // absent = workspace sans IG
const H = { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

const GO = has("--go");
const NOW = has("--now");
const SCHEDULE = has("--schedule");
const ONLY = val("--only");
const LIMIT = val("--limit") ? Number(val("--limit")) : Infinity;
const START = val("--start");   // "YYYY-MM-DD" : jour du 1er post (défaut : demain)
const FORCE = has("--force");   // ignore le journal (reposte même si déjà planifié)

// journal des vidéos déjà planifiées (évite les doublons entre vagues)
const LEDGER = path.resolve(P.ledger);
const loadLedger = (): Set<string> =>
  new Set(existsSync(LEDGER) ? (JSON.parse(readFileSync(LEDGER, "utf8")) as string[]) : []);
const saveLedger = (s: Set<string>) =>
  writeFileSync(LEDGER, JSON.stringify([...s], null, 2));

// ---- helpers ---------------------------------------------------------
const durationSec = (file: string): number =>
  Number(spawnSync("ffprobe", [
    "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", file,
  ], { encoding: "utf8" }).stdout.trim());

// les hooks du pipeline B portent un balisage *mot* (violet) : on le retire
const clean = (s: string): string => s.replace(/\*/g, "");
const caption = (fr: string): string => `${clean(fr)}\n\n${HASHTAGS}`;

const presign = async (filename: string): Promise<{ uploadUrl: string; publicUrl: string }> => {
  const r = await fetch(`${API}/media/presign`, {
    method: "POST", headers: H,
    body: JSON.stringify({ filename, contentType: "video/mp4" }),
  });
  if (!r.ok) throw new Error(`presign ${r.status} : ${await r.text()}`);
  return r.json() as Promise<{ uploadUrl: string; publicUrl: string }>;
};

const upload = async (uploadUrl: string, file: string): Promise<void> => {
  const body = await readFile(file);
  const r = await fetch(uploadUrl, {
    method: "PUT", headers: { "Content-Type": "video/mp4" }, body,
  });
  if (!r.ok) throw new Error(`upload ${r.status} : ${await r.text()}`);
};

const buildBody = (publicUrl: string, cap: string, igOk: boolean, when?: string) => {
  const platforms: any[] = [{ platform: "tiktok", accountId: TT }];
  if (igOk && IG) platforms.push({
    platform: "instagram", accountId: IG,
    platformSpecificData: { shareToFeed: true },
  });
  const body: any = {
    content: cap,
    mediaItems: [{ type: "video", url: publicUrl }],
    platforms,
    tiktokSettings: {
      privacy_level: "PUBLIC_TO_EVERYONE",
      allow_comment: true, allow_duet: true, allow_stitch: true,
      content_preview_confirmed: true, express_consent_given: true,
    },
  };
  if (when) { body.scheduledFor = when; body.timezone = TZ; }
  else body.publishNow = true;
  return body;
};

const createPost = async (body: any): Promise<any> => {
  const r = await fetch(`${API}/posts`, { method: "POST", headers: H, body: JSON.stringify(body) });
  const text = await r.text();
  if (!r.ok) throw new Error(`post ${r.status} : ${text}`);
  return JSON.parse(text);
};

// datetime local naïve (interprétée par timezone côté Zernio)
const pad = (n: number) => String(n).padStart(2, "0");
const baseDate = (): Date => {
  const d = new Date();
  d.setHours(12, 0, 0, 0);            // ancre à midi pour éviter les bascules
  if (START) {
    const [y, m, day] = START.split("-").map(Number);
    d.setFullYear(y, m - 1, day);
  } else {
    d.setDate(d.getDate() + 1);       // défaut : premier post = demain
  }
  return d;
};
const scheduleFor = (index: number): string => {
  const day = Math.floor(index / SLOTS.length);
  const slot = SLOTS[index % SLOTS.length];
  const d = baseDate();
  d.setDate(d.getDate() + day);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${slot}:00`;
};

// ---- main ------------------------------------------------------------
const main = async () => {
  const raw = JSON.parse(readFileSync(path.resolve(P.texts), "utf8"));
  const frByFile = new Map<string, string>(
    P.kind === "pairs"
      ? (raw as { file: string; fr: string }[]).map((t) => [t.file, t.fr])
      : Object.entries(raw as Record<string, unknown>)
          .filter(([k, v]) => !k.startsWith("_") && typeof v === "string") as [string, string][],
  );

  // tri par vues d'origine (meilleures d'abord), depuis l'index de la librairie
  const views = new Map<string, number>();
  const idxPath = path.resolve(P.index);
  if (existsSync(idxPath)) {
    for (const r of JSON.parse(readFileSync(idxPath, "utf8")) as any[]) {
      views.set(r.file, r.views ?? 0);
    }
  }
  let files = readdirSync(OUT).filter((f) => f.endsWith(".mp4"))
    .sort((a, b) => (views.get(b) ?? 0) - (views.get(a) ?? 0));
  if (ONLY) files = files.filter((f) => f === ONLY || f.startsWith(ONLY));
  files = files.slice(0, LIMIT);

  console.log(`${GO ? "🚀 PUBLICATION" : "🧪 DRY-RUN (rien ne sera posté)"} — ${files.length} vidéo(s)`);
  console.log(`Projet : ${PROJECT} (${P.out})  ·  clé : ZERNIO_API_KEY${SUF}`);
  console.log(`Cibles : TikTok${IG ? " + Instagram" : " seulement (aucun compte IG sur ce workspace)"}`);
  const modeStr = NOW ? "immédiat"
    : SCHEDULE ? `planifié ${SLOTS.length}/jour (${SLOTS.join(", ")}, ${TZ}), tri par vues`
    : "immédiat (défaut)";
  console.log(`Mode : ${modeStr}\n`);

  const ledger = loadLedger();
  let i = 0;
  for (const f of files) {
    const fr = frByFile.get(f);
    if (!fr) { console.log(`  ⏭️  ${f} : pas de traduction, sauté`); continue; }
    if (!FORCE && ledger.has(f)) { console.log(`  ⏭️  ${f} : déjà planifié (journal), sauté`); continue; }
    const file = path.join(OUT, f);
    const dur = durationSec(file);
    const igOk = dur <= 90;
    const cap = caption(fr);
    const when = SCHEDULE ? scheduleFor(i) : undefined;
    const targets = !IG ? "TikTok"
      : `TikTok + ${igOk ? "Instagram" : "(IG sauté >90s)"}`;

    console.log(`▶ ${f}  [${dur.toFixed(0)}s → ${targets}]${when ? `  @ ${when.slice(0, 16)}` : ""}`);
    const shown = clean(fr);   // ce qui partira vraiment (balisage *…* retiré)
    console.log(`    légende: ${shown.slice(0, 70)}${shown.length > 70 ? "…" : ""}`);

    if (!GO) { console.log("    (dry-run : pas d'upload ni de post)\n"); i++; continue; }

    try {
      const { uploadUrl, publicUrl } = await presign(f);
      await upload(uploadUrl, file);
      const res = await createPost(buildBody(publicUrl, cap, igOk, when));
      ledger.add(f); saveLedger(ledger);   // journalise pour ne pas reposter
      console.log(`    ✓ posté (id: ${res?.post?._id ?? res?._id ?? "ok"})\n`);
    } catch (err) {
      console.log(`    ✗ ${(err as Error).message}\n`);
    }
    i++;
  }
  if (!GO) console.log("Ajoute --go pour publier réellement (--now pour tout de suite, --schedule pour étaler).");
};

main().catch((e) => { console.error(`✗ ${e.message}`); process.exit(1); });
