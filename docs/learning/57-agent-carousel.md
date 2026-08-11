# 57 — Agent carousel (sliding-effect branch)

> **Status:** built and logic-verified. This is an experiment on its own branch
> (`sliding-effect`), not yet on `main` — see [`AgentCarousel.tsx`](../../frontend/components/AgentCarousel.tsx).

## What we built

The report page used to show its 8 agents as `AgentReel` — a tall, scroll-driven
sequence where each agent got a full-width plate that widened as you scrolled past
it. We replaced it with `AgentCarousel`: a small, shallow arc of cards you drive with
arrows, dots, the keyboard, or a drag — nothing moves until you touch it. Click a card
and a popup opens over a blurred background with that agent's verdict, duration, top
issues, and a link to its full report. `AgentReel.tsx` is left on disk, unused, so
switching back is a two-line change, not a rebuild.

## New concepts

### Placing things on an arc: sin and cos turn an angle into a position

A computer screen only understands "how many pixels right" (`x`) and "how many
pixels down" (`y`). But the carousel thinks in *angles* — card 3 is a bit further
around the arc than card 2. `sin` and `cos` are the translation between the two:
given an angle, `sin(angle)` tells you the horizontal position and `cos(angle)` the
vertical position, as fractions between −1 and 1.

```python
import math

for hour in range(12):
    angle = (hour / 12) * 2 * math.pi        # 12 hours = one full circle
    x = math.sin(angle)                       # −1 (9 o'clock) .. 1 (3 o'clock)
    y = -math.cos(angle)                      # −1 (12 o'clock) .. 1 (6 o'clock)
    print(hour, round(x, 2), round(y, 2))
```

Run that and you've built a clock face's numbers, purely from `sin`/`cos` — no
image, no manual coordinates. The carousel does exactly this for each card, just
with a small angle range instead of a full circle:

```ts
const angle = (d / VISIBLE_COUNT) * Math.PI;   // d = the card's distance from centre
const x = Math.sin(angle) * radiusX;
const y = -Math.cos(angle) * radiusY;
```

`radiusX`/`radiusY` are just "how many pixels is 1.0" — the clock example above used
a radius of 1, ours uses however wide the carousel's track measures.

### The shortest way around a ring: signed modulo

Plain subtraction treats positions as a straight line. On a ring, that's wrong: the
distance from card 7 to card 0 (in an 8-card ring) should read as "1 step forward",
not "7 steps back" — the same way 11 o'clock is *one hour before* midnight, not
*eleven hours after* it.

```python
def hours_until(now, target, hours_on_clock=12):
    diff = (target - now) % hours_on_clock      # 0 .. 11, always positive
    if diff > hours_on_clock / 2:
        diff -= hours_on_clock                  # fold the long way onto the short way
    return diff

print(hours_until(11, 0))   # 1  — not -11 or 11
print(hours_until(2, 10))   # -4 — 10 is 4 hours *before* 2, going backwards
```

Without that fold, the original reference snippet showed **7 of 8 cards crammed onto
one side** instead of 5 spread evenly — the bug this fixes. Our version:

```ts
let d = (((index - activeIndex) % total) + total) % total; // 0 … total-1, always positive
if (d > total / 2) d -= total;                              // fold onto the short way round
```

(The extra `(x % n + n) % n` dance is just because JavaScript's `%` can return a
*negative* remainder for a negative input, unlike Python's — so `-1 % 8` is `-1` in
JS, not `7`. Adding `n` before the final `% n` forces it positive first.)

### Watching an element's size: `ResizeObserver`

The reference snippet hardcoded `RADIUS_X = 220` pixels — fine on a laptop, but wider
than an entire phone screen. `ResizeObserver` is the browser telling you, live,
whenever an element's box changes size — no polling, no `resize` event on the whole
window:

```html
<div id="box" style="width: 50%; resize: horizontal; overflow: auto"></div>
<script>
  const box = document.getElementById("box");
  new ResizeObserver((entries) => {
    console.log("box is now", entries[0].contentRect.width, "px wide");
  }).observe(box);
</script>
```

Drag that box's corner and the console logs every step. We use the same thing on the
carousel's own track: its measured width becomes the input to `radiusX`, clamped
between a minimum and maximum, so a phone-width track gets a phone-width ring
instead of a 220px-radius ring that runs off the edge.

### `AnimatePresence`: animating things *out*, not just in

Normally when React stops rendering something, it's just gone — no chance to fade
it out first. `AnimatePresence` (from the `motion` library) delays the actual
removal until an `exit` animation finishes:

```jsx
import { AnimatePresence, motion } from "motion/react";

function List({ items }) {
  return (
    <AnimatePresence>
      {items.map((item) => (
        <motion.li key={item.id} exit={{ opacity: 0 }}>
          {item.text}
        </motion.li>
      ))}
    </AnimatePresence>
  );
}
```

Delete an item from `items` and its `<li>` fades out before disappearing, instead of
snapping away. The important part is the `key` — that's how `AnimatePresence`
recognises "this specific one is now missing" across two renders. Our cards use the
same trick, except instead of removing an item from an array, we make an *individual*
card's slot return `null` once it rotates outside the visible window — `AnimatePresence`
still notices that key vanished and plays its exit animation before it actually
leaves the DOM.

## The actual code

**`frontend/components/AgentCarousel.tsx`** — `ringPosition()` is the geometry
function above (shortest-arc `d`, then `sin`/`cos` into `x`/`y`), plus a fade/scale
by distance from centre so cards further from the active one sit smaller and dimmer.
A `ResizeObserver` effect keeps `radius` in sync with the track's actual measured
width. `goTo`/`next`/`prev` all funnel through one modulo wrap, which is also what
lets `safeIndex` self-correct if a re-scan ever changes how many agents come back —
no separate effect-plus-setState needed to "fix" an out-of-range index (an earlier
draft had exactly that, and the lint rule `react-hooks/set-state-in-effect` caught it:
computing the safe value on every render is simpler than reacting to it being wrong).

**`frontend/components/AgentPeekDialog.tsx`** — deliberately *not* a new pattern.
`components/landing/scan-select/ScanDialog.tsx` already solves the scrim, the blur,
Escape-to-close, returning focus to whatever was clicked, and locking page scroll
while open. Copying that structure (scrim as a sibling `<button>`, not a parent, so a
click inside the panel can't bubble out and close it) means one dialog behaviour to
maintain, not two that can drift apart.

## Try this

- In `ringPosition`, change `VISIBLE_COUNT` from `5` to `3` and reload — fewer cards
  visible at once, and `HALF` (which is `Math.floor(VISIBLE_COUNT / 2)`) drops to `1`.
- Comment out the `if (d > total / 2) d -= total;` line and scan a site — watch the
  cards bunch up on one side again, the exact bug this fixes.
- In the browser console on a report page, run
  `document.querySelectorAll('[aria-label="Agents"] button[aria-label*="—"]').length`
  right after clicking a dot — you'll sometimes see more than 5 briefly, because the
  card that just rotated out is still mid-`exit` animation, not gone yet.

## Words you now know

- **Polar vs. cartesian coordinates** — angle-and-distance vs. x-and-y; `sin`/`cos`
  convert one into the other.
- **Signed modulo / shortest-arc distance** — folding a ring's "long way round"
  distance onto the shorter one, the same idea a 12-hour clock uses.
- **`ResizeObserver`** — a browser API that reports an element's size changing,
  without polling.
- **`AnimatePresence`** — delays a component's removal from the DOM until its `exit`
  animation finishes; tracks which item is which by `key`.
