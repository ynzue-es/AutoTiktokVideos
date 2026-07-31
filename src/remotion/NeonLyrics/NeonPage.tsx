/**
 * Une page de paroles : les quelques mots affiches ensemble, dont un seul
 * est allume a la fois.
 *
 * Reprend le principe du template officiel (comparaison du temps courant aux
 * bornes de chaque token) mais remplace le simple changement de couleur par
 * le neon, et ajuste la taille de police pour que la page tienne dans le
 * cadre vertical.
 */
import { fitText } from "@remotion/layout-utils";
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import type { Page, Style } from "../types.ts";
import { NeonWord } from "./NeonWord.tsx";

export const NeonPage: React.FC<{
  readonly page: Page;
  readonly style: Style;
  readonly uppercase: boolean;
  /** Debut de la page en ms, pour repasser en temps absolu. */
  readonly pageStartMs: number;
}> = ({ page, style, uppercase, pageStartMs }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const timeMs = pageStartMs + (frame / fps) * 1000;

  const displayText = uppercase ? page.text.toUpperCase() : page.text;

  // On ne depasse jamais la taille demandee, mais on retrecit si la page
  // deborde de la zone sure — celle que l'interface de TikTok ne recouvre pas.
  const fitted = fitText({
    fontFamily: style.fontFamily,
    text: displayText,
    withinWidth: width * style.maxWidthPct,
    fontWeight: "900",
  });
  const fontSize = Math.min(style.fontSize, fitted.fontSize);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: style.bottomOffset,
        paddingLeft: 60,
        paddingRight: 60,
      }}
    >
      <div
        style={{
          fontFamily: style.fontFamily,
          fontWeight: 900,
          fontSize,
          lineHeight: 1.1,
          letterSpacing: "0.01em",
          textAlign: "center",
          textTransform: uppercase ? "uppercase" : "none",
        }}
      >
        {page.words.map((word, i) => {
          const active = timeMs >= word.startMs && timeMs < word.endMs;
          const framesSinceOn = ((timeMs - word.startMs) / 1000) * fps;

          return (
            <React.Fragment key={`${word.startMs}-${i}`}>
              <NeonWord
                text={uppercase ? word.text.toUpperCase() : word.text}
                active={active}
                framesSinceOn={framesSinceOn}
                style={style}
                fontSize={fontSize}
              />
              {i < page.words.length - 1 ? <span> </span> : null}
            </React.Fragment>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
