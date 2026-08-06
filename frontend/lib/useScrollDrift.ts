"use client";

import { useEffect, useRef } from "react";

/**
 * Ties an element's vertical position to scroll — the glass panels "drifting
 * at different scroll speeds" from docs/DESIGN.md's glass mechanic. `speed`
 * is a multiplier on how far the page has scrolled: 0 never moves, 1 moves in
 * lockstep with the page, a small positive value (what every current caller
 * uses) drifts slower than the page around it, which is what reads as depth
 * rather than everything scrolling as one flat plane.
 *
 * `maxOffsetPx`, if given, caps how far the drift can go. Without a cap,
 * `scrollY * speed` grows without bound as the page gets longer — harmless
 * for a panel near the top, but an element positioned deep in a long report
 * (see `FindingsCategory` in `Report.tsx`) can reach a scrollY large enough
 * for even a small speed to drift it past the fixed gap before whatever
 * follows it, visibly overlapping that content. Capping the offset is the
 * standard fix for unbounded scroll-linked motion. Omitted here (as every
 * caller before this one does), the drift is exactly `scrollY * speed`,
 * unchanged — this is an addition, not a behaviour change for A-0.
 */
export function useScrollDrift<T extends HTMLElement>(
  speed: number,
  maxOffsetPx?: number,
) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Some people get real motion sickness from parallax/drift effects —
    // this is the OS-level "reduce motion" accessibility setting, and the
    // one correct response to it here is to just not animate at all.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    function onScroll() {
      const offset = window.scrollY * speed;
      const clamped =
        maxOffsetPx === undefined ? offset : Math.min(offset, maxOffsetPx);
      el!.style.transform = `translateY(${clamped}px)`;
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [speed, maxOffsetPx]);

  return ref;
}
