"use client";

/* The scan-type chooser — pick an engine, then use it.

   Rebuilt against a frame-by-frame reading of the reference recording rather
   than against a description of it. The measurements live in `motion.ts` and
   `choices.ts`; this file is the state and the composition.

   THREE PIECES OF STATE:

     hovered   which card the pointer (or keyboard focus) is on right now
     selected  which card has been clicked and locked in
     leaving   a navigation is in flight

   and one derived value that does most of the work:

     focused = hovered ?? selected

   Hovering always wins, because a pointer is a live intention. When the
   pointer leaves it falls back to whatever was chosen, so the page keeps its
   colour and the selected card keeps its emphasis instead of blanking out.

   WHERE THE URL GETS TYPED. In a dialog (`ScanDialog`), not in this section.
   An earlier build revealed the field underneath the cards, which buried the
   one remaining action at the bottom of a full-height section. Both cards now
   do the same kind of thing when clicked — hand off to somewhere the choice
   is acted on. GitHub hands off to a route (`/repo`); Website hands off to
   the dialog. Neither one makes this section grow. */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { RESTING_THEME, SCAN_CHOICES, type ScanChoiceId } from "./choices";
import { ScanChoiceCard, type CardState } from "./ScanChoiceCard";
import { ScanDialog } from "./ScanDialog";
import { ScanHeadline } from "./ScanHeadline";
import { promptVariants, THEME_FADE } from "./motion";

/* How long the lock-in gets to land before a card that leads somewhere else
   actually navigates. Roughly one card-spring settle — long enough to see
   the page take the card's colour, short enough that it never feels like the
   click didn't register. */
const LOCK_IN_BEFORE_NAVIGATE_MS = 520;

