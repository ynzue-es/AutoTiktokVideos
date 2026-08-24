/**
 * Publie UN fichier video local en reel sur Facebook ou Instagram.
 *
 * Complement de `post-produits.ts`, qui ne sait poster que des carrousels
 * d'images tires de la boutique. Ici la video est deja faite — elle sort du
 * pipeline E (`render/reels/mix.py`) — et le script ne fait que l'heberger
 * puis la publier.
 *
 * Flux : presign -> PUT sur l'hebergement Zernio -> POST /posts.
 *
 * SECURITE : par defaut = DRY-RUN. Il faut `--go` pour publier reellement.
 * Le dry-run affiche la legende exacte et la taille du fichier, mais ne
 * televerse rien : une video posee sur une page publique ne se reprend pas.
 *
 * Usage :
 *   npx tsx src/post-reel.ts --video ~/Desktop/reel.mp4                  # dry-run
 *   npx tsx src/post-reel.ts --video ~/Desktop/reel.mp4 --go             # publie
 *   npx tsx src/post-reel.ts --video ... --reseau instagram --go
 *   npx tsx src/post-reel.ts --video ... --at 2026-08-25T12:00 --go      # programme
 *
 * --legende  texte complet (sinon : --titre / --lien composent le defaut)
 * --reseau   "facebook" (defaut) ou "instagram"
 *
 * Les cles vivent dans ./.env, les memes que `post-produits.ts` :
 * ZERNIO_API_KEY_LEMURSONORE + ZERNIO_FB_ACCOUNT_LEMURSONORE pour Facebook,
 * ZERNIO_API_KEY + ZERNIO_IG_ACCOUNT pour Instagram.
 */
