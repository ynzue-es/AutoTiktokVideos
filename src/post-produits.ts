/**
 * Publie un mini-carrousel par jour sur Facebook ou Instagram : 1 produit
 * Shopify, ses 2 premieres images. Source = la collection « Incontournables »
 * de lemursonore.fr.
 *
 * Flux : Shopify (OAuth client_credentials -> GraphQL collection)
 *        -> telechargement des 2 images
 *        -> presign + PUT sur Zernio
 *        -> POST /posts sur le reseau choisi.
 *
 * Les deux reseaux vivent dans des WORKSPACES Zernio differents, donc sur deux
 * cles d'API : la page Facebook « Le Mur Sonore » est sur le compte
 * lemursonore@gmail.com, le compte Instagram @lemursonoreee sur le compte
 * historique yannis.nzuepro. Chaque reseau tient aussi son propre journal :
 * un produit deja passe sur Facebook peut repasser sur Instagram.
 *
 * SECURITE : par defaut = DRY-RUN. Il faut --go pour publier reellement.
 *
 * Usage :
 *   npx tsx src/post-produits.ts                          # dry-run Facebook
 *   npx tsx src/post-produits.ts --reseau instagram       # dry-run Instagram
 *   npx tsx src/post-produits.ts --go --limit 1           # publie tout de suite
 *   npx tsx src/post-produits.ts --go --schedule --limit 29 --slots 12:00
 *
 * --reseau : "facebook" (defaut) ou "instagram".
 *
 * Les identifiants Shopify vivent dans ../ScriptsShopify/.env (SHOPIFY_STORE,
 * SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET) ; ceux de Zernio dans ./.env
 * (ZERNIO_API_KEY_LEMURSONORE + ZERNIO_FB_ACCOUNT_LEMURSONORE pour Facebook,
 * ZERNIO_API_KEY + ZERNIO_IG_ACCOUNT pour Instagram).
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

const API = "https://zernio.com/api/v1";
const TZ = "Europe/Paris";
const COLLECTION = "incontournables";
const SHOPIFY_API_VERSION = "2024-10";
// Miroir SQLite du catalogue (projet ScriptsShopify) : sert les textes d'artiste.
const BASE_DIR = "../ScriptsShopify";
const BASE_DB = "donnees/catalogue.db";

// ---- args ------------------------------------------------------------
const args = process.argv.slice(2);
const has = (f: string) => args.includes(f);
const val = (f: string) => { const i = args.indexOf(f); return i >= 0 ? args[i + 1] : undefined; };

const RESEAU = (val("--reseau") ?? "facebook").toLowerCase();
if (RESEAU !== "facebook" && RESEAU !== "instagram") {
  throw new Error(`--reseau inconnu : ${RESEAU} (facebook | instagram)`);
}
const GO = has("--go");
const SCHEDULE = has("--schedule");
const LIMIT = Number(val("--limit") ?? 1);
const SLOTS = (val("--slots") ?? "12:00").split(",").map((s) => s.trim()).filter(Boolean);
const START = val("--start");           // "YYYY-MM-DD", defaut : demain
const ONLY = val("--only");             // handle produit precis
const FORCE = has("--force");           // ignore le journal

// ---- env -------------------------------------------------------------
/** Lit une cle dans un .env sans dependance externe (process.env prioritaire). */
const envFrom = (file: string, k: string, optional = false): string => {
  if (process.env[k]) return process.env[k]!;
  const p = path.resolve(file);
  if (existsSync(p)) {
    const line = readFileSync(p, "utf8").split("\n")
      .find((l) => l.trimStart().startsWith(k + "="));
    if (line) return line.trim().slice(k.length + 1).trim();
  }
  if (optional) return "";
  throw new Error(`${k} manquant dans ${file}`);
};

const SHOP_ENV = val("--shopify-env") ?? "../ScriptsShopify/.env";
// Un reseau = un workspace Zernio = une cle + un identifiant de compte.
const CIBLE = RESEAU === "instagram"
  ? { cle: "ZERNIO_API_KEY", compte: "ZERNIO_IG_ACCOUNT", nom: "Instagram @lemursonoreee" }
  : { cle: "ZERNIO_API_KEY_LEMURSONORE", compte: "ZERNIO_FB_ACCOUNT_LEMURSONORE",
      nom: "Facebook — page « Le Mur Sonore »" };
