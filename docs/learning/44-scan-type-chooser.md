# 44 — The scan-type chooser

> **Status:** done. The landing page's plain "paste a URL" section is now a
> two-card chooser, built as a close match to the reference site
> (hollywoodexhibit2026.com) rather than an impression of it — every colour,
> distance and duration below was measured out of a screen recording of it,
> frame by frame. Website reveals the real scan input; GitHub locks in, then
> lands on `/repo` saying "Coming soon."
> Frontend only. No backend file, API route or scanning rule was touched.

## What we built

| File | Role |
|---|---|
| `components/landing/scan-select/choices.ts` | The two options as data — copy, image path, theme colours, where a click goes. **Swap an image here and nothing else moves.** |
| `components/landing/scan-select/motion.ts` | Every spring, curve and distance, defined once. |
| `components/landing/scan-select/ScanChoiceCard.tsx` | One card. |
| `components/landing/scan-select/ScanHeadline.tsx` | The big two-line headline — `Scan` over `GitHub` / `Website`. |
| `components/landing/scan-select/ScanDialog.tsx` | The "enter a URL" modal, which becomes the scanning view. |
| `components/landing/scan-select/ScanTypeSelect.tsx` | Owns the state, composes the rest. |
| `app/repo/page.tsx` | The "Coming soon" page the GitHub card leads to. |
| `components/ScanLauncher.tsx` | Three new **optional** props (`label`, `placeholder`, `submitLabel`). `/url` passes none and is unchanged. |

New dependency: `motion` — this is Framer Motion; the package was renamed
from `framer-motion` at v12, so the import is `from "motion/react"`.

## The one idea worth naming: measure the reference, don't eyeball it

The first version of this section was built from a written description. It
had rounded corners, a blur on the losing card, a parallax drift, a coloured
glow — all reasonable-sounding "premium hover" ideas, and all things the
reference does not do.

So the second version started by taking the reference apart. The screen
recording was 10s at 60fps; `ffmpeg` cut it into stills, and then each still
was read for real numbers:

```bash
# one still every 1/15th of a second, cropped past the browser chrome
ffmpeg -ss 5.25 -t 0.80 -i recording.mp4 \
  -vf "fps=15,crop=1920:820:0:120,scale=1000:-1" frames/r%02d.jpg
```

Then the colours were sampled straight out of the pixels rather than guessed
from looking:

| | measured |
|---|---|
| resting background | `#000000` — flat black, no gradient |
| left card hovered | background `#252525`, text `#848080` |
| right card hovered | background `#E3E3E3`, text `#686868` |
| card aspect | 193 x 255 → **3:4**, square corners |
| card width | 19.3% of viewport |
| how far a card travels | 38px on a 193px card → **19.7% of its own width** |
| hovered / dimmed scale | **1.10** / **0.82** |
| headline travel | ~55px on a 1000px viewport → **5vw** |

Almost every one of those numbers is a surprise if you only watched the
video. "Both cards move toward each other" is the big one — it *looks* like
only the hovered card moves, but the losing card's left edge sits 38px to the
right of where a pure scale-down would put it. That single detail is what
makes the pair read as closing ranks around a choice.

### Tiny standalone example: percentages of yourself

The travel distance is written as a percentage, and that's the trick worth
keeping:

```js
// `x: "20%"` in a transform means 20% of the ELEMENT'S OWN width,
// not 20% of its parent. So one number stays right at every size:
const card = { width: 193 }; console.log(193 * 0.20);  // 38 on desktop
const phone = { width: 142 }; console.log(142 * 0.20); // 28 on a phone
```

The cards are 38vw wide on a phone and 19vw on a desktop. Written in px or
vw, the travel would need one value per breakpoint and they'd drift apart.
Written as `20%`, there is one value forever.

## The signature move: two lines that converge

The headline is `Scan` over `GitHub` / `Website`. The two lines do **not** arrive
together:

- **line one enters from the left**, moving right
- **line two enters from the right**, moving left

They converge on their final positions while fading up. That's what "the text
coming from the left and right" means, and it's visible in the frames: across
the transition line one's left edge moved `+55px` while line two's moved
`−55px`. It only reads as a convergence while each line is a **single word** —
which is why the copy is `Scan` / `GitHub` and not `Welcome to GitHub
Repository`.

The headline sits **in front of** the cards (`z-30` against their `z-10`),
its inner end crossing over the photograph. The reference tucks its headline
*behind* the cover instead, and the first build copied that — but the card
swallowed whole words, so the overlap became a deliberate editorial one
rather than an occlusion. The layer keeps `pointer-events: none`, or an
invisible box over the cards would break the hover hand-off it's describing.

## Three bugs the browser found that reading the code wouldn't

**1. Tailwind silently read a font-size as a colour.** `text-[var(--headline)]`
compiled, looked fine, and rendered at the inherited 16px instead of 89px —
Tailwind can't tell whether `text-[…]` means size or colour when the value is
a variable, and picks colour. The fix is to say so: `text-[length:var(--headline)]`.