import { readFileSync, existsSync, statSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const API = "https://zernio.com/api/v1";
const TZ = "Europe/Paris";

// ---- args ------------------------------------------------------------
const args = process.argv.slice(2);
const has = (f: string) => args.includes(f);
const val = (f: string) => { const i = args.indexOf(f); return i >= 0 ? args[i + 1] : undefined; };

const VIDEO = val("--video");
if (!VIDEO) throw new Error("--video <fichier.mp4> est obligatoire");
const FICHIER = path.resolve(VIDEO.replace(/^~/, process.env.HOME ?? "~"));
if (!existsSync(FICHIER)) throw new Error(`introuvable : ${FICHIER}`);

const RESEAU = (val("--reseau") ?? "facebook").toLowerCase();
if (RESEAU !== "facebook" && RESEAU !== "instagram") {
  throw new Error(`--reseau inconnu : ${RESEAU} (facebook | instagram)`);
}
const GO = has("--go");
const AT = val("--at");                 // "YYYY-MM-DDTHH:MM" local, sinon immediat
const FORCE = has("--force");           // ignore le journal

// ---- env -------------------------------------------------------------
/** Lit une cle dans un .env sans dependance externe (process.env prioritaire). */
const envFrom = (file: string, k: string): string => {
  if (process.env[k]) return process.env[k]!;
  const p = path.resolve(file);
  if (existsSync(p)) {
    const line = readFileSync(p, "utf8").split("\n")
      .find((l) => l.trimStart().startsWith(k + "="));
    if (line) return line.trim().slice(k.length + 1).trim();
  }
  throw new Error(`${k} manquant dans ${file}`);
};

// Un reseau = un workspace Zernio = une cle + un identifiant de compte.
const CIBLE = RESEAU === "instagram"
  ? { cle: "ZERNIO_API_KEY", compte: "ZERNIO_IG_ACCOUNT", nom: "Instagram @lemursonoreee" }
  : { cle: "ZERNIO_API_KEY_LEMURSONORE", compte: "ZERNIO_FB_ACCOUNT_LEMURSONORE",
      nom: "Facebook — page « Le Mur Sonore »" };
const KEY = envFrom(".env", CIBLE.cle);
const COMPTE = envFrom(".env", CIBLE.compte);
const H = { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

// ---- journal ---------------------------------------------------------
// Un journal par reseau, comme les autres pipelines : la meme video peut
// legitimement passer sur Facebook et sur Instagram.
const JOURNAL = path.resolve(`render/${RESEAU}/posted-reels.json`);
const lireJournal = (): string[] =>
  existsSync(JOURNAL) ? JSON.parse(readFileSync(JOURNAL, "utf8")) : [];
const noterJournal = (nom: string) => {
  mkdirSync(path.dirname(JOURNAL), { recursive: true });
  writeFileSync(JOURNAL, JSON.stringify([...lireJournal(), nom], null, 2));
};

// ---- legende ---------------------------------------------------------
const legende = (): string => {
  const explicite = val("--legende");
  if (explicite) return explicite;
  const titre = val("--titre") ?? "";
  const lien = val("--lien");
  // Pas de lien sur Instagram : il n'y est pas cliquable, et le reseau pousse
  // moins les publications qui en portent un.
  const pied = RESEAU === "instagram" || !lien ? [] : [``, `👉 ${lien}`];
  return [titre, ``, `Affiche encadrée, tracklist complète, impression qualité musée.`,
          `Plus de 6 000 artistes.`, ...pied]
    .filter((l, i, a) => !(l === "" && a[i - 1] === "")).join("\n");
};

// ---- Zernio ----------------------------------------------------------
/** Televerse le mp4 et rend son URL publique. */
const heberger = async (): Promise<string> => {
  const bin = readFileSync(FICHIER);
  const pr = await fetch(`${API}/media/presign`, {
    method: "POST", headers: H,
    body: JSON.stringify({ filename: path.basename(FICHIER), contentType: "video/mp4" }),
  });
  if (!pr.ok) throw new Error(`presign ${pr.status} : ${await pr.text()}`);
  const { uploadUrl, publicUrl } = await pr.json() as { uploadUrl: string; publicUrl: string };

  const up = await fetch(uploadUrl, {
    method: "PUT", headers: { "Content-Type": "video/mp4" }, body: bin,
  });
  if (!up.ok) throw new Error(`upload ${up.status} : ${await up.text()}`);
  return publicUrl;
};

/**
 * Poste la video. Tente d'abord le format REEL explicite.
 *
 * Zernio ne documente pas partout le nom du champ, et un intitule inconnu se
 * fait refuser en 400 par la validation. On retente donc sans lui : une video
 * verticale de moins de 90 s part de toute facon en reel chez Meta, le champ
 * ne fait que le rendre explicite.
 */
const publier = async (url: string, contenu: string): Promise<any> => {
  const base = (specifique?: any): any => {
    const body: any = {
      content: contenu,
      mediaItems: [{ type: "video", url }],
      platforms: [{
        platform: RESEAU, accountId: COMPTE,
        ...(specifique ? { platformSpecificData: specifique } : {}),
      }],
    };
    if (AT) { body.scheduledFor = `${AT}:00`.slice(0, 19); body.timezone = TZ; }
    else body.publishNow = true;
    return body;
  };
  const specifique = RESEAU === "instagram"
    ? { mediaType: "REELS", shareToFeed: true }
    : { postType: "reel" };

  for (const corps of [base(specifique), base()]) {
    const r = await fetch(`${API}/posts`, {
      method: "POST", headers: H, body: JSON.stringify(corps),
    });
    const texte = await r.text();
    if (r.ok) return JSON.parse(texte);
    if (r.status !== 400) throw new Error(`post ${r.status} : ${texte}`);
    console.log(`  format reel explicite refusé, second essai sans :\n    ${texte.slice(0, 200)}`);
  }
  throw new Error("les deux formats ont été refusés");
};

// ---- main ------------------------------------------------------------
const main = async () => {
  const nom = path.basename(FICHIER);
  const taille = statSync(FICHIER).size / 1024 / 1024;
  const contenu = legende();

  console.log(`${GO ? "🚀 PUBLICATION" : "🧪 DRY-RUN (rien ne sera posté)"} — ${CIBLE.nom}`);
  console.log(`Fichier : ${nom} (${taille.toFixed(1)} Mo)`);
  console.log(`Quand   : ${AT ? `${AT} (${TZ})` : "tout de suite"}`);
  console.log(`\n--- légende ---\n${contenu}\n---------------\n`);

  if (!FORCE && lireJournal().includes(nom)) {
    console.log(`⚠️  déjà publié sur ${RESEAU} d'après ${JOURNAL} — --force pour repasser outre`);
    return;
  }
  if (!GO) { console.log("(dry-run : ni téléversement ni publication)"); return; }

  console.log("téléversement…");
  const url = await heberger();
  console.log(`  hébergé : ${url}`);
  const res = await publier(url, contenu);
  noterJournal(nom);
  console.log(`✅ publié — ${JSON.stringify(res).slice(0, 300)}`);
};

main().catch((e) => { console.error(`❌ ${e.message}`); process.exit(1); });
