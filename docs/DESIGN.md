# Frontend design direction

> **Status:** agreed with Arihant, 2026-07-29. Not yet built — this is the brief for
> A13-A15 (Act 4). Written down so the decision survives even if the conversation that
> produced it is cleared; this file, not chat history, is the source of truth.

## References considered

- [sondaven.com/en](https://sondaven.com/en) — Webflow + GSAP/Lenis/Barba, chaptered
  document structure, huge numbers as hero moments, tan/near-black palette, ~38
  screens of scroll.
- [izanami-official.com](https://izanami-official.com/) — hand-built, real WebGL
  shader glass distortion, near-black + serif type, ~11 screens.

**Verdict:** borrow structure and craft from both — chaptered/dossier layout, huge
numbers, glass panels drifting on scroll — not their literal palettes (green/tan read
wrong for security) and not Izanami's real WebGL (CSS `backdrop-filter` gets ~85% of
the look for a fraction of the build cost, and matches where Arihant is on the JS/React
learning curve). Not a 30+ screen scroll story either — Sentinels is a tool, not a
brochure; a user wants an answer in seconds, not a lingering read.

## Concept

An **inspection dossier**, not a hacker-aesthetic dashboard. Sentinels never attacks —
it reads headers, certificates, DNS records, `robots.txt` — and issues a letter grade.
The visual language is the official inspection notice / audit certificate, not
matrix-rain-and-neon-green (the templated default every competitor in this space uses).

## Palette — graphite dossier

| Role | Value | Notes |
|---|---|---|
| Background | `#0E0E0D` | warm near-black, not pure black |
| Text | `#D9D7D4` | warm off-white, never pure white |
| Glass panel fill | `rgba(255,255,255,0.04)` | + `backdrop-filter: blur(20px) saturate(1.2)` |
| Panel border | `rgba(255,255,255,0.08)` | hairline |
| Critical accent | `#8B3A2F` | oxidized red — **reserved exclusively for Critical findings**, nothing else gets color |

No green (rejected — nature/Izanami vibe reads wrong for a security tool regardless of
how it's adjusted). No neon. Restraint on the one accent color is what makes it mean
something when it appears.

## Typography — three roles, not two

- **Display** (grade, chapter titles) — a serif with real character (Cinzel/Instrument
  Serif family feel), all Google Fonts, free.
- **Evidence** (headers, TLS certs, DNS records, `Finding.evidence` field) —
  **JetBrains Mono**. Not a "hacker" affectation — genuinely correct, since that data
  really is fixed-width machine output.
- **Body** — Inter.

## Structure — three screens, not a scroll epic

| # | Screen | Notes |
|---|---|---|
| 1 | **Input** | Near-empty. One field, one thesis line. No stats-and-gradient hero. |
| 2 | **Scan** | The set piece. Five agents reporting in with real timings — this is where the animation budget goes, because it's the one place the product has genuine (not manufactured) waiting to dramatize. Ties directly to A16 (SSE live progress) later. |
| 3 | **Report** | The dossier. Grade huge → AI summary → findings by category → agent log. ~5 screens, scannable, not a story. |

## The glass mechanic — pure CSS, not WebGL

- Frosted panels via `backdrop-filter: blur(20px) saturate(1.2)`, hairline border.
- Panels drift at different scroll speeds (`transform: translateY()` tied to scroll
  position) — the "windows going up and down" Arihant wants from Izanami.
- **Decided:** what fills the panels is the scan's own data, rendered as artifacts —
  cert details, header dumps, DNS records styled as inspection evidence. Not stock
  photography (nothing to photograph; server-room stock is the exact cliché this
  project is avoiding) and not abstract texture. The subject matter *is* the content —
  free, always correct, never generic.

## What this ruled out, explicitly

- Green/nature palette (Izanami) — wrong genre.
- Tan/warm-luxury palette (Sondaven) — wrong genre.
- 30+ screens of scroll narrative — wrong product; Sentinels is a fast tool.
- Real WebGL shader glass — right effect, wrong cost for the timeline and the JS/React
  learning curve.
- Stock/subject photography — no real subject exists to photograph; would fight the
  document aesthetic anyway.

## Decided at A13 kickoff

All three items previously open here were settled before A13 was built, and A13-A15
are built against these answers:

- **Serif/mono pairing:** Instrument Serif (display) + JetBrains Mono (evidence) +
  Inter (body). Cinzel considered and rejected — caps-only reads well for a single
  huge grade but weak for longer chapter titles.
- **Input screen:** fully typographic. No illustration, no drifting glass panel on
  screen 1 — maximum restraint there is what makes the report screen's density land
  by contrast. *(Still true of the scan launcher, which now lives at `/url`.)*
- ~~**Entry point:** straight to the scan input, no landing/marketing layer.
  `localhost:3000` *is* the input screen (`/`). Matches "Sentinels is a tool, not a
  brochure."~~ **Superseded 2026-08-04, on Arihant's explicit direction.** `/` is now
  a landing page: a full-bleed hero with the wordmark, the tagline "AI-Powered
  Autonomous Website Security Auditor", and a cinematic image reveal; the scan
  launcher moved to `/url`. This is a deliberate reversal of the "not a brochure"
  position above, taken to make the first impression read as a finished product
  rather than a bare input field.

  What was kept from the original decision: the landing page is **one screen**, not
  the ~27-screen scroll narrative the reference site uses — the objection to a long
  brochure still stands, only the objection to *having a front door at all* was
  dropped. It also reuses the existing palette untouched (the reference's own
  background, `#0E0E0E`, turned out to be within a hair of this project's
  `#0E0E0D`), and its motion is hand-built CSS on the same `cubic-bezier(0.16, 1,
  0.3, 1)` curve `materialize` already used — no animation library was added.

  The one genuine departure from the palette rule: the hero image is a subject
  photograph, which "Panel contents" below explicitly rules out. It is confined to
  the landing page and never appears in a report.

## Process note

Every achievement (A13, A14, A15, ...) still gets its own learning note in
`docs/learning/`, same as every backend achievement so far (A1-A12) — this doesn't
change for frontend work. This file is the *design brief* those achievements build
against; it doesn't replace the per-achievement learning notes, `docs/ROADMAP.md`, or
`docs/ACTIVITY_LOG.md`.