export function ScanTypeSelect() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();

  const [hovered, setHovered] = useState<ScanChoiceId | null>(null);
  const [selected, setSelected] = useState<ScanChoiceId | null>(null);
  const [leaving, setLeaving] = useState(false);

  const navigationTimer = useRef<number | null>(null);
  useEffect(() => {
    // A pending timer would call `push` on a dead component if the user
    // navigates away by some other route first.
    return () => {
      if (navigationTimer.current !== null) {
        window.clearTimeout(navigationTimer.current);
      }
    };
  }, []);

  const dialogOpen = selected === "url" && !leaving;
  const focused = hovered ?? selected;
  const focusedChoice = SCAN_CHOICES.find((choice) => choice.id === focused);
  const theme = focusedChoice?.theme ?? RESTING_THEME;

  function handleSelect(id: ScanChoiceId) {
    const choice = SCAN_CHOICES.find((c) => c.id === id);
    if (!choice) return;

    setSelected(id);

    // A card with an `href` isn't an inline mode — it's a door. Let the
    // lock-in play on the card the user just clicked, then go. A card
    // without one opens the dialog, which `dialogOpen` derives from
    // `selected` directly rather than tracking as its own boolean — two
    // flags for one fact is how they end up disagreeing.
    if (choice.href) {
      setLeaving(true);
      navigationTimer.current = window.setTimeout(
        () => router.push(choice.href as string),
        reduceMotion ? 0 : LOCK_IN_BEFORE_NAVIGATE_MS,
      );
    }
  }

  /* Closing without scanning clears the selection too. Leaving the card
     locked in would claim a choice the user just backed out of, and the
     next click on that same card would then be a no-op — `selected` would
     already be "url", so nothing would change and the dialog would never
     reopen. */
  function handleDialogClose() {
    setSelected(null);
  }

  function cardState(id: ScanChoiceId): CardState {
    if (focused === null) return "idle";
    return focused === id ? "focused" : "dimmed";
  }

  return (
    <motion.section
      aria-label="Choose a scan type"
      animate={{ backgroundColor: theme.background }}
      transition={reduceMotion ? { duration: 0 } : THEME_FADE}
      /* EVERY LENGTH IN THIS SECTION DERIVES FROM `--card-w`.

         Card width, the gap between the pair, the headline size, how far the
         headline sits off the centre line — all of it is written as a
         multiple of this one custom property, so a breakpoint changes one
         number and the whole composition rescales in proportion. Measured
         off the reference at 19.3% of viewport width; phones need the cards
         much larger in relative terms or they become postage stamps.

         `--headline` is separate because type doesn't scale linearly with
         layout — 6.2vw is right on a desktop and far too small on a phone. */
      /* `bg-black` is the base the class system paints, and motion's inline
         `background-color` overrides it from the first frame onward. Without
         it the section is transparent until hydration runs, which shows as a
         flash of the page's warm `--color-ink` before it snaps to true
         black — and it is also what a reduced-motion or no-JS visitor sees. */
      className="relative flex min-h-screen flex-col items-center justify-center
                 overflow-hidden bg-black px-[5vw] py-24
                 [--card-w:38vw] [--headline:11vw] [--headline-out:0.05]
                 sm:[--card-w:26vw] sm:[--headline:8vw] sm:[--headline-out:0.35]
                 lg:[--card-w:19vw] lg:[--headline:6.2vw] lg:[--headline-out:0.55]"
    >
      {/* THE PROMPT. Present only while nothing has focus — the moment a card
          takes over, the headline is the answer to the question this was
          asking, so it gets out of the way. */}
      <AnimatePresence>
        {!focusedChoice && (
          <motion.p
            key="prompt"
            variants={promptVariants}
            initial="enter"
            animate="settled"
            exit="leave"
            style={{ color: theme.text }}
            className="absolute top-[12vh] px-6 text-center text-sm leading-relaxed sm:text-base"
          >
            Choose what you want
            <br />
            Sentinels to inspect
          </motion.p>
        )}
      </AnimatePresence>

      {/* THE STAGE. The headline layer and the card row share this box, which
          is what lets the headline position itself off the stage's centre
          line and land exactly on the card's edge. */}
      <div className="relative flex w-full items-center justify-center">
        {/* THE HEADLINE SITS IN FRONT OF THE CARDS, not behind them.

            The reference tucks it behind, and the first build copied that —
            but with our copy ("to GITHUB", "to WEBSITE") the card swallowed
            whole syllables and the line read as "WELCO… GITHUB" / "WELCOME
            … BSITE". The reference gets away with it because its second
            line is a single short word set well clear of the cover.

            `z-30` beats the card row's `z-10`, and `pointer-events-none`
            keeps the text from stealing the hover it is describing — an
            invisible box over the cards would break the hand-off the moment
            the pointer crossed it. */}
        <div className="pointer-events-none absolute inset-0 z-30">
          {/* Default (overlapping) `AnimatePresence` mode: the outgoing
              headline leaves while the incoming one arrives, so crossing
              between the two cards is one continuous movement. `mode="wait"`
              would queue them and the stall would read as lag. */}
          <AnimatePresence initial={false}>
            {focusedChoice && (
              <motion.div
                key={focusedChoice.id}
                className="absolute inset-0"
                style={{ color: theme.text }}
              >
                <ScanHeadline choice={focusedChoice} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* `role="radiogroup"` is the honest description: two mutually
            exclusive options, one of which ends up chosen. The cards are
            buttons rather than radio inputs because one of them navigates,
            and a radio that leaves the page is a lie. */}
        <div
          role="radiogroup"
          aria-label="Scan type"
          className="relative z-10 flex items-center justify-center
                     gap-[calc(var(--card-w)*0.26)]"
        >
          {SCAN_CHOICES.map((choice) => (
            <ScanChoiceCard
              key={choice.id}
              choice={choice}
              state={cardState(choice.id)}
              selected={selected === choice.id}
              theme={theme}
              onEnter={() => setHovered(choice.id)}
              onLeave={() =>
                // Only clear if this card is still the one being pointed at.
                // Crossing between the two fires the outgoing card's leave
                // AFTER the incoming card's enter, and clearing blindly would
                // blank the focus for a frame — which is exactly the flicker
                // that makes a hand-off look like two separate effects.
                setHovered((current) =>
                  current === choice.id ? null : current,
                )
              }
              onSelect={() => handleSelect(choice.id)}
            />
          ))}
        </div>
      </div>

      {/* THE INPUT, as a dialog over the top rather than a panel below.
          It renders inside this section but is `position: fixed`, so it
          escapes the section's own box and covers the viewport — which is
          why this section never changes height when a card is picked. */}
      <ScanDialog
        open={dialogOpen}
        onClose={handleDialogClose}
        label="Website URL"
        placeholder="https://example.com"
      />
    </motion.section>
  );
}
