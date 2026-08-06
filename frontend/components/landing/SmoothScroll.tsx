"use client";

/* Lenis smooth scrolling, wired into GSAP's ticker.

   Deliberately mounted around the landing page ONLY, not in the root
   layout. Lenis hijacks the page's scroll position, and the scan pages
   already run their own scroll listener (`lib/useScrollDrift.ts`) that
   reads `window.scrollY` directly. Making smooth scroll global would put
   two systems in charge of the same number for no benefit on pages that
   don't need it — so it stays scoped to the one page that does.

   The important detail is that Lenis and ScrollTrigger must share a single
   clock. Left alone, Lenis runs its own requestAnimationFrame loop and
   ScrollTrigger runs another, so ScrollTrigger reads a scroll position
   that Lenis is about to change — the animation lags the scrollbar by a
   frame and jitters. Driving `lenis.raf` from `gsap.ticker` puts both on
   GSAP's single loop, and `ScrollTrigger.update` on every Lenis scroll
   event keeps the trigger's cached positions honest. */

import { useEffect } from "react";
import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function SmoothScroll({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    /* Smooth scroll is motion. Someone who asked the OS for less of it gets
       the native scrollbar, same contract as everywhere else in this
       codebase (see lib/useScrollDrift.ts). */
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const lenis = new Lenis({
      duration: 1.1,
      /* Exponential ease-out. Long tail, no bounce — matches the
         cubic-bezier(0.16, 1, 0.3, 1) the CSS animations already use. */
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      touchMultiplier: 1.6,
    });

    lenis.on("scroll", ScrollTrigger.update);

    const raf = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    /* GSAP normally "catches up" after a stalled frame by clamping delta
       time. With an external scroll source that correction fights Lenis
       and shows up as a hitch, so it's switched off. */
    gsap.ticker.lagSmoothing(0);

    return () => {
      lenis.off("scroll", ScrollTrigger.update);
      gsap.ticker.remove(raf);
      lenis.destroy();
    };
  }, []);

  return <>{children}</>;
}
