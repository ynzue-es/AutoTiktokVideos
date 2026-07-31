/**
 * Composition principale.
 *
 * Empilement, du fond vers l'avant :
 *   fond noir  ->  plans video  ->  pluie  ->  degrade de lisibilite  ->  paroles
 *
 * La pluie passe DERRIERE le texte : devant, ses trainees claires traversent
 * les lettres et brouillent le halo neon.
 */
import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  cancelRender,
  continueRender,
  delayRender,
  Sequence,
  staticFile,
  useVideoConfig,
} from "remotion";
import { ensureFont, fontStack } from "../load-font.ts";
import type { NeonLyricsProps } from "../types.ts";
import { ClipSequence } from "./ClipSequence.tsx";
import { NeonPage } from "./NeonPage.tsx";
import { RainOverlay } from "./RainOverlay.tsx";

export const NeonLyrics: React.FC<NeonLyricsProps> = ({
  clips,
  audioSrc,
  pages,
  style,
  rain,
  fadeToBlackSec,
  uppercase,
}) => {
  const { fps } = useVideoConfig();

  // La police doit etre prete avant la premiere mesure de fitText, sinon la
  // taille est calculee sur une police de substitution et le texte saute.
  const [fontHandle] = useState(() => delayRender("chargement de la police"));
  useEffect(() => {
    ensureFont(style.fontFile)
      .then(() => continueRender(fontHandle))
      .catch((err) => cancelRender(err));
  }, [fontHandle, style.fontFile]);

  const resolvedStyle = {
    ...style,
    fontFamily: fontStack(style.fontFile, style.fontFamily),
  };

  // Chaque plan porte la moitie de la transition qui le separe du suivant.
  const fadeFrames = Math.max(1, Math.round((fadeToBlackSec * fps) / 2));

  let cursor = 0;
  const positioned = clips.map((clip, i) => {
    const from = cursor;
    const durationInFrames = Math.round(clip.durationSec * fps);
    cursor += durationInFrames;
    return { clip, from, durationInFrames, index: i };
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {positioned.map(({ clip, from, durationInFrames, index }) => (
        <ClipSequence
          key={index}
          src={staticFile(clip.staticSrc)}
          from={from}
          durationInFrames={durationInFrames}
          fadeFrames={fadeFrames}
          isFirst={index === 0}
          isLast={index === positioned.length - 1}
        />
      ))}

      {rain.enabled ? <RainOverlay {...rain} /> : null}

      {/* Assombrit le bas de l'image : sans cela un plan clair avale le texte. */}
      {style.bottomScrim > 0 ? (
        <AbsoluteFill
          style={{
            background: `linear-gradient(to top, rgba(0,0,0,${style.bottomScrim}) 0%, rgba(0,0,0,${
              style.bottomScrim * 0.6
            }) 25%, rgba(0,0,0,0) 55%)`,
          }}
        />
      ) : null}

      {pages.map((page, index) => {
        const from = Math.round((page.startMs / 1000) * fps);
        const to = Math.round((page.endMs / 1000) * fps);
        const durationInFrames = Math.max(1, to - from);

        return (
          <Sequence key={index} from={from} durationInFrames={durationInFrames}>
            <NeonPage
              page={page}
              style={resolvedStyle}
              uppercase={uppercase}
              pageStartMs={page.startMs}
            />
          </Sequence>
        );
      })}

      {audioSrc ? <Audio src={staticFile(audioSrc)} /> : null}
    </AbsoluteFill>
  );
};