**2. The two photographs sat at different heights.** The GitHub card carries a
second caption line ("Coming soon") that the Website card doesn't, so its
button was taller, and a `flex … items-center` row centres each item
separately. Measured: card tops at 5307 and 5318. Fixed by taking the caption
out of flow, which also made the stage's midpoint the *card's* midpoint —
which is the line the headline measures from.

The caption then moved again, onto the picture itself. Where it sits in the
stack matters more than where it sits on screen: it is layered **above the
image but below the veil**, so a dimmed card's caption bleaches or sinks
along with its artwork instead of staying stubbornly crisp on a card that is
supposed to be receding. One rule dims the whole object, and the type can
stay a plain light neutral instead of being recoloured per theme.

**3. The headline was anchored to the wrong box.** It was positioned `58vw`
from the section's edge, but the section carries `px-[5vw]`, so that was 58vw
from the *padding box*, not the viewport — right at one window size, drifting
at every other. Rewritten to measure from `50%`, the centre line, which
padding cannot move.

## Where the URL gets typed: a dialog, not a panel

The first build revealed the input *underneath* the cards. That put the one
remaining action at the bottom of a full-height section — below the fold on a
short window, and visually subordinate to artwork the user had already
finished with.

It's a dialog now, and the shape came out cleaner than the panel did. Both
cards do the same *kind* of thing when clicked: hand off to somewhere the
choice gets acted on. GitHub hands off to a route (`/repo`); Website hands
off to `ScanDialog`. Neither makes the section grow — verified, the section's
height is byte-identical before and after a card is picked, because the
dialog is `position: fixed` and escapes the section's box entirely.

**The dialog wraps `ScanLauncher` rather than reimplementing it.** That
component already owns the streaming scan, the per-agent progress list, the
error state and the navigation to `/scan/{id}` — and `/url` uses the same one.
Forking it to get different chrome around it is exactly how two copies start
drifting. So the dialog supplies the frame and nothing else. Press **Next**
and `ScanLauncher` swaps its own form for `ScanProgress` *in place*, which is
what turns the dialog into the scanning view instead of something sitting on
top of one.

Verified end to end: `example.com` through the dialog → 5 live agent panels →
`/scan/dac1fcc3-…` showing a real F, 54/100, in 1064ms.

### A dialog has obligations a styled `<div>` doesn't

All of these are things you only notice when they're missing:

- **Escape closes it**, and the listener is removed on unmount.
- **Focus moves to the field on open** so you can just start typing, and
  returns to the card that opened it on close — otherwise a keyboard user is
  dumped at the top of the document with no idea where they were.
- **The scrim is a sibling of the panel, not its parent.** As a parent, every
  click inside the panel would bubble out to it and close the dialog
  mid-typing.
- **Body scroll is locked** while it's open — the page behind is a 560vh
  pinned hero, and scrolling it under a fixed dialog is disorienting.
- **Closing clears the selection.** Not cosmetic: leaving `selected === "url"`
  would make the next click on that card a no-op, since the state wouldn't
  change and the dialog would never reopen. Verified open → Escape → reopen.

## One call I made that departs from the reference

**GitHub goes to a real route, not a dialog.** `/repo` is the path
`docs/PLAN-v3.md` R11 already reserved for the repository launcher. When that
launcher is built it replaces `app/repo/page.tsx` and the card needs no
change.

## Try it

```bash
cd frontend && npm run dev
```

Scroll to the bottom of `/`, past the puzzle.

- Nothing hovered: **pure black**, two square-cornered cards, a small prompt.
- Hover **GitHub**: page goes dark grey, both cards close toward each other,
  GitHub grows and comes forward, Website is washed over with the new
  background colour, and `Scan / GitHub` converges in at the **bottom**.
- Hover **Website**: same choreography, but the page goes near-white and the
  headline arrives at the **top**. Crossing between the two should feel like
  one continuous hand-off, not two effects firing.
- **Tab** to a card instead of hovering — identical choreography, plus a
  focus outline in the theme's own text colour.
- Click **Website** → a dialog opens with the field already focused. Type an
  address, press **Next**, and the dialog itself becomes the scanning view
  (five live agent panels) before landing on `/scan/{id}`.
- Press **Escape**, or click the scrim, to back out — the card un-selects, and
  clicking it again reopens the dialog.
- Click **GitHub** → the card locks in, then `/repo`: "Coming soon."
- Turn animations off (Settings → Accessibility → Visual effects): cards jump
  straight to position, the headline cross-fades without travelling.

## Words worth knowing

- **Damping ratio** — `damping / (2·√(stiffness·mass))`. Below 1 overshoots,
  above 1 doesn't. Ours is 1.34, which is how "no bounce" becomes something
  you can check rather than something you hope for.
- **Overlapping `AnimatePresence`** — the default mode runs the outgoing
  element's exit and the incoming element's entrance *at the same time*.
  `mode="wait"` queues them, and the stall reads as lag.
- **A variant's own `transition` wins.** That's why reduced motion had to be
  handled *inside* `headlineVariants(...)` — a `transition` prop on the
  element would have been silently ignored.
- **`z-index` is set, not animated.** It has no in-between values, and the
  focused card has to be on top for the whole of its travel, not from the
  halfway point.

---

**Next:** `/repo` is a real route holding a real name — when the repository
launcher is built it replaces that file, and the landing page already points
there.
