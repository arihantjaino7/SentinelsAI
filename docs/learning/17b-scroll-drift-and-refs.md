# A17b — Scroll drift and refs

> **Status:** done. `frontend/lib/useScrollDrift.ts` makes the Agent Log panel
> drift slightly slower than the page as you scroll.

## What we built

The Agent Log panel on the report screen now moves a little slower than the
rest of the page when you scroll — it "hangs back" instead of scrolling in
lockstep with everything around it. It's built as a reusable hook, so any
other panel can get its own drift speed later in a single line.

## The one big idea: a custom hook

React ships some hooks for you — `useState` is one you've already used. A
**custom hook** is just a function you write yourself that also starts with
`use` and is allowed to call those built-in hooks inside it. That's the whole
rule. Without it, every panel that wants to drift would need the same few
lines copy-pasted into it — instead, `AgentLog.tsx` writes one line,
`useScrollDrift(0.06)`, and never has to know how the drifting works.

```tsx
function useCounter(start: number) {
  const [count, setCount] = useState(start);
  return { count, increment: () => setCount((c) => c + 1) };
}
```

Any component can call `useCounter(0)` and get its own independent counter —
same idea as `useScrollDrift` giving each panel its own independent listener.

## Reaching into the real page: `useRef` + `useEffect`

Normally in React you don't touch the actual page elements — you change
state, and React updates the screen for you. But to make a panel drift, we
need to grab the *real* HTML element and move it directly. Two tools do that:

- **`useRef`** gives you a box, `{ current: ... }`, that React fills in with
  the real DOM element once it exists. `<div ref={someRef}>` is how you say
  "hand me this one."
- **`useEffect`** runs code *after* React has drawn the screen — the right
  moment to attach something like a scroll listener, since the element needs
  to already exist. It can also return a cleanup function that runs when the
  component goes away, so old listeners don't pile up.

Think of `useRef` as a sticky note with an address on it, `useEffect` as
"once the building exists, go do something at that address."

## The actual code

```ts
export function useScrollDrift<T extends HTMLElement>(speed: number) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Respect the OS "reduce motion" setting — just don't animate at all.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    function onScroll() {
      el!.style.transform = `translateY(${window.scrollY * speed}px)`;
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [speed]);

  return ref;
}
```

- `speed` is a multiplier: `0.06` means the panel moves at 6% of however far
  you've scrolled — subtle, not seasick.
- `el.style.transform` is set directly on the real element, not through
  `setState` — scroll fires very often, so re-rendering React each time would
  be wasteful.
- `{ passive: true }` promises the browser this listener won't block
  scrolling, so scrolling can start immediately.

In `AgentLog.tsx`: `const driftRef = useScrollDrift<HTMLDivElement>(0.06);`,
then `<div ref={driftRef} className="glass ...">`.

## Try it

- In `AgentLog.tsx`, change `0.06` to `0.3` and scroll — much more noticeable
  drift. Try `0` — the panel stops moving relative to the page entirely.
- Turn on "reduce motion" in your OS accessibility settings, reload the page,
  and scroll — the panel should stay still.
- Comment out the `return () => window.removeEventListener(...)` line, then
  navigate to the report and back a few times — scrolling gets janky as old
  listeners pile up.

## Words worth knowing

- **Custom hook** — a function you write, named `use...`, that calls real
  hooks inside it.
- **`useRef`** — a box that survives re-renders and can hold a real DOM
  element.
- **`useEffect`** — runs code after React updates the screen; can return a
  cleanup function.
- **Passive listener** — a scroll/touch listener that promises not to block
  the browser's default handling.

---

**Next:** 17c — giving each panel its own drift speed, and capping it so it
doesn't overlap the next section.
