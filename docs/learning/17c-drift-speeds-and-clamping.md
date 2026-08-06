# A17c — Drift speeds and clamping

> **Status:** done. The header and each findings category now drift at their
> own speed, and `useScrollDrift` can cap how far that drift goes.

## What we built

Only the Agent Log panel drifted before. Now the report's header and each
findings category ("Headers", "TLS", "DNS", ...) drift too, each at a
different speed — different rates moving together is what reads as depth,
instead of one flat plane. Getting there surfaced a real bug: on a long
report, an uncapped drift on a findings category made its text overlap the
"Agent log" heading below it. The fix was teaching `useScrollDrift` an
optional cap.

## The one big idea: you can't call a hook inside a loop

`Report.tsx` renders one section per findings category using
`groups.map(...)`. The obvious move is to call `useScrollDrift` once per
category inside that loop — but React doesn't allow it. Hooks must run the
same number of times, in the same order, on every render, and a `.map()`
over a list that can grow or shrink (a report can have 3 categories or 5)
breaks that promise.

The fix: pull the thing that needs its own hook call into its own small
component — `groups.map(group => <FindingsCategory group={group} />)`. Each
`<FindingsCategory>` calls `useScrollDrift` once, which is fine: from React's
point of view that's five separate components each independently using a
hook, not one component looping.

```tsx
function Counter({ label }: { label: string }) {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{label}: {count}</button>;
}
// items.map(item => <Counter key={item} label={item} />) — fine, each
// instance calls useState once. useState directly inside the .map()
// callback instead would NOT be fine.
```

## Clamping: capping a value that would otherwise grow forever

The drift was just `scrollY * speed` — no limit. Fine on a short page, but
findings categories sit at different depths depending on how many findings a
scan turns up, and a category drifting at speed `0.08` could move ~200px by
the bottom of a long report — more than the fixed 80px gap to the next
heading, so the text visibly overlapped it.

The fix is `Math.min(offset, cap)`: once the drift would go past the cap,
just use the cap instead.

```ts
function healthBarWidth(currentHp: number, maxHp: number): number {
  const rawPercent = (currentHp / maxHp) * 100;
  return Math.min(rawPercent, 100); // healing past max still shows a full bar
}
```

## The actual code

`useScrollDrift` gained an optional second parameter:

```ts
export function useScrollDrift<T extends HTMLElement>(
  speed: number,
  maxOffsetPx?: number,
) {
  // ...
  function onScroll() {
    const offset = window.scrollY * speed;
    const clamped =
      maxOffsetPx === undefined ? offset : Math.min(offset, maxOffsetPx);
    el!.style.transform = `translateY(${clamped}px)`;
  }
  // ...
}
```

If `maxOffsetPx` isn't passed, nothing changes — `AgentLog.tsx`'s existing
`useScrollDrift(0.06)` call still drifts uncapped, exactly as before. The two
new calls in `Report.tsx` both pass a cap:

```ts
const headerDriftRef = useScrollDrift<HTMLElement>(0.03, 32);
// and, once per category:
const driftRef = useScrollDrift<HTMLElement>(0.08, 48);
```

The cap numbers (32px, 48px) came from actually measuring the gap between
elements on a real report, not guesswork — leaving some of that gap always
intact no matter how long a report gets.

## Try it

- In `FindingsCategory`, drop the cap (`useScrollDrift<HTMLElement>(0.08)`),
  scan a site with several findings, and scroll to the bottom — watch the
  last category's text run into "Agent log." Put the `48` back afterward.
- Try moving `useScrollDrift(0.08, 48)` directly inside the `groups.map(...)`
  callback instead of inside `FindingsCategory` — React throws a dev-mode
  error about hooks being called conditionally.
- Log `{ offset, clamped }` inside `onScroll` and scroll a long report — the
  numbers match early on, then diverge once `offset` passes the cap.

## Words worth knowing

- **Rules of hooks** — hooks must run the same number of times, in the same
  order, on every render of a component.
- **Component extraction** — pulling repeated hook + JSX logic into its own
  component so each repetition is its own instance.
- **Clamping** — bounding a value with `Math.min` (cap a max) or `Math.max`
  (floor a min).

---

**Next:** 17d — styling findings evidence as a bordered "glass" box.
