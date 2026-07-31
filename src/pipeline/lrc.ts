/**
 * Parsing LRC et repartition des mots dans le temps.
 *
 * LRCLIB ne donne qu'un timestamp par LIGNE. Pour allumer les mots un par un
 * il faut descendre au mot : on repartit la duree de la ligne entre ses mots
 * au prorata de leur nombre de syllabes, ce qui colle nettement mieux au chant
 * qu'une repartition au nombre de caracteres ("rythme" et "l'" ne durent pas
 * proportionnellement a leur longueur ecrite).
 */

export type LrcLine = { startSec: number; text: string };

export type Word = {
  text: string;
  startMs: number;
  endMs: number;
};

export type Line = {
  /** Index de la ligne dans le LRC complet, pratique pour deboguer. */
  index: number;
  startMs: number;
  endMs: number;
  text: string;
  words: Word[];
};

const LRC_TIME = /\[(\d+):(\d+(?:[.:]\d+)?)\]/g;

/**
 * Une ligne LRC peut porter plusieurs timestamps (refrain repete).
 * Les tags de metadonnees ([ar:], [ti:]...) n'ont pas de partie numerique
 * et sont donc ignores naturellement.
 */
export const parseLrc = (lrc: string): LrcLine[] => {
  const lines: LrcLine[] = [];

  for (const raw of lrc.split(/\r?\n/)) {
    LRC_TIME.lastIndex = 0;
    const stamps: number[] = [];
    let match: RegExpExecArray | null;
    while ((match = LRC_TIME.exec(raw)) !== null) {
      stamps.push(Number(match[1]) * 60 + Number(match[2].replace(":", ".")));
    }
    if (stamps.length === 0) continue;

    const text = raw.replace(LRC_TIME, "").trim();
    for (const startSec of stamps) {
      lines.push({ startSec, text });
    }
  }

  return lines.sort((a, b) => a.startSec - b.startSec);
};

/**
 * Compte les groupes de voyelles. Approximation volontairement simple, mais
 * elle capture l'essentiel : un mot de 3 syllabes tient l'ecran plus longtemps
 * qu'un monosyllabe.
 */
export const countSyllables = (word: string, lang: string): number => {
  const cleaned = word
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z']/g, "");
  if (cleaned.length === 0) return 1;

  const groups = cleaned.match(/[aeiouy]+/g);
  let count = groups ? groups.length : 1;

  // Le "e" final est muet en francais comme en anglais ("rythme", "made").
  if (count > 1 && /e$/.test(cleaned)) count -= 1;
  // Pluriels et conjugaisons francais : "-es", "-ent" restent muets.
  if (lang.startsWith("fr") && count > 1 && /(es|ent)$/.test(cleaned)) count -= 1;

  return Math.max(1, count);
};

/**
 * Attribue un debut et une fin a chaque mot d'une ligne.
 *
 * `maxDurationSec` evite qu'une ligne suivie d'un long pont instrumental
 * ne voie ses mots s'etirer sur trente secondes : au-dela du plafond, la
 * ligne s'arrete et l'ecran se vide.
 */
export const distributeWords = (
  line: LrcLine,
  nextStartSec: number | null,
  maxDurationSec: number,
  lang: string,
  index: number,
): Line | null => {
  const tokens = line.text.split(/\s+/).filter((t) => t.length > 0);
  if (tokens.length === 0) return null;

  const gap = nextStartSec === null ? maxDurationSec : nextStartSec - line.startSec;
  const durationSec = Math.max(0.2, Math.min(gap, maxDurationSec));

  const weights = tokens.map((t) => countSyllables(t, lang));
  const totalWeight = weights.reduce((a, b) => a + b, 0);

  const startMs = Math.round(line.startSec * 1000);
  const durationMs = durationSec * 1000;

  let cursor = startMs;
  const words: Word[] = tokens.map((text, i) => {
    const share = (weights[i] / totalWeight) * durationMs;
    const wordStart = cursor;
    // Le dernier mot absorbe l'arrondi pour que la ligne finisse pile.
    const wordEnd =
      i === tokens.length - 1 ? startMs + Math.round(durationMs) : Math.round(cursor + share);
    cursor = wordEnd;
    return { text, startMs: wordStart, endMs: wordEnd };
  });

  return {
    index,
    startMs,
    endMs: words[words.length - 1].endMs,
    text: tokens.join(" "),
    words,
  };
};

