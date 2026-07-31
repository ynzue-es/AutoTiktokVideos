/**
 * Chargement de police, sans reseau.
 *
 * Par defaut on se contente d'une police systeme grasse, ce qui garantit un
 * rendu identique hors ligne. Si `style.fontFile` designe un fichier depose
 * dans public/fonts/, il est enregistre sous CUSTOM_FONT_FAMILY et prend le
 * pas sur la pile systeme.
 */
import { staticFile } from "remotion";
import { CUSTOM_FONT_FAMILY } from "./types.ts";

let pending: Promise<void> | null = null;

export const ensureFont = (fontFile: string | null): Promise<void> => {
  if (!fontFile) return Promise.resolve();
  // Une seule tentative par processus de rendu, meme si plusieurs images
  // sont calculees en parallele.
  if (pending) return pending;

  pending = (async () => {
    const face = new FontFace(
      CUSTOM_FONT_FAMILY,
      `url(${staticFile(`fonts/${fontFile}`)})`,
    );
    await face.load();
    document.fonts.add(face);
  })();

  return pending;
};

/** Pile de polices effective, police locale en tete si elle existe. */
export const fontStack = (fontFile: string | null, fallback: string): string =>
  fontFile ? `${CUSTOM_FONT_FAMILY}, ${fallback}` : fallback;