const KEY = envFrom(".env", CIBLE.cle);
const COMPTE = envFrom(".env", CIBLE.compte);
const H = { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" };

/** Accepte handle, handle.myshopify.com ou une URL admin. */
const normalizeStore = (raw: string): string => {
  raw = raw.trim().replace(/^https?:\/\//, "").replace(/\/$/, "");
  const m = raw.match(/admin\.shopify\.com\/store\/([^/]+)/);
  if (m) return `${m[1]}.myshopify.com`;
  return raw.endsWith(".myshopify.com") ? raw : `${raw}.myshopify.com`;
};
const STORE = normalizeStore(envFrom(SHOP_ENV, "SHOPIFY_STORE"));

// ---- journal ---------------------------------------------------------
const LEDGER = path.resolve(`render/${RESEAU}/posted.json`);
const loadLedger = (): string[] =>
  existsSync(LEDGER) ? (JSON.parse(readFileSync(LEDGER, "utf8")) as string[]) : [];
const saveLedger = (l: string[]) => {
  mkdirSync(path.dirname(LEDGER), { recursive: true });
  writeFileSync(LEDGER, JSON.stringify(l, null, 2));
};


// ---- textes ----------------------------------------------------------
/** Enleve les balises et rend les entites HTML les plus courantes. */
const texteBrut = (html: string): string =>
  html.replace(/<[^>]+>/g, "")
      .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")
      .replace(/&#39;|&rsquo;/g, "\u2019")
      .replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">")
      .replace(/\s+/g, " ").trim();

/**
 * Le paragraphe qui parle de l'album, dans la fiche produit.
 *
 * Les fiches suivent toutes le meme plan : un premier <p> de presentation du
 * produit (« … sur votre mur », formats, cadre), puis le <p> de l'album, puis
 * « Caracteristiques » et la tracklist. On prend donc le premier paragraphe
 * qui ne porte aucun marqueur du boilerplate produit.
 */
const BOILERPLATE = /sur votre mur|puce NFC|prêt à accrocher|Caractéristiques|Titres de l|Imprimé et encadré/i;
const paragrapheAlbum = (html: string): string => {
  for (const m of html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/g)) {
    const t = texteBrut(m[1]);
    if (t.length > 80 && !BOILERPLATE.test(t)) return t;
  }
  return "";
};

/**
 * La notice d'artiste du catalogue (table `contextes_artistes` du miroir
 * SQLite). On passe par le client sqlite3 : le module natif n'existe pas sur
 * Node 20 et la base est en lecture seule ici.
 */
const contexteArtiste = (nom: string): string => {
  if (!nom) return "";
  // Le client sqlite3 n'accepte pas de parametre lie en ligne de commande : on
  // inline le nom en litteral, apostrophes doublees comme le veut SQL.
  const litteral = `'${nom.replace(/'/g, "''")}'`;
  const r = spawnSync("sqlite3", [
    "-json", BASE_DB,
    `select texte from contextes_artistes where nom = ${litteral} limit 1`,
  ], { cwd: path.resolve(BASE_DIR), encoding: "utf8" });
  // Base absente ou artiste inconnu : le post part avec le seul texte d'album.
  if (r.status !== 0 || !r.stdout.trim()) return "";
  try {
    const rows = JSON.parse(r.stdout) as { texte: string }[];
    return rows[0]?.texte?.replace(/\s+/g, " ").trim() ?? "";
  } catch { return ""; }
};

// ---- Shopify ---------------------------------------------------------
type Produit = { title: string; handle: string; url: string; artiste: string; album: string; images: string[] };

/** Token Admin API, valable ~24 h, regenere a chaque run. */
const shopifyToken = async (): Promise<string> => {
  const r = await fetch(`https://${STORE}/admin/oauth/access_token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: envFrom(SHOP_ENV, "SHOPIFY_CLIENT_ID"),
      client_secret: envFrom(SHOP_ENV, "SHOPIFY_CLIENT_SECRET"),
    }),
  });
  if (!r.ok) throw new Error(`shopify oauth ${r.status} : ${await r.text()}`);
  return (await r.json() as { access_token: string }).access_token;
};

const QUERY = `
query($h:String!, $cur:String){
  collectionByHandle(handle:$h){
    products(first:100, after:$cur, sortKey:COLLECTION_DEFAULT){
      pageInfo{ hasNextPage endCursor }
      nodes{
        title handle status onlineStoreUrl descriptionHtml
        metafield(namespace:"custom", key:"artiste"){ value }
        media(first:2){ nodes{ ... on MediaImage { image{ url } } } }
      }
    }
  }
}`;

/** Les produits actifs de la collection, dans l'ordre de la vitrine. */
const fetchProduits = async (): Promise<Produit[]> => {
  const token = await shopifyToken();
  const out: Produit[] = [];
  let cur: string | null = null;
  for (;;) {
    const r = await fetch(`https://${STORE}/admin/api/${SHOPIFY_API_VERSION}/graphql.json`, {
      method: "POST",
      headers: { "X-Shopify-Access-Token": token, "Content-Type": "application/json" },
      body: JSON.stringify({ query: QUERY, variables: { h: COLLECTION, cur } }),
    });
    if (!r.ok) throw new Error(`shopify graphql ${r.status} : ${await r.text()}`);
    const d = await r.json() as any;
    if (d.errors) throw new Error(`shopify graphql : ${JSON.stringify(d.errors)}`);
    const c = d.data?.collectionByHandle;
    if (!c) throw new Error(`collection « ${COLLECTION} » introuvable sur ${STORE}`);
    for (const p of c.products.nodes) {
      if (p.status !== "ACTIVE") continue;
      const images = (p.media?.nodes ?? [])
        .map((m: any) => m?.image?.url).filter(Boolean) as string[];
      if (images.length < 2) continue;   // pas de carrousel a une image
      out.push({
        title: p.title, handle: p.handle,
        url: p.onlineStoreUrl ?? `https://lemursonore.fr/products/${p.handle}`,
        artiste: p.metafield?.value ?? "",
        album: paragrapheAlbum(p.descriptionHtml ?? ""),
        images: images.slice(0, 2),
      });
    }
    if (!c.products.pageInfo.hasNextPage) break;
    cur = c.products.pageInfo.endCursor;
  }
  return out;
};

