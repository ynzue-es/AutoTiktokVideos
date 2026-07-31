/**
 * Un plan visuel et ses fondus.
 *
 * Le fondu au noir est obtenu en faisant simplement varier l'opacite du plan
 * au-dessus d'un fond noir : le plan sortant s'efface, le suivant apparait.
 * Chaque plan ne prend en charge que sa moitie de transition, ce qui evite
 * de decaler le montage.
 *
 * Le premier plan n'a pas de fondu d'entree et le dernier pas de fondu de
 * sortie : sur un format court, ouvrir ou fermer sur du noir gaspille des
 * dixiemes de seconde d'attention.
 */
import React from "react";
import { AbsoluteFill, interpolate, OffthreadVideo, Sequence, useCurrentFrame } from "remotion";

export const ClipSequence: React.FC<{
  readonly src: string;
  readonly from: number;
  readonly durationInFrames: number;
  readonly fadeFrames: number;
  readonly isFirst: boolean;
  readonly isLast: boolean;
}> = ({ src, from, durationInFrames, fadeFrames, isFirst, isLast }) => (
  <Sequence from={from} durationInFrames={durationInFrames}>
    <ClipBody
      src={src}
      durationInFrames={durationInFrames}
      fadeFrames={fadeFrames}
      isFirst={isFirst}
      isLast={isLast}
    />
  </Sequence>
);

const ClipBody: React.FC<{
  readonly src: string;
  readonly durationInFrames: number;
  readonly fadeFrames: number;
  readonly isFirst: boolean;
  readonly isLast: boolean;
}> = ({ src, durationInFrames, fadeFrames, isFirst, isLast }) => {
  const frame = useCurrentFrame();

  const fadeIn = isFirst
    ? 1
    : interpolate(frame, [0, fadeFrames], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });

  const fadeOut = isLast
    ? 1
    : interpolate(
        frame,
        [durationInFrames - fadeFrames, durationInFrames],
        [1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      );

  return (
    <AbsoluteFill style={{ opacity: fadeIn * fadeOut }}>
      <OffthreadVideo
        src={src}
        // Le son de la source a deja ete retire a l'etape 2 ; ce garde-fou
        // evite qu'un plan avec une piste residuelle ne vienne se melanger
        // a la musique.
        muted
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};
