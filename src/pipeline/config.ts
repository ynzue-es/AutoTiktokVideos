import { z } from "zod";

/**
 * Un temps accepte plusieurs ecritures : 92, "92", "1:32", "01:32.500",
 * "00:01:32.500". Toujours normalise en secondes flottantes.
 */
export const timeSchema = z.union([z.number(), z.string()]);

export const clipSchema = z.object({
  /** URL YouTube. Le son de ce clip est TOUJOURS supprime. */
  url: z.string().url(),
  /** Debut du plan dans la video source. */
  start: timeSchema,
  /** Duree du plan a l'ecran, en secondes. */
  duration: z.number().positive(),
  /** Libelle purement informatif, affiche dans les logs. */
  label: z.string().optional(),
});

export const configSchema = z.object({
  /** Identifiant du run : nomme le dossier de travail et le MP4 final. */
  slug: z
    .string()
    .regex(/^[a-z0-9-]+$/, "slug : minuscules, chiffres et tirets uniquement"),

  /**
   * La bande-son. Doit pointer vers la version STUDIO du morceau
   * (clip officiel ou chaine "- Topic"), sinon les timings LRCLIB
   * ne correspondront pas.
   */
  music: z.object({
    url: z.string().url(),
    start: timeSchema,
    end: timeSchema,
  }),

  /** Les plans visuels, dans l'ordre. Muets. */
  clips: z.array(clipSchema).min(1),

  transition: z
    .object({
      /** Duree totale du fondu au noir, a cheval sur la coupe. */
      fadeToBlackSec: z.number().min(0).default(0.6),
    })
    .default({}),

  /** Sert a interroger LRCLIB. */
  track: z.object({
    title: z.string(),
    artist: z.string(),
    album: z.string().optional(),
    /** Code langue ISO, informatif (utilise pour la coupure syllabique). */
    lang: z.string().default("en"),
    /**
     * Si LRCLIB se trompe de version (remix, live, edit), colle ici l'id
     * exact d'un resultat de recherche pour court-circuiter le matching.
     */
    lrclibId: z.number().nullable().default(null),
  }),

  lyrics: z
    .object({
      enabled: z.boolean().default(true),
      /**
       * Une ligne LRC dure jusqu'a la suivante. Sur un pont instrumental
       * cet ecart peut faire 30 s : on plafonne pour ne pas etirer les
       * mots dans le vide.
       */
      maxLineDurationSec: z.number().positive().default(6),
      /** Nombre de mots affiches simultanement a l'ecran. */
      wordsPerPage: z.number().int().positive().default(3),
      /** Passe le texte en majuscules. */
      uppercase: z.boolean().default(true),
    })
    .default({}),

  style: z
    .object({
      /** Couleur du glow neon. */
      neonColor: z.string().default("#00E5FF"),
      /** Couleur des mots pas encore chantes. */
      idleColor: z.string().default("#FFFFFF"),
      /** Opacite des mots pas encore chantes. */
      idleOpacity: z.number().min(0).max(1).default(0.35),
      fontSize: z.number().positive().default(110),
      /** Distance entre le bas de l'ecran et le bloc de paroles, en px. */
      bottomOffset: z.number().default(420),
      /**
       * Largeur maximale du texte, en fraction de l'ecran.
       *
       * TikTok superpose sa colonne de boutons (partage, like, commentaires)
       * sur la droite et son bloc de legende en bas. Au-dela de ~0,72 le
       * texte passe dessous.
       */
      maxWidthPct: z.number().min(0.3).max(1).default(0.72),
      /**
       * Depose un .ttf ou .otf dans public/fonts/ et mets son nom de fichier
       * ici pour l'utiliser. Sans cela on retombe sur une police systeme
       * grasse, ce qui evite toute dependance reseau.
       */
      fontFile: z.string().nullable().default(null),
      fontFamily: z
        .string()
        .default("Impact, 'Arial Black', 'Helvetica Neue', sans-serif"),
      /** Assombrit le bas de l'image pour que le texte reste lisible. */
      bottomScrim: z.number().min(0).max(1).default(0.55),
    })
    .default({}),

  rain: z
    .object({
      enabled: z.boolean().default(true),
      /**
       * "onScreen" : les gouttes s'ecrasent sur l'objectif, restent collees
       *   a la vitre et glissent en deformant l'image derriere elles.
       * "falling"  : averse vue de loin, les gouttes traversent le champ.
       */
      style: z.enum(["onScreen", "falling"]).default("onScreen"),
      /** 0 = rien, 1 = averse. Pilote le nombre de gouttes. */
      intensity: z.number().min(0).max(1).default(0.6),
      /** Inclinaison des gouttes. N'a d'effet qu'en mode "falling". */
      angleDeg: z.number().default(12),
      opacity: z.number().min(0).max(1).default(0.5),
    })
    .default({}),

  fps: z.number().int().positive().default(30),
});

export type Config = z.infer<typeof configSchema>;
export type Clip = z.infer<typeof clipSchema>;