// ---- Zernio ----------------------------------------------------------
/** Recopie une image du CDN Shopify vers l'hebergement Zernio. */
const heberger = async (imgUrl: string, nom: string): Promise<string> => {
  const src = await fetch(imgUrl);
  if (!src.ok) throw new Error(`image ${src.status} : ${imgUrl}`);
  const bin = Buffer.from(await src.arrayBuffer());
  const type = src.headers.get("content-type") ?? "image/jpeg";

  const pr = await fetch(`${API}/media/presign`, {
    method: "POST", headers: H,
    body: JSON.stringify({ filename: nom, contentType: type }),
  });
  if (!pr.ok) throw new Error(`presign ${pr.status} : ${await pr.text()}`);
  const { uploadUrl, publicUrl } = await pr.json() as { uploadUrl: string; publicUrl: string };

  const up = await fetch(uploadUrl, { method: "PUT", headers: { "Content-Type": type }, body: bin });
  if (!up.ok) throw new Error(`upload ${up.status} : ${await up.text()}`);
  return publicUrl;
};

/**
 * Album, puis artiste, puis le lien : rien d'autre.
 *
 * Pas de lien sur Instagram : il n'y est pas cliquable, et le reseau pousse
 * moins les publications qui en portent un.
 */
const legende = (p: Produit): string => {
  const nom = p.title.split(" — ")[0];       // "Artiste · Album"
  const ctx = contexteArtiste(p.artiste);
  const lien = RESEAU === "instagram" ? [] : [``, `👉 ${p.url}`];
  return [`${nom}`, ``, p.album, ...(ctx ? [``, ctx] : []), ...lien]
    .filter((l, i, a) => !(l === "" && a[i - 1] === "")).join("\n");
};

