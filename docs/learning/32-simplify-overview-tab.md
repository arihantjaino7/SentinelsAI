# 32 — Strip the overview down to score + buttons

> **Status:** done. The overview tab is now just the score header (unchanged) and the 5-agent button panel. Everything else — the AI summary, the "biggest problem" callout, deployment badge, full findings list, recent scans — is gone from this page; it all still exists, one click away, on the per-agent detail pages and the Checklist tab.

## What changed

Last note (30) made the overview page *busier* — it added a "biggest problem" callout above the agent grid. This note undoes that in favor of the opposite idea: the overview should answer "what's my score" and "which agent do I want to open," nothing else. Every other page (agent detail, checklist) already existed and already had the real depth — the overview didn't need to duplicate any of it.

Removed from `app/scan/[scanId]/page.tsx`: the "biggest problem" callout, the deployment badge, the AI summary paragraph, the entire findings list (and its `FindingsCategory` helper), and the recent-scans list. What's left is the header (score ring, URL, download button, severity counts — untouched) and `<AgentLog agents={report.agents} scanId={scanId} />`.

## The bug: five boxes instead of one panel

The agent grid had a real visual bug, separate from the simplification. Each of the 5 agent cards was its own `glass` box (`background: rgba(255,255,255,0.04)` + `backdrop-filter: blur(20px)`). A frosted-glass effect needs something behind it to blur — against the flat, textureless page background, a box that small just shows a barely-there 4%-white tint. Five of those side by side read as text floating with no visible container at all, which is exactly what "the background is kind of missing" meant.

## New concept: CSS Grid's `gap` divider trick

The fix wasn't Tailwind's `divide-x`/`divide-y` utilities — checked live in the browser console and confirmed this project's Tailwind build generates **zero** CSS for them (searched every stylesheet rule for `divide`, found nothing). Rather than fight that, the fix uses a plain CSS Grid technique that doesn't depend on any utility class working correctly:

```html
<!-- small standalone example -->
<style>
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: hotpink; }
  .cell { background: white; padding: 1rem; }
</style>
<div class="grid">
  <div class="cell">A</div>
  <div class="cell">B</div>
  <div class="cell">C</div>
  <div class="cell">D</div>
</div>
```

The grid container's own background only shows through the `gap` — everywhere else, each cell's own background covers it. So the "divider" isn't a border at all, it's the *container's color leaking through a 1px seam*. Applied here: the wrapping `glass` panel is the (lightly tinted) container, each agent cell paints itself solid `bg-[#0e0e0d]` (the exact `--color-ink` page background), and the 1px `gap-px` between cells reveals the glass panel's tint as a hairline. One real panel, five cells that read as divided, and nothing depends on a utility class that turned out not to exist in this build.

## Try it

- Open a scan's overview. It should be just: score ring + URL + counts, then a single frosted panel with 5 clickable agent names — nothing else.
- Click any agent name — its full detail page (findings, evidence, "Get AI fix") is unchanged.
- Resize to a narrow (mobile) width — the panel should wrap to 2 columns, dividers still show correctly on the wrapped row (this is the thing `divide-x` could never do cleanly, since it doesn't know about row wraps — the `gap` trick doesn't care, it's just CSS Grid).
- Checklist tab is untouched.

## Words worth knowing

- **`backdrop-filter: blur()`** — blurs whatever is *behind* an element, through it. Needs visual texture behind it to have any visible effect; against a flat color it's nearly invisible.
- **CSS Grid `gap`** — the empty space between grid cells. It isn't transparent by default in the sense of "shows the page" — it shows the *grid container's own background*, which is what makes the divider trick work.
- **Arbitrary value (Tailwind)** — `bg-[#0e0e0d]` bypasses the Tailwind theme lookup entirely and emits that exact CSS value, useful as a fallback when a theme-based utility (`bg-ink`, `divide-white/6`) can't be trusted to exist.