/**
 * Ne conserve que ce qui tombe dans la fenetre [startSec, endSec] et recale
 * le tout sur zero, puisque la video finale commence au debut de la fenetre.
 *
 * Une ligne a cheval sur le bord est conservee : elle sera simplement
 * tronquee, ce qui est preferable a un mot qui disparait en plein milieu.
 */
/**
 * Duree en dessous de laquelle un mot n'a pas le temps d'etre lu : a 30 fps
 * cela represente moins de trois images. Ne sert qu'a ecarter les fragments
 * tronques par le bord de la fenetre.
 */
const MIN_VISIBLE_MS = 90;

export const clipToWindow = (lines: Line[], startSec: number, endSec: number): Line[] => {
  const windowStartMs = Math.round(startSec * 1000);
  const windowEndMs = Math.round(endSec * 1000);

  const result: Line[] = [];

  for (const line of lines) {
    if (line.endMs <= windowStartMs || line.startMs >= windowEndMs) continue;

    const words = line.words
      .filter((w) => w.endMs > windowStartMs && w.startMs < windowEndMs)
      .map((w) => ({
        text: w.text,
        startMs: Math.max(0, w.startMs - windowStartMs),
        endMs: Math.min(windowEndMs - windowStartMs, w.endMs - windowStartMs),
      }))
      .filter((w) => w.endMs > w.startMs);

    // Le premier et le dernier mot peuvent avoir ete rognes par la fenetre
    // jusqu'a n'etre qu'un clignotement. On les retire plutot que de les
    // faire apparaitre une image. Les mots interieurs, eux, sont toujours
    // conserves : en supprimer un trahirait le texte.
    while (words.length > 0 && words[0].endMs - words[0].startMs < MIN_VISIBLE_MS) {
      words.shift();
    }
    while (
      words.length > 0 &&
      words[words.length - 1].endMs - words[words.length - 1].startMs < MIN_VISIBLE_MS
    ) {
      words.pop();
    }

    if (words.length === 0) continue;

    result.push({
      index: line.index,
      startMs: words[0].startMs,
      endMs: words[words.length - 1].endMs,
      text: words.map((w) => w.text).join(" "),
      words,
    });
  }

  return result;
};

/**
 * Decoupe une ligne en pages d'au plus `size` mots, en equilibrant.
 *
 * Un decoupage naif laisse une page orpheline : 7 mots par paquets de 3
 * donnent 3+3+1, et ce mot seul a l'ecran casse le rythme. On repartit
 * donc sur le meme nombre de pages, mais aussi egalement que possible
 * (3+2+2).
 */
export const paginate = (lines: Line[], size: number): Line[] => {
  const pages: Line[] = [];

  for (const line of lines) {
    const total = line.words.length;
    const pageCount = Math.ceil(total / size);
    const base = Math.floor(total / pageCount);
    // Les `remainder` premieres pages prennent un mot de plus.
    const remainder = total % pageCount;

    let cursor = 0;
    for (let i = 0; i < pageCount; i++) {
      const take = base + (i < remainder ? 1 : 0);
      const words = line.words.slice(cursor, cursor + take);
      cursor += take;
      pages.push({
        index: line.index,
        startMs: words[0].startMs,
        endMs: words[words.length - 1].endMs,
        text: words.map((w) => w.text).join(" "),
        words,
      });
    }
  }

  return pages;
};
