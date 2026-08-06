"use client";

/* One card in the chooser.

   Deliberately plain compared to what a "premium hover" usually reaches for.
   The reference does exactly four things to a card and nothing else:

     1. both cards slide toward each other, by the same distance
     2. the focused one scales up and comes to the front
     3. the other scales down and is washed over with the page's new
        background colour
     4. corners stay square; nothing blurs, tilts or drifts

   Everything that isn't on that list — parallax, a blur on the loser, a
   coloured glow, rounded corners — was in the first version of this file and
   has been taken out, because each one was a thing the reference doesn't do.
   The restraint is what makes it read as expensive. */

import Image from "next/image";
import { motion, useReducedMotion } from "motion/react";

import type { ScanChoice, Theme } from "./choices";
import { CARD_SPRING, CONVERGE, DIM_SCALE, DIM_VEIL, HOVER_SCALE } from "./motion";

export type CardState = "idle" | "focused" | "dimmed";

type ScanChoiceCardProps = {
  choice: ScanChoice;
  state: CardState;
  selected: boolean;
  /** The theme currently painting the section — the veil borrows its colour
      so the losing card sinks into whatever the page has just become. */
  theme: Theme;
  /** Pointer entered, or the card took keyboard focus — same signal. */
  onEnter: () => void;
  onLeave: () => void;
  onSelect: () => void;
};

export function ScanChoiceCard({
  choice,
  state,
  selected,
  theme,
  onEnter,
  onLeave,
  onSelect,
}: ScanChoiceCardProps) {
  const reduceMotion = useReducedMotion();

  const isIdle = state === "idle";
  const isFocused = state === "focused";

  /* Which way "toward the middle" is, for this card. The left card closes to
     the right and the right card closes to the left, so one constant serves
     both and the pair stays symmetrical by construction. */
  const inward = choice.side === "left" ? CONVERGE : -CONVERGE;

  return (
    <motion.button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-label={choice.ariaLabel}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      // Keyboard focus drives exactly the same state as the pointer, so
      // tabbing through the cards plays the whole choreography — the page
      // changes colour, the headline arrives. It isn't a mouse-only feature.
      onFocus={onEnter}
      onBlur={onLeave}
      onClick={onSelect}
      // `zIndex` is set rather than animated: it has no in-between values, and
      // the focused card must be on top for the whole of its travel, not from
      // the halfway point.
      style={{ zIndex: isFocused ? 20 : 10, outlineColor: theme.text }}
      animate={{
        x: isIdle ? "0%" : `${inward}%`,
        scale: isFocused ? HOVER_SCALE : isIdle ? 1 : DIM_SCALE,
      }}
      transition={reduceMotion ? { duration: 0 } : CARD_SPRING}
      className="group relative block cursor-pointer bg-transparent text-left
                 outline-none focus-visible:outline-2 focus-visible:outline-offset-[6px]"
    >
      {/* Square corners. No radius anywhere on this element or its children —
          that was an explicit requirement and it is also what the reference
          does: a magazine cover has corners, so does a photograph. */}
      <div className="relative aspect-[3/4] w-[var(--card-w)] overflow-hidden bg-black">
        <Image
          src={choice.image}
          alt={choice.imageAlt}
          fill
          sizes="(max-width: 640px) 40vw, (max-width: 1024px) 26vw, 19vw"
          className="object-cover"
        />

        {/* THE CAPTION, PRINTED ON THE PHOTOGRAPH.

            Inside the picture rather than under it, and deliberately ABOVE
            the image but BELOW the veil in this stack. That ordering is the
            whole trick: because the veil paints over the caption too, a
            dimmed card's caption bleaches or sinks along with its artwork
            instead of staying stubbornly crisp on a card that is supposed
            to be receding. One rule dims the whole object.

            Which also means the colour can just be a light neutral — the
            photograph underneath is dark in both cards, and the theme does
            its work through the veil rather than by recolouring the type. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 px-3 pb-4 text-center text-white/85">
          <p className="font-mono text-[10px] uppercase tracking-[0.28em]">
            {choice.title}
          </p>
          {choice.note && (
            <p className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.28em] opacity-60">
              {choice.note}
            </p>
          )}
        </div>

        {/* THE VEIL. One rectangle of the page's current background colour,
            faded in over the card that lost. On the light theme that bleaches
            it toward white; on the dark theme it sinks it into the black. The
            same rule produces both, which is why the two directions can never
            drift apart. */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          animate={{
            backgroundColor: theme.background,
            opacity: state === "dimmed" ? DIM_VEIL : 0,
          }}
          transition={reduceMotion ? { duration: 0 } : CARD_SPRING}
        />

        {/* The selected card keeps a hairline of the theme's text colour, so
            a locked-in choice still reads as chosen once the pointer has
            left and the emphasis has gone back to neutral. */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 border"
          animate={{ borderColor: theme.text, opacity: selected ? 0.75 : 0 }}
          transition={reduceMotion ? { duration: 0 } : CARD_SPRING}
        />
      </div>

    </motion.button>
  );
}
