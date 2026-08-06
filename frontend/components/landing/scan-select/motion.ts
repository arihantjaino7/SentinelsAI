/* The shared motion vocabulary for the scan-type chooser.

   Every spring, curve and distance in this section is defined here once. The
   numbers are not taste — they were measured off the reference recording
   (hollywoodexhibit2026.com) frame by frame at 15fps, and the comments say
   what was measured where. If a value needs tuning, tune it here; the
   components import, they never inline. */

import type { Transition, Variants } from "motion/react";

/* Expo-out. Fast off the mark, long settle — already the curve the rest of
   this landing page uses (see `rise-in` in globals.css). */
export const EXPO_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];

/* THE CARD SPRING.

   A spring is a simulation, not a duration: stiffness pulls toward the
   target, damping is friction, mass is inertia. Whether it overshoots is
   the damping ratio:

     ratio = damping / (2 * sqrt(stiffness * mass))
           = 32 / (2 * sqrt(220 * 0.65))
           = 1.34

   Above 1.0 is overdamped — it reaches the target and stops dead, never
   crossing it. That is "no bounce" stated where it can actually be
   guaranteed. It settles in roughly 300ms, and because it is a spring, a
   pointer that crosses between the two cards mid-flight gets a smooth
   reversal from the midpoint instead of a restart. */
export const CARD_SPRING: Transition = {
  type: "spring",
  stiffness: 220,
  damping: 32,
  mass: 0.65,
};

/* The background is a colour, not a position, so a spring buys nothing —
   colour has no momentum. A plain tween is the honest tool. Measured at
   roughly half a second in the reference: the wash is still visibly moving
   two frames after the cards have arrived. */
export const THEME_FADE: Transition = { duration: 0.5, ease: EXPO_OUT };

/* HOW FAR THE CARDS MOVE.

   Measured: at a 1000px-wide viewport the cards were 193px across and each
   one travelled 38px toward the centre — 19.7% of a card's own width.

   So the distance is expressed as a PERCENTAGE rather than in px or vw. A
   percentage on `x` is a percentage of the element's own width, which means
   this one number stays correct at every breakpoint even though the cards
   are 38vw wide on a phone and 19vw wide on a desktop. */
export const CONVERGE = 20;

/* Both cards move toward each other — the hovered one is not the only thing
   that travels. That is what makes the pair read as closing ranks around
   the choice rather than as one card wandering off. */
export const HOVER_SCALE = 1.1;
export const DIM_SCALE = 0.82;
/* How much of the active background colour is washed over the card that
   lost. On the light theme this bleaches it toward white, on the dark theme
   it sinks it into the background — one rule, both directions. */
export const DIM_VEIL = 0.62;

/* THE HEADLINE.

   The signature move. The two lines do NOT arrive together: line one comes
   in from the left, line two from the right, and they converge on their
   final positions while fading up. Measured at ~55px of travel on a 1000px
   viewport, hence 5vw — a vw distance rather than px so the gesture keeps
   its proportion on a large monitor.

   No blur, no scale, no letter-spacing. The reference does one thing here
   and it is this. */
export const HEADLINE_SLIDE = "5vw";

/* A factory rather than two constants, because the variants have to know
   about reduced motion. A variant's own `transition` beats anything the
   element sets, so a `transition={{duration:0}}` on the component would be
   silently ignored — the only place the preference can actually be honoured
   is inside the variant itself. Reduced motion keeps the cross-fade (an
   opacity change is not vestibular motion) and drops the travel. */
export function headlineVariants(
  line: "one" | "two",
  reduceMotion: boolean,
): Variants {
  const offset = reduceMotion
    ? "0vw"
    : line === "one"
      ? `-${HEADLINE_SLIDE}`
      : HEADLINE_SLIDE;

  return {
    enter: { opacity: 0, x: offset },
    settled: {
      opacity: 1,
      x: "0vw",
      transition: { duration: reduceMotion ? 0.2 : 0.55, ease: EXPO_OUT },
    },
    leave: {
      opacity: 0,
      x: offset,
      // Leaving is faster than arriving, so the outgoing headline is gone
      // before the incoming one is legible and the swap never smears.
      transition: { duration: reduceMotion ? 0.1 : 0.28, ease: "easeIn" },
    },
  };
}

/* The small prompt above the cards. It exists only while nothing is chosen —
   the moment a card takes focus, the headline is the answer to the question
   the prompt was asking, so the prompt gets out of the way. */
export const promptVariants: Variants = {
  enter: { opacity: 0 },
  settled: { opacity: 1, transition: { duration: 0.45, ease: EXPO_OUT } },
  leave: { opacity: 0, transition: { duration: 0.22, ease: "easeIn" } },
};

/* The dialog's own entrance lives in ScanDialog.tsx rather than here. It is
   the one piece of motion in this section that isn't shared between
   components, and inlining it keeps the scrim and the panel — which have to
   fade in together — readable side by side. */
