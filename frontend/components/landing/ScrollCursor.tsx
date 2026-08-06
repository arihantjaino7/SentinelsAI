"use client";

/* A small "SCROLL DOWN" label that trails the pointer.

   Modelled on the reference's `project-cursor-follower`: a
   `pointer-events-none fixed` element at a high z-index, held at `scale(0)`
   until it should appear, set in mono. It never replaces the real cursor —
   the native arrow stays visible, so links and text selection keep behaving
   normally and nothing about the page becomes less usable.

   Two behaviours worth naming:

   - It LERPS toward the pointer instead of tracking it exactly. Writing the
     raw pointer position each event makes a follower feel glued and cheap;
     easing a fraction of the remaining distance per frame gives it weight,
     so it trails slightly and settles. Same technique, same reasoning as the
     parallax that used to be on the hero image.

   - It fades out once the puzzle has finished assembling. Telling someone to
     scroll down when there is nothing left to scroll to is worse than saying
     nothing, so the label's job ends when the scroll does.

   Hidden entirely on touch devices (no pointer to follow) and under
   `prefers-reduced-motion`, matching the contract used everywhere else in
   this codebase. */

import { useEffect, useRef } from "react";

/** Fraction of the remaining distance covered per frame. Lower = heavier. */
const EASING = 0.14;
/** Below this much remaining page scroll, the prompt has nothing to ask for. */
const HIDE_NEAR_END_PX = 240;

export function ScrollCursor() {
  const labelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = labelRef.current;
    if (!node) return;

    /* A coarse pointer means touch: there is no cursor to follow, and a
       label chasing taps would just be litter on the screen. */
    const isTouch = window.matchMedia("(pointer: coarse)").matches;
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (isTouch || reducedMotion) return;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currentX = targetX;
    let currentY = targetY;
    let visible = false;
    let frameId = 0;

    function handlePointerMove(event: PointerEvent) {
      targetX = event.clientX;
      targetY = event.clientY;
      if (!visible) {
        visible = true;
        if (node) node.style.opacity = "1";
      }
    }

    /* Leaving the window should retract the label rather than leave it
       stranded at the last known position. */
    function handlePointerLeave() {
      visible = false;
      if (node) node.style.opacity = "0";
    }

    function tick() {
      currentX += (targetX - currentX) * EASING;
      currentY += (targetY - currentY) * EASING;

      const remaining =
        document.documentElement.scrollHeight -
        window.scrollY -
        window.innerHeight;
      const atEnd = remaining < HIDE_NEAR_END_PX;

      if (node) {
        /* translate3d keeps this on its own compositor layer, so moving it
           never repaints the page beneath. The offset puts the label below
           and right of the actual cursor rather than under it. */
        node.style.transform = `translate3d(${(currentX + 18).toFixed(1)}px, ${(currentY + 20).toFixed(1)}px, 0)`;
        node.style.opacity = visible && !atEnd ? "1" : "0";
      }
      frameId = requestAnimationFrame(tick);
    }

    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    document.addEventListener("pointerleave", handlePointerLeave);
    frameId = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerleave", handlePointerLeave);
      cancelAnimationFrame(frameId);
    };
  }, []);

  return (
    <div
      ref={labelRef}
      aria-hidden
      className="pointer-events-none fixed top-0 left-0 z-[1000] hidden opacity-0
                 transition-opacity duration-500 will-change-transform sm:block"
    >
      <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.28em] text-muted">
        Scroll down
        <span aria-hidden className="text-[9px]">
          ↓
        </span>
      </span>
    </div>
  );
}
