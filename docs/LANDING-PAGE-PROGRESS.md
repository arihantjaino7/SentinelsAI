# Landing page — progress and handoff

> Written so a fresh chat (after clearing this one) can pick up exactly
> where this one left off, with zero re-derivation. Not part of
> `docs/PLAN-v3.md`'s R1-R12 GitHub-scanning plan — this is the separate
> hero/landing-page UI work, referenced from R11's status note there.

## Where things stand

**Done, approved by Arihant:** the hero — wordmark, tagline, puzzle
assembly — through the point the puzzle finishes assembling and the page
releases into normal scroll. His words: *"I am liking till the puzzle part
is ending."*

**Done, built against a measured reference:** the section after the puzzle.
The plain "Start an inspection" form is gone; it is now a two-card chooser —
GitHub Repository / Website URL. The GitHub card locks in and navigates to
`/repo` ("Coming soon"), because the repo launcher UI doesn't exist yet.
See `docs/learning/44-scan-type-chooser.md`.

Built twice. The first pass worked from Arihant's written brief and came out
generic (rounded corners, blur, parallax, coloured glow — none of which the
reference does). The second pass took a screen recording of
**hollywoodexhibit2026.com** apart with `ffmpeg` and sampled real values.
**Do not re-tune this section by eye** — the numbers below are measured, and
they are all in `motion.ts` / `choices.ts`:

| | measured |
|---|---|
| resting background | `#000000` flat, no gradient anywhere |
| left card hovered | bg `#252525`, text `#848080` |
| right card hovered | bg `#E3E3E3`, text `#686868` |
| card | 3:4, square corners, 19.3% of viewport wide |
| card travel on hover | **both** cards move toward each other, 19.7% of a card's own width |
| hovered / dimmed scale | 1.10 / 0.82, loser washed with the active bg at 0.62 |
| headline | `Scan` / `GitHub`\|`Website`; line one enters from the left, line two from the right, ~5vw, **in front of** the cards (`z-30`, `pointer-events-none`) |

Artwork lives at `frontend/public/card-*.jpg` — 600x800 (3:4, matching the
card box), desaturated so no colour cast survives. **Give a replacement a new
filename**; `next/image` caches by URL, so overwriting in place serves the old
picture through server restarts and forced reloads alike.

The URL is typed in a **dialog** (`ScanDialog`), not in a panel under the
cards. Both cards hand off on click — GitHub to `/repo`, Website to the
dialog — so this section never changes height.

**Not started:** nothing queued on the landing page. Next landing-page work
is whatever Arihant asks for.

## Files involved

| File | Role |
|---|---|
| `frontend/components/landing/HeroPuzzle.tsx` | The whole hero timeline: wordmark scale, tagline travel, opener float, puzzle assembly. Almost all tuning happens here. |
| `frontend/app/page.tsx` | Landing page composition. Passes the wordmark+tagline JSX into `HeroPuzzle` as `header`, renders `<ScanTypeSelect />` below it. |
| `frontend/components/landing/scan-select/` | The chooser. `choices.ts` (the two options as data — **swap an image path here, nothing else moves**), `motion.ts` (every measured spring/curve/distance), `ScanChoiceCard.tsx`, `ScanHeadline.tsx`, `ScanTypeSelect.tsx`. |
| `frontend/app/repo/page.tsx` | "Coming soon" — where the GitHub card lands. Replace this file when the repo launcher is built; the card already points here. |
| `frontend/app/url/page.tsx` | Standalone `/url` launcher — now just copy + `<ScanLauncher>`. Untouched by the chooser work. |
| `frontend/components/ScanLauncher.tsx` | The actual scan form (input, submit, streaming progress, error state, navigate-to-report). Shared by the chooser and `/url` — it was **extended, not forked**: two optional props (`label`, `placeholder`) that `/url` doesn't pass, so `/url` renders exactly as before. |
| `frontend/components/landing/{SplitText,SmoothScroll,ScrollCursor}.tsx` | Supporting pieces, untouched this round. |
| `frontend/app/layout.tsx` | Adds the Space Grotesk font (`font-geo`) for the landing wordmark only. |
| `frontend/app/globals.css` | `--color-ink` darkened to `#070706`; landing-only motion keyframes/utilities (`rise-in`, `fade-in-up`, `hero-settle`, `hero-float`). |

## Reference site

**https://produx.design** — the puzzle mechanic is modeled on this, via
live DOM measurement (not eyeballing a video). Key measured facts:

- Tile grid: **7 columns × 4 rows = 28 tiles** (`background-size: 700% 400%`)
- Start transform: scale `0.2`, `translateZ(-1000px)`, `perspective: 1200px`,
  `blur(40px)`, **no rotation** (pure scale, both off-diagonal matrix terms zero)
- Scroll runway: 4680px sticky wrapper / 803px hero = **5.83× viewport
  height**. Ours: `560vh` ≈ 5.6×.

