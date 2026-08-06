/* Word-by-word masked reveal — the landing page's signature motion.

   Each word is wrapped in an `overflow-hidden` box with the word itself
   starting fully below it, then rising into view. The clipping is what
   makes this read as premium: the word is *uncovered*, not flown in from
   off-screen, so nothing ever appears outside the line it belongs to.

   Deliberately a pure-CSS animation rather than JS-driven. It costs no
   JavaScript, starts painting the instant the element exists (no waiting
   for hydration or an effect to fire), and can't desync the way a rAF loop
   can under load. The stagger is just a per-word `animation-delay` handed
   in through a CSS custom property.

   No "use client" — this renders identically on the server, so it stays a
   server component and ships zero JS. */

import { Fragment } from "react";

type SplitTextProps = {
  /** The line to animate. Split on spaces; each word animates separately. */
  text: string;
  /** Milliseconds before the first word starts. */
  delay?: number;
  /** Milliseconds added per word — the stagger itself. */
  stagger?: number;
  className?: string;
};

export function SplitText({
  text,
  delay = 0,
  stagger = 70,
  className = "",
}: SplitTextProps) {
  const words = text.split(" ");

  return (
    <span className={className}>
      {words.map((word, index) => (
        <Fragment key={`${word}-${index}`}>
          {/* The mask. `inline-block` is required — an inline box won't clip
              a transformed child at all.

              The padding/negative-margin pair is not decoration: `overflow:
              hidden` cuts exactly at the box edge, which would shear the
              descenders off letters like g, y, and the p in "Powered". The
              padding gives those tails somewhere to live; the equal negative
              margin takes the space back so line spacing is unaffected. */}
          <span className="inline-block overflow-hidden pb-[0.14em] -mb-[0.14em] align-bottom">
            <span
              className="rise-in inline-block"
              style={
                {
                  "--rise-delay": `${delay + index * stagger}ms`,
                } as React.CSSProperties
              }
            >
              {word}
            </span>
          </span>
          {/* The space lives OUTSIDE the mask. Inside, it would be clipped
              and every word would run into the next one. Outside, it also
              lets the browser wrap lines normally. */}
          {index < words.length - 1 ? " " : null}
        </Fragment>
      ))}
    </span>
  );
}
