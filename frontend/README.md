# Sentinels — frontend

The report screen for Sentinels, a passive website security auditor. Next.js
(App Router) + React + Tailwind CSS v4 — see the [root README](../README.md)
for what the project does and how to run both halves together.

## Quick start

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Needs the backend
running on `http://localhost:8000` — see the root README for that half; this
app has nothing to scan against without it.

## Structure

- `app/page.tsx` — the whole product: input screen → live scan progress →
  finished report, as one piece of client state.
- `components/` — `ScanProgress` (the five-agent waiting state),
  `Report`, `ScoreRing`, `FindingRow`, `AgentLog`.
- `lib/api.ts` — talks to the backend (`fetch`, the SSE-based `streamScan`,
  PDF download).
- `lib/useScrollDrift.ts` — the scroll-drift hook behind the report's glass
  panels.

## Design

Three type roles, not two — Instrument Serif (display), JetBrains Mono
(evidence: headers, certs, DNS records), Inter (body) — set up in
`app/layout.tsx` via `next/font/google`. Full design brief, palette, and
rationale in [`docs/DESIGN.md`](../docs/DESIGN.md).