## The sequence, as specced and verified

1. **On load:** "Sentinels" wordmark huge, top-left. Tagline "AI-Powered
   Autonomous Website Security Auditor" sits at the bottom-left, ~48px inset.
2. **Act One** (hero timeline `0 → 0.18`, i.e. `ACT_ONE_END`): wordmark
   shrinks to logo size (final scale `0.16`/`0.20`/`0.28` by breakpoint)
   **while** the tagline flies up to rest just under it. Both tweens start
   at position `0`, share `duration: ACT_ONE_END`, both `ease: "none"`
   (linear) — this is what makes "no delay, same start, same end" actually
   true frame-by-frame, not just at the endpoints. Verified: 60.89% /
   60.89% complete mid-flight, drift 0.003 percentage points.
3. **The instant Act One ends**, the first puzzle pieces appear — not a
   blank beat. 4 openers (`OPENER_COUNT`), staggered `0.02` apart
   (`OPENER_STAGGER`), drift in from far depth and **hold in mid-air**
   rather than assembling immediately.
4. **Tagline exits** (`TAGLINE_EXIT_AT = 0.38`, scrolls up + fades) while
   the openers are still hovering.
5. **The remaining 24 tiles assemble** via an accelerating arrival curve
   (`place ** ARRIVAL_CURVE`, currently `0.55`); the 4 openers are released
   from their hover into final position too. Grid fills `GRID_FILL = 0.92`
   of available height — lands at roughly 70–76% of viewport *width* on
   tall screens (900px+); shorter viewports are geometrically capped lower,
   see the comment above `GRID_FILL` in the component.
6. **After full assembly** (timeline `1.0`, all 28 tiles settled, zero
   blur), the pinned hero releases into a normal-scrolling section with the
   working scan form. Verified end-to-end: submitting a real URL through it
   hits `POST /scan/stream` and navigates to a real `/scan/{id}` report.

## Tuning already applied (most recent pass)

- Grid fill `0.84 → 0.92` (puzzle reads bigger).
- **The "black screen" fix**, which was a visibility problem, not a timing
  one — the pieces already started on cue, they just weren't legible yet:
  - Opacity split into its own tween that completes in `OPENER_FADE_IN =
    0.22` of the travel, instead of riding the whole travel tween.
  - Opener start depth brought forward: `2000–2600px → 1700–2200px`, scale
    `0.08–0.16 → 0.13–0.20`. First piece now measures **14×16px at 47%
    opacity** the instant Act One ends (was ~4px, functionally invisible).
- Slightly faster: stagger `0.03 → 0.02`, float travel `0.10 → 0.085`.
- Tagline size raised **three times** on request:
  `text-sm/base → text-base/lg → text-lg/xl → text-xl/2xl`. Final: **20px
  mobile / 24px sm+**, confirmed still one line, still fully on screen,
  Act One sync still locked at this size.
- Removed the "PASSIVE BY DESIGN" eyebrow line entirely — no use for it.

## Key tunable constants (all in `HeroPuzzle.tsx`)

```
ACT_ONE_END = 0.18          wordmark+tagline sync window
OPENER_COUNT = 4
FLOAT_START = ACT_ONE_END
OPENER_STAGGER = 0.02
FLOAT_TRAVEL = 0.085
OPENER_FADE_IN = 0.22       fraction of travel spent fading in (not all of it)
TAGLINE_EXIT_AT = 0.38
TAGLINE_EXIT_DURATION = 0.1
ASSEMBLY_START = 0.46
CROWD_LAST_START = 0.84     last tile STARTS here; +duration lands it at 1.0
ARRIVAL_CURVE = 0.55        exponent controlling acceleration of arrivals
GRID_FILL = 0.92
runway = 560vh
```

If asked to tune further: change constants, don't restructure the timeline
— the shape (Act One lock, float-then-assemble, accelerating arrival
curve) is deliberate and was reverse-engineered from produx.design's own
DOM, not guessed.

## Known environment caveats (not app bugs)

- **Screenshots aren't available in this Browser pane** — it's not
  displayed, so nothing composites. Verification here was done via direct
  DOM/JS measurement (`getComputedStyle`, `DOMMatrix` on transforms) instead
  — more precise for motion timing than a screenshot anyway, but the
  "feel" should still be eyeballed by Arihant himself.
- **Lenis owns scroll.** Scripting `window.scrollTo()` for testing doesn't
  fire the event that drives `ScrollTrigger.update` — dispatch a plain
  `scroll` event manually after. Ordinary user scrolling doesn't have this
  issue; it's purely a browser-automation quirk.
- A stale/orphaned `uvicorn --reload` worker has bitten a previous session
  on this project (serves old code on the expected port after file edits).
  Not relevant to frontend work, but worth remembering if `npm run dev`
  ever seems to be serving stale JS after a big edit — check for a second
  process on port 3000.
