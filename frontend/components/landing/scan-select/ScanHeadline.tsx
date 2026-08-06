"use client";

/* The big two-line headline — "Scan" over "GitHub" / "Website".

   THE MOVE THIS FILE EXISTS FOR.

   The two lines do not enter together. Line one comes in from the LEFT and
   line two comes in from the RIGHT, and they converge on their final
   positions while fading up. That is the thing the reference does that a
   plain fade-and-rise doesn't, and it is what "the text coming from the left
   and right" describes. It only reads that way while each line is a single
   word — which is why `choices.ts` insists on keeping both short.

   WHERE IT SITS. Anchored to the card, not to the page:

     left card   bottom-aligned, right-aligned, unfurling LEFT
     right card  top-aligned,    left-aligned,  unfurling RIGHT

   and in both cases the inner end of the text crosses OVER the card, at
   `z-30` against the cards' `z-10`/`z-20`. The reference tucks its headline
   behind the cover instead; that ate whole words here, so the overlap became
   a deliberate editorial one — type printed across a photograph — rather
   than an occlusion. See the note in ScanTypeSelect.tsx. */

import { motion, useReducedMotion } from "motion/react";

import type { ScanChoice } from "./choices";
import { headlineVariants } from "./motion";

/* BOTH OFFSETS ARE MEASURED FROM THE CENTRE LINE, in card-widths.

   That is the fix for the first attempt, which anchored the headline to the
   section's edge with a vw distance. It looked right at one window size and
   drifted at every other, because the section carries `px-[5vw]` padding —
   so a "58vw from the right edge" offset was really 58vw from the padding
   box, not from the viewport. Measuring from `50%` sidesteps the padding
   entirely: the centre line is the centre line whatever the padding does.

   Vertical: measured off the reference at 1.27 card-half-heights above the
   centre, and a card is 4/3 as tall as it is wide, so 1.27 x (4/3) / 2 =
   0.85 card-widths.

   Horizontal: `--headline-out` card-widths out from centre, 0.55 on desktop
   to match the reference. It has to shrink on narrow screens — the headline
   is `whitespace-nowrap`, so on a phone the desktop offset walks most of the
   word off the left edge of the screen. The section drops it to 0.05 there,
   which parks the text almost centred behind the cards and keeps every
   letter on screen. */
const EDGE_FROM_CENTRE = "calc(50% - var(--card-w) * 0.85)";
const SIDE_FROM_CENTRE = "calc(50% + var(--card-w) * var(--headline-out))";

export function ScanHeadline({ choice }: { choice: ScanChoice }) {
  const onLeft = choice.side === "left";
  const reduceMotion = useReducedMotion() ?? false;

  return (
    <motion.div
      key={choice.id}
      aria-hidden
      initial="enter"
      animate="settled"
      exit="leave"
      style={
        onLeft
          ? { right: SIDE_FROM_CENTRE, bottom: EDGE_FROM_CENTRE }
          : { left: SIDE_FROM_CENTRE, top: EDGE_FROM_CENTRE }
      }
      className={`pointer-events-none absolute font-display uppercase leading-[0.92]
                  tracking-[0.01em] ${onLeft ? "text-right" : "text-left"}`}
    >
      {/* `whitespace-nowrap` on each line: these are positioned off one edge
          of the screen, so a wrap would push the text back across the card
          instead of doing anything useful. */}
      {/* `length:` is not decoration — without it Tailwind cannot tell whether
          `text-[…]` means font-size or colour, and silently picks colour.
          That is what made the headline render at the inherited 16px on the
          first pass. */}
      <motion.div
        variants={headlineVariants("one", reduceMotion)}
        className="whitespace-nowrap text-[length:var(--headline)]"
      >
        {choice.lineOne}
      </motion.div>

      <motion.div
        variants={headlineVariants("two", reduceMotion)}
        className="whitespace-nowrap text-[length:var(--headline)]"
      >
        {choice.lineTwo}
      </motion.div>
    </motion.div>
  );
}
