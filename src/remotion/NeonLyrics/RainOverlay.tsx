/**
 * Pluie — deux rendus au choix.
 *
 * `onScreen` (defaut) : les gouttes s'ecrasent SUR l'objectif. Elles
 *   apparaissent par un impact, restent collees a la vitre, deforment l'image
 *   derriere elles, et les plus grosses glissent en laissant une trainee.
 *   C'est l'effet "camera sous la pluie".
 *
 * `falling` : averse classique vue de loin, les gouttes traversent le champ
 *   de haut en bas.
 *
 * Dans les deux cas, tout est tire de `random()` de Remotion et jamais de
 * `Math.random()` : la position ne depend que du numero d'image, donc
 * n'importe quelle image peut etre calculee seule. C'est indispensable au
 * rendu multi-processus, sinon la pluie scintille au lieu de tomber.
 */
import React, { useMemo } from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame, useVideoConfig } from "remotion";
import type { Rain } from "../types.ts";

export const RainOverlay: React.FC<Rain> = (props) =>
  props.style === "falling" ? <FallingRain {...props} /> : <ScreenRain {...props} />;

// ------------------------------------------------------------------ ecran

/** Nombre de gouttes sur la vitre a intensite 1. */
const MAX_DROPLETS = 70;

/** Duree de l'impact, en secondes. */
const IMPACT_SEC = 0.12;

/** En dessous de ce rayon la goutte est trop legere pour glisser. */
const SLIDE_THRESHOLD_PX = 17;