const pad = (n: number) => String(n).padStart(2, "0");
/** Date locale naive : Zernio l'interprete dans `timezone`. */
const scheduleFor = (index: number): string => {
  const d = new Date();
  d.setHours(12, 0, 0, 0);                   // ancre a midi, pas de bascule de jour
  if (START) {
    const [y, m, day] = START.split("-").map(Number);
    d.setFullYear(y, m - 1, day);
  } else {
    d.setDate(d.getDate() + 1);              // defaut : demain
  }
  d.setDate(d.getDate() + Math.floor(index / SLOTS.length));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${SLOTS[index % SLOTS.length]}:00`;
};

const createPost = async (urls: string[], contenu: string, when?: string): Promise<any> => {
  const body: any = {
    content: contenu,
    mediaItems: urls.map((url) => ({ type: "image", url })),
    platforms: [RESEAU === "instagram"
      ? { platform: "instagram", accountId: COMPTE, platformSpecificData: { shareToFeed: true } }
      : { platform: "facebook", accountId: COMPTE }],
  };
  if (when) { body.scheduledFor = when; body.timezone = TZ; }
  else body.publishNow = true;
  const r = await fetch(`${API}/posts`, { method: "POST", headers: H, body: JSON.stringify(body) });
  const text = await r.text();
  if (!r.ok) throw new Error(`post ${r.status} : ${text}`);
  return JSON.parse(text);
};

// ---- main ------------------------------------------------------------
const main = async () => {
  const tous = await fetchProduits();
  const ledger = loadLedger();
  const dejaFait = new Set(ledger);

  let file = ONLY
    ? tous.filter((p) => p.handle === ONLY || p.handle.startsWith(ONLY))
    : tous.filter((p) => FORCE || !dejaFait.has(p.handle));
  // Tour complet fini : on repart du debut, le plus ancien poste en tete.
  if (!file.length && !ONLY) {
    file = [...tous].sort((a, b) => ledger.indexOf(a.handle) - ledger.indexOf(b.handle));
  }
  file = file.slice(0, LIMIT);

  console.log(`${GO ? "🚀 PUBLICATION" : "🧪 DRY-RUN (rien ne sera posté)"} — ${file.length} carrousel(s)`);
  console.log(`Source : ${STORE} / collection « ${COLLECTION} » (${tous.length} produits éligibles)`);
  console.log(`Cible  : ${CIBLE.nom} (${COMPTE})  ·  clé ${CIBLE.cle}`);
  console.log(`Mode   : ${SCHEDULE ? `planifié ${SLOTS.join(", ")} (${TZ})` : "immédiat"}\n`);

  let i = 0;
  for (const p of file) {
    const when = SCHEDULE ? scheduleFor(i) : undefined;
    console.log(`▶ ${p.title}${when ? `  @ ${when.slice(0, 16)}` : ""}`);
    console.log(`    images : ${p.images.length} — ${p.images.map((u) => u.split("/").pop()!.split("?")[0]).join(", ")}`);
    const cap = legende(p);
    // En dry-run on montre la legende entiere : c'est le seul moment ou on peut
    // la relire avant qu'elle parte.
    console.log(cap.split("\n").map((l) => `    │ ${l}`).join("\n"));

    if (!GO) { console.log("    (dry-run : pas d'upload ni de post)\n"); i++; continue; }

    try {
      const urls: string[] = [];
      for (const [n, img] of p.images.entries()) {
        urls.push(await heberger(img, `${p.handle}-${n + 1}.jpg`));
      }
      const res = await createPost(urls, cap, when);
      if (!FORCE) { ledger.push(p.handle); saveLedger(ledger); }
      console.log(`    ✓ posté (id: ${res?.post?._id ?? res?._id ?? "ok"})\n`);
    } catch (err) {
      console.log(`    ✗ ${(err as Error).message}\n`);
    }
    i++;
  }
  if (!GO) console.log("Ajoute --go pour publier réellement (--schedule pour étaler 1/jour).");
};

main().catch((e) => { console.error(`✗ ${e.message}`); process.exit(1); });
