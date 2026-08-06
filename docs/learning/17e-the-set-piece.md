# A17e — Screen 2: the set piece

> **Status:** done. `frontend/components/ScanProgress.tsx` shows five glass
> panels, one per agent, that "materialize" the instant that agent's real
> result arrives.

## What we built

The waiting screen used to be five plain words fading from dim to bright.
Now it's five glass panels — one per scanning agent — sitting dim and
"Waiting…" until that agent's real result comes in over the network. The
moment it does, that one panel (and only that one) plays a short pop-in
animation and shows its real finding count and timing. Nothing is faked:
the order panels light up in is just whichever agent the real scan actually
finished first.

## The one big idea: forcing React to replay an animation

A CSS `animation` set on an element only plays when that element is first
put on the page. If React just *updates* an existing element's text, the
animation does **not** replay — same element, so no fresh entrance.

React decides "same element or new element?" using each item's `key` prop.
Normally you pick a key that stays stable (like a database id) so React
reuses the element. This component does the opposite on purpose:

```tsx
key={result ? `${name}-done` : `${name}-waiting`}
```

Before a result arrives, the key is `"headers-waiting"`. The instant
`agentResults.headers` gets set, the key becomes `"headers-done"` — a
different string. React has never seen that key before, so it throws away
the old panel and mounts a brand new one. That fresh mount is what makes
the pop-in animation fire, exactly once, exactly when real data shows up.

Everyday version: it's like renaming a package the moment it's delivered.
The delivery service sees a "new" label and re-does the drop-off ritual,
instead of just updating a sticky note on the same box.

## The other concept: `prefers-reduced-motion`

Some people set an OS-level setting asking apps to cut down on motion
(motion sickness, vestibular issues, or just preference). CSS can check
for that setting directly, no JavaScript needed:

```css
@keyframes materialize {
  from { opacity: 0; transform: translateY(10px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

@utility materialize-in {
  animation: materialize 550ms cubic-bezier(0.16, 1, 0.3, 1) both;

  @media (prefers-reduced-motion: reduce) {
    animation: none;
  }
}
```

`@keyframes` just names a sequence of styles over time ("start like this,
end like this"), and `animation` is what actually plays it on an element.
The `@media (prefers-reduced-motion: reduce)` block overrides that to
`animation: none` for anyone who's asked their OS for less motion — checked
for real by reading the built stylesheet, not just eyeballing the source.

## The actual code

```tsx
{AGENT_NAMES.map((name) => {
  const result = agentResults[name];
  return (
    <div
      key={result ? `${name}-done` : `${name}-waiting`}
      className={`glass materialize-in px-4 py-4 ${result ? "" : "opacity-40"}`}
    >
      <p className={`font-mono text-[10px] uppercase tracking-[0.2em] ${result ? "" : "animate-pulse"}`}>
        {name}
      </p>
      {result ? (
        result.error ? (
          <p className="mt-2 font-mono text-[10px] leading-snug break-words">{result.error}</p>
        ) : (
          <p className="mt-2 font-mono text-[10px] text-muted">
            {result.findings.length} checks · {result.duration_ms}ms
          </p>
        )
      ) : (
        <p className="mt-2 font-mono text-[10px] text-muted">Waiting…</p>
      )}
    </div>
  );
})}
```

- Waiting panels are dimmed (`opacity-40`) and pulse; done panels go full
  brightness — contrast by weight, not a new color.
- The error branch mirrors `AgentLog.tsx`: if an agent failed, its own
  error text shows instead of a check count — A3's rule that agents never
  crash the scan, just report their own failure.
- `page.tsx` shrank to one line — this whole block used to live there
  inline.

## Try it

- Change the `key` to just `key={name}` (drop the `-waiting`/`-done`
  suffix), run a real scan, and watch the pop-in stop firing — panels still
  switch from dim to lit, but React now just updates the old element.
- In dev tools, inspect a "done" panel and confirm `animationName` shows
  `materialize` in its computed styles.
- Scan a domain your network can't reach and watch a panel show its own
  error text instead of a check count.

## Words worth knowing

- **Mount-triggered animation** — a CSS animation that only plays when its
  element is newly inserted into the page, not when its content updates.
- **Keying to force a remount** — deliberately changing an element's `key`
  so React treats it as new instead of reusing the old one.
- **`prefers-reduced-motion`** — an OS-level accessibility setting; CSS can
  check it directly with `@media` and turn animations off.

---

**Next:** [`17f`](17f-event-loops-and-the-reload-trap.md) — a real bug found
while testing setup instructions, and the two Windows event loops behind it.
