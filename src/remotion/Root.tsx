/**
 * Enregistrement de la composition.
 *
 * La composition n'est pilotee que par `slug` et les reglages de style :
 * `calculateMetadata` va lire les manifestes ecrits par les etapes 2 et 3
 * pour en deduire les plans, la bande-son, les paroles et la duree. On peut
 * donc ouvrir n'importe quel run dans le Studio en changeant simplement le
 * slug, sans repasser par l'orchestrateur.
 */
import React from "react";
import { Composition, staticFile, type CalculateMetadataFunction } from "remotion";
import { NeonLyrics } from "./NeonLyrics/index.tsx";
import { neonLyricsSchema, type NeonLyricsProps } from "./types.ts";

type SegmentManifest = {
  audio: { staticSrc: string; durationSec: number };
  clips: { staticSrc: string; durationSec: number; label?: string }[];
};

type LyricsFile = {
  pages: NeonLyricsProps["pages"];
};

const fetchJson = async <T,>(src: string): Promise<T | null> => {
  const res = await fetch(staticFile(src));
  if (!res.ok) return null;
  return (await res.json()) as T;
};

const calculateMetadata: CalculateMetadataFunction<NeonLyricsProps> = async ({
  props,
}) => {
  const { slug, fps } = props;

  const segment = await fetchJson<SegmentManifest>(
    `runs/${slug}/segment/manifest.json`,
  );
  if (!segment) {
    throw new Error(
      `runs/${slug}/segment/manifest.json introuvable — lance d'abord les etapes 1 et 2`,
    );
  }

  // Les paroles sont facultatives : un run sans correspondance LRCLIB doit
  // quand meme pouvoir etre rendu.
  const lyrics = await fetchJson<LyricsFile>(`runs/${slug}/lyrics/words.json`);

  const clipsDuration = segment.clips.reduce((sum, c) => sum + c.durationSec, 0);
  // On s'aligne sur le plus court : ni musique qui continue sur du noir, ni
  // image qui tourne dans le silence.
  const durationSec = Math.min(clipsDuration, segment.audio.durationSec);

  return {
    fps,
    width: 1080,
    height: 1920,
    durationInFrames: Math.max(1, Math.round(durationSec * fps)),
    props: {
      ...props,
      clips: segment.clips,
      audioSrc: segment.audio.staticSrc,
      pages: lyrics?.pages ?? [],
    },
  };
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="NeonLyrics"
    component={NeonLyrics}
    schema={neonLyricsSchema}
    calculateMetadata={calculateMetadata}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={600}
    defaultProps={{
      slug: "daft-punk-get-lucky",
      fps: 30,
      fadeToBlackSec: 0.6,
      uppercase: true,
      style: {
        neonColor: "#00E5FF",
        idleColor: "#FFFFFF",
        idleOpacity: 0.35,
        fontSize: 110,
        bottomOffset: 420,
        maxWidthPct: 0.72,
        fontFile: null,
        fontFamily: "Impact, 'Arial Black', 'Helvetica Neue', sans-serif",
        bottomScrim: 0.55,
      },
      rain: {
        enabled: true,
        style: "onScreen" as const,
        intensity: 0.6,
        angleDeg: 12,
        opacity: 0.5,
      },
      clips: [],
      audioSrc: null,
      pages: [],
    }}
  />
);
