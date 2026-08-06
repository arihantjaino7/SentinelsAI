# A15 — Report view

> **Status:** done. Scanning a site now shows a real report page: a score ring,
> an AI summary, findings grouped by category, and a log of what each agent did.

## What we built

Four new files under `frontend/components/`: `ScoreRing.tsx` (draws the grade as
a circle), `FindingRow.tsx` (one finding, one block of text), `AgentLog.tsx` (the
five agents and how long each took), and `Report.tsx` (puts the other three
together into the full page). Once a scan finishes, `page.tsx` swaps its
placeholder for `<Report report={report} />`.

## The one big idea: props are just parameters

A React component is a function. **Props are how you pass it arguments.**

```jsx
function Greeting({ name }) {
  return <p>Hello, {name}.</p>;
}

<Greeting name="Priya" />
```

`name="Priya"` at the call site and `{ name }` in the function signature are
the whole mechanism — React bundles every attribute you write on a tag into one
object and hands it to the function as its single argument. This is exactly
Python's keyword arguments:

```python
def greeting(name):
    return f"Hello, {name}."

greeting(name="Priya")
```

The one rule worth remembering: **props flow one way, parent to child.** A
component can read its props but can't change them — `ScoreRing` gets `score`
and `grade` from `Report`, but has no way to hand a different number back up.

```jsx
export function ScoreRing({ score, grade }: { score: number; grade: string }) {
```

The second `{ }` is just the TypeScript type of the props object — "this
component takes exactly these two things." Mix them up at the call site and
it's a compile error, not a bug you find by staring at a broken page.

## The actual code

`Report.tsx` doesn't know how to draw a circle or format a finding — it just
imports the three smaller components and arranges them:

```jsx
<ScoreRing score={report.score} grade={report.grade} />
...
{group.problems.map((finding) => (
  <FindingRow key={finding.id} finding={finding} />
))}
...
<AgentLog agents={report.agents} totalMs={report.duration_ms} />
```

This is called **composition** — building one big screen from several small,
single-purpose pieces. Same idea as `orchestrator.py` combining five agents
without knowing how any single one works internally.

A couple of smaller things worth a glance in the source:

- `Report.tsx` computes `groups` and `problemCount` fresh on every render
  instead of storing them in `useState` — they're fully determined by
  `report.findings`, which is already a prop, so recalculating avoids two
  copies of the same fact drifting apart.
- `ScoreRing` draws its arc with `strokeDasharray`/`strokeDashoffset`: the
  circle's outline is one dash the length of the whole circumference, and the
  offset hides the part that shouldn't show. At `score=100` nothing is hidden;
  at `score=0` the whole dash is hidden. The ring never changes colour with the
  score — `DESIGN.md` reserves the accent red for Critical findings only, so
  the arc's *length* carries the information instead of a colour.
- Findings only show a description, evidence box, or remediation line if that
  field is actually non-empty (`{finding.evidence && (...)}`) — every one of
  those fields is optional in the backend model.

## Try it

1. Scan two very different sites (e.g. `github.com` and `neverssl.com`) and
   watch the ring's arc length change while its colour stays the same.
2. In `ScoreRing.tsx`, hardcode `strokeDashoffset={0}`. Every scan now shows a
   full ring, proving the offset — not some hidden per-grade logic — draws it.
3. Remove `key={finding.id}` from the `.map()` in `Report.tsx`, run a scan, and
   check the browser console — React warns about a missing `key` on list items.
4. In `FindingRow`, try `finding.severity = "Critical"` at the top of the
   function body. Nothing breaks, but `Report.tsx` never sees the change —
   props are a snapshot handed down, not a live link back up.

## A few words worth knowing

- **Props** — the object a component receives as its one argument, built from
  the attributes at its call site. Flow one direction: parent to child.
- **Composition** — building a screen from small, focused components instead
  of one giant one.
- **Derived data** — a value computed fresh from props/state every render,
  instead of stored separately, so it can never fall out of sync.
- **`strokeDasharray` / `strokeDashoffset`** — SVG's way of drawing a partial
  circle: the dash pattern length, and how far into it drawing starts.

---

**Next:** A16 — live progress, watching each agent finish in real time instead
of waiting for all five at once.
