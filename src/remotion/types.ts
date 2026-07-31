import { z } from "zod";

/** Un mot et sa fenetre d'affichage, en ms depuis le debut de la video. */
export const wordSchema = z.object({
  text: z.string(),
  startMs: z.number(),
  endMs: z.number(),
});

/** Une page = les quelques mots affiches ensemble a l'ecran. */
export const pageSchema = z.object({
  index: z.number(),
  startMs: z.number(),
  endMs: z.number(),
  text: z.string(),
  words: z.array(wordSchema),
});

export const styleSchema = z.object({
  neonColor: z.string(),
  idleColor: z.string(),
  idleOpacity: z.number(),
  fontSize: z.number(),
  bottomOffset: z.number(),
  maxWidthPct: z.number(),
  fontFile: z.string().nullable(),
  fontFamily: z.string(),
  bottomScrim: z.number(),
});

export const rainSchema = z.object({
  enabled: z.boolean(),
  style: z.enum(["onScreen", "falling"]),
  intensity: z.number(),
  angleDeg: z.number(),
  opacity: z.number(),
});

export const clipSchema = z.object({
  staticSrc: z.string(),
  durationSec: z.number(),
  label: z.string().optional(),
});

/**
 * Props de la composition.
 *
 * `slug` suffit a piloter le rendu : `calculateMetadata` lit les manifestes
 * ecrits par les etapes 2 et 3 et remplit `clips`, `audioSrc` et `pages`.
 * C'est ce qui permet d'ouvrir n'importe quel run dans le Studio sans
 * repasser par l'orchestrateur.
 */
export const neonLyricsSchema = z.object({
  slug: z.string(),
  fps: z.number(),
  fadeToBlackSec: z.number(),
  uppercase: z.boolean(),
  style: styleSchema,
  rain: rainSchema,

  // Remplis par calculateMetadata.
  clips: z.array(clipSchema),
  audioSrc: z.string().nullable(),
  pages: z.array(pageSchema),
});

/** Nom sous lequel une police deposee dans public/fonts/ est enregistree. */
export const CUSTOM_FONT_FAMILY = "AutoTiktokDisplay";

export type Word = z.infer<typeof wordSchema>;
export type Page = z.infer<typeof pageSchema>;
export type Style = z.infer<typeof styleSchema>;
export type Rain = z.infer<typeof rainSchema>;
export type NeonLyricsProps = z.infer<typeof neonLyricsSchema>;
