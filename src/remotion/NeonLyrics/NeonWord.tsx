/**
 * Un mot, eteint ou allume.
 *
 * Le neon est obtenu en empilant plusieurs `text-shadow` de rayons croissants
 * autour d'un coeur blanc : les petits rayons donnent le trait lumineux, les
 * grands la diffusion dans l'air. C'est ce degrade de halos qui fait la
 * difference avec un simple `color` fluo.
 */
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Style } from "../types.ts";

/** Rayons des halos, en px a la taille de police de reference. */
const HALO_RADII = [4, 11, 22, 42, 78];
const REFERENCE_FONT_SIZE = 110;

export const NeonWord: React.FC<{
  readonly text: string;
  readonly active: boolean;
  /** Nombre d'images ecoulees depuis l'allumage, negatif si pas encore allume. */
  readonly framesSinceOn: number;
  readonly style: Style;
  readonly fontSize: number;
}> = ({ text, active, framesSinceOn, style, fontSize }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Petit sursaut a l'allumage, comme un tube qui s'amorce.
  const ignite = spring({
    frame: Math.max(0, framesSinceOn),
    fps,
    config: { damping: 14, stiffness: 220, mass: 0.5 },
    durationInFrames: 12,
  });

  // Respiration lente du halo : un neon reel n'est jamais parfaitement fixe.
  const breathe = 0.9 + 0.1 * Math.sin((frame / fps) * 5.5);

  const scale = active ? interpolate(ignite, [0, 1], [0.86, 1]) : 0.94;
  const glowStrength = active ? ignite * breathe : 0;

  const ratio = fontSize / REFERENCE_FONT_SIZE;
  const shadow = HALO_RADII.map(
    (radius) => `0 0 ${radius * ratio * glowStrength}px ${style.neonColor}`,
  ).join(", ");

  return (
    <span
      style={{
        display: "inline-block",
        whiteSpace: "pre",
        color: active ? "#FFFFFF" : style.idleColor,
        opacity: active ? 1 : style.idleOpacity,
        textShadow: active
          ? shadow
          : // Les mots eteints gardent un contour sombre pour rester lisibles
            // sur une image claire.
            "0 2px 8px rgba(0,0,0,0.85)",
        transform: `scale(${scale})`,
        transition: "none",
        willChange: "transform, text-shadow",
      }}
    >
      {text}
    </span>
  );
};