const ScreenRain: React.FC<Rain> = ({ intensity, opacity }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const t = frame / fps;

  const count = Math.round(MAX_DROPLETS * intensity);

  // Chaque goutte a son propre cycle : elle nait, glisse, s'efface, puis
  // renait ailleurs. Le decalage evite que toutes apparaissent ensemble.
  const specs = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => ({
        periodSec: 3.5 + random(`drop-period-${i}`) * 5.5,
        offsetSec: random(`drop-offset-${i}`) * 9,
      })),
    [count],
  );

  return (
    <AbsoluteFill style={{ opacity, pointerEvents: "none", overflow: "hidden" }}>
      {specs.map((spec, i) => {
        const elapsed = t + spec.offsetSec;
        // La generation change a chaque cycle : la goutte renait ailleurs,
        // avec une nouvelle taille, sans jamais dependre de l'image d'avant.
        const generation = Math.floor(elapsed / spec.periodSec);
        const age = elapsed % spec.periodSec;
        const seed = `${i}-${generation}`;

        // Elevation au cube : beaucoup de fines gouttelettes, tres peu de
        // grosses. Une repartition uniforme donne une vitre uniformement
        // constellee de pastilles, ce qui ne ressemble a rien.
        const radius = 4 + random(`drop-r-${seed}`) ** 3 * 26;
        const xPct = random(`drop-x-${seed}`) * 100;
        const yPctBirth = random(`drop-y-${seed}`) * 100;

        const slideSpeed =
          radius > SLIDE_THRESHOLD_PX ? (radius - SLIDE_THRESHOLD_PX) * 2.4 : 0;
        const slideSec = Math.max(0, age - IMPACT_SEC);
        const slidePx = slideSpeed * slideSec;

        const yBirthPx = (yPctBirth / 100) * height;
        const yPx = yBirthPx + slidePx;
        if (yPx - radius > height) return null;

        // Impact : la goutte s'ecrase, donc elle depasse un instant sa
        // taille au repos avant de la retrouver.
        const pop = interpolate(age, [0, IMPACT_SEC * 0.55, IMPACT_SEC], [0, 1.35, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const fadeOut = interpolate(
          age,
          [spec.periodSec - 0.9, spec.periodSec],
          [1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        );

        const dropletOpacity = fadeOut;
        if (dropletOpacity <= 0.01) return null;

        return (
          <React.Fragment key={i}>
            {/* Trainee laissee par les grosses gouttes qui glissent. */}
            {slidePx > 4 ? (
              <div
                style={{
                  position: "absolute",
                  left: `${xPct}%`,
                  top: yBirthPx,
                  width: radius * 0.55,
                  height: slidePx,
                  marginLeft: -radius * 0.275,
                  opacity: dropletOpacity * 0.42,
                  background:
                    "linear-gradient(to bottom, rgba(255,255,255,0) 0%, rgba(255,255,255,0.1) 60%, rgba(255,255,255,0.2) 100%)",
                  backdropFilter: "blur(1.8px)",
                  borderRadius: radius,
                }}
              />
            ) : null}

            {/* Anneau d'impact, tres bref. */}
            {age < 0.35 ? (
              <div
                style={{
                  position: "absolute",
                  left: `${xPct}%`,
                  top: yPx,
                  width: radius * 2 * interpolate(age, [0, 0.35], [1, 2.6]),
                  height: radius * 2 * interpolate(age, [0, 0.35], [1, 2.6]),
                  transform: "translate(-50%, -50%)",
                  borderRadius: "50%",
                  border: "1.5px solid rgba(255,255,255,0.5)",
                  opacity: interpolate(age, [0, 0.35], [0.55, 0]),
                }}
              />
            ) : null}

            {/* La goutte elle-meme.
                Le flou d'arriere-plan fait la refraction : c'est lui qui
                donne l'impression que l'image est vue A TRAVERS la goutte.
                Volontairement AUCUNE ombre interne sombre : sur un plan
                nocturne elle transformerait la goutte en pastille grise. De
                l'eau ne se voit que par son lisere lumineux et par ce qu'elle
                deforme. */}
            <div
              style={{
                position: "absolute",
                left: `${xPct}%`,
                top: yPx,
                width: radius * 2,
                height: radius * 2.1,
                transform: `translate(-50%, -50%) scale(${pop})`,
                borderRadius: "50%",
                opacity: dropletOpacity,
                backdropFilter: `blur(${Math.max(1.5, radius * 0.24)}px) brightness(1.06)`,
                background:
                  "radial-gradient(circle at 34% 27%, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0.05) 30%, rgba(255,255,255,0) 56%)",
                boxShadow:
                  "inset 0 -1.5px 3px rgba(255,255,255,0.42), inset 0 1px 2px rgba(255,255,255,0.1)",
                border: "0.5px solid rgba(255,255,255,0.16)",
              }}
            />
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};

// ------------------------------------------------------------------ averse

const MAX_DROPS = 320;

const FallingRain: React.FC<Rain> = ({ intensity, angleDeg, opacity }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const count = Math.round(MAX_DROPS * intensity);

  const drops = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => ({
        // On deborde volontairement de -10% a +110% : apres rotation, les
        // coins du cadre doivent rester couverts.
        xPct: random(`rain-x-${i}`) * 120 - 10,
        lengthPx: 40 + random(`rain-len-${i}`) * 130,
        speedPxPerSec: 900 + random(`rain-speed-${i}`) * 1100,
        phase: random(`rain-phase-${i}`),
        thicknessPx: 1 + random(`rain-thick-${i}`) * 1.6,
        alpha: 0.2 + random(`rain-alpha-${i}`) * 0.8,
      })),
    [count],
  );

  const timeSec = frame / fps;

  return (
    <AbsoluteFill style={{ opacity, pointerEvents: "none", overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: "-20%",
          top: "-20%",
          width: "140%",
          height: "140%",
          transform: `rotate(${angleDeg}deg)`,
        }}
      >
        {drops.map((drop, i) => {
          const travel = height * 1.4 + drop.lengthPx;
          const y =
            ((timeSec * drop.speedPxPerSec + drop.phase * travel) % travel) -
            drop.lengthPx;

          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${drop.xPct}%`,
                top: 0,
                width: drop.thicknessPx,
                height: drop.lengthPx,
                transform: `translateY(${y}px)`,
                background: `linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,${drop.alpha}))`,
                borderRadius: drop.thicknessPx,
              }}
            />
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
