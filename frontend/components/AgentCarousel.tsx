"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { AgentInfo, AgentResult } from "@/lib/api";
import { isProblem } from "@/lib/findings";
import { AgentPeekDialog } from "@/components/AgentPeekDialog";

/* ---------------------------------------------------------------------------
   Replaces the scroll-driven AgentReel with a circular carousel: a shallow
   arc of small cards, driven by arrows/dots/keyboard/drag instead of scroll.
   AgentReel.tsx is left on disk, unused — reverting this experiment is then
   a two-line change in the page that renders this, not a file resurrection.

   GEOMETRY. Each card sits at an angle along a flattened arc (an ellipse,
   not a circle — RADIUS_Y_RATIO squashes the vertical reach so the shape
   reads as a shelf, not a wheel). The angle comes from `d`, the card's
   *signed* distance from the active card:

     d = shortest-arc(index - activeIndex, total)
     angle = (d / VISIBLE_COUNT) * π
     x = sin(angle) * radiusX      y = -cos(angle) * radiusY

   The "shortest signed distance" part matters at 8 items. A naive
   `index - activeIndex` treats the ring as a line, so with activeIndex = 0
   and total = 8, index 7 computes as offset -7 (all the way around one
   side) instead of offset -1 (one step the other way) — every card ends up
   crowded onto one side of centre instead of split evenly. `d` folds any
   distance greater than half the ring back onto the short way round, the
   same trick a clock face uses to say "11 o'clock is one hour before 12,
   not eleven hours after it". */

const VISIBLE_COUNT = 5; // cards visible at once: the active one + two either side
const HALF = Math.floor(VISIBLE_COUNT / 2); // 2

// The ring's reach is a fraction of the track's own measured width rather
// than a fixed pixel count, via ResizeObserver below — so a phone-width
// track gets a phone-width ring instead of overflowing it.
const MIN_RADIUS_X = 110;
const MAX_RADIUS_X = 240;
const RADIUS_X_RATIO = 0.34;
const RADIUS_Y_RATIO = 0.45; // a shallow arc, not a full circle

interface RingGeometry {
  x: number;
  y: number;
  scale: number;
  opacity: number;
  zIndex: number;
}

function ringPosition(
  index: number,
  activeIndex: number,
  total: number,
  radiusX: number,
  radiusY: number,
): RingGeometry | null {
  if (total === 0) return null;

  let d = (((index - activeIndex) % total) + total) % total; // 0 … total-1
  if (d > total / 2) d -= total; // fold onto the short way round
  if (Math.abs(d) > HALF) return null; // outside the visible span

  const angle = (d / VISIBLE_COUNT) * Math.PI;
  const x = Math.sin(angle) * radiusX;
  const y = -Math.cos(angle) * radiusY;

  const distance = Math.abs(d);
  const maxDistance = HALF + 1;
  const scale = Math.max(0, 1 - (distance / maxDistance) * 0.3);
  const opacity = Math.max(0.3, 1 - (distance / maxDistance) * 0.7);
  const zIndex = VISIBLE_COUNT - distance;

  return { x, y, scale, opacity, zIndex };
}

// Lifted verbatim from AgentReel.tsx — same rule, same wording.
export function statusLabel(result: AgentResult): string {
  if (result.error) return "Failed";
  const problems = result.findings.filter(isProblem).length;
  if (problems === 0) return "Clean";
  return `${problems} issue${problems === 1 ? "" : "s"}`;
}

// Inline rather than lucide-react — that package isn't installed, and two
// static paths aren't worth adding a dependency for.
function Chevron({ direction }: { direction: "left" | "right" }) {
  const d = direction === "left" ? "M15 18l-6-6 6-6" : "M9 18l6-6-6-6";
  return (
    <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden>
      <path
        d={d}
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function AgentCarousel({
  agents,
  info,
  scanId,
}: {
  agents: AgentResult[];
  info: AgentInfo[];
  scanId: string;
}) {
  // `report.agents` arrives in completion order, which varies run to run
  // because the agents race each other — re-sort into registry order so the
  // ring is stable regardless of finish order.
  const ordered = useMemo(
    () =>
      [...agents].sort(
        (a, b) =>
          info.findIndex((i) => i.name === a.agent) -
          info.findIndex((i) => i.name === b.agent),
      ),
    [agents, info],
  );

  const total = ordered.length;
  const [activeIndex, setActiveIndex] = useState(0);
  const [peekAgent, setPeekAgent] = useState<AgentResult | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [radius, setRadius] = useState({ x: 180, y: 81 });
  const reduceMotion = useReducedMotion() ?? false;

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? el.clientWidth;
      const x = Math.min(
        MAX_RADIUS_X,
        Math.max(MIN_RADIUS_X, width * RADIUS_X_RATIO),
      );
      setRadius({ x, y: x * RADIUS_Y_RATIO });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // A re-scan could in principle change how many agents come back. Rather
  // than an effect that notices `activeIndex` is out of range and issues a
  // second setState to correct it — a cascading render — the same modulo
  // `goTo` already uses folds it back into range on every read, so a stale
  // index just wraps instead of pointing past the end of the array.
  const safeIndex = total > 0 ? ((activeIndex % total) + total) % total : 0;

  const goTo = useCallback(
    (index: number) => {
      if (total === 0) return;
      setActiveIndex(((index % total) + total) % total);
    },
    [total],
  );
  const next = useCallback(() => goTo(safeIndex + 1), [safeIndex, goTo]);
  const prev = useCallback(() => goTo(safeIndex - 1), [safeIndex, goTo]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "ArrowLeft") prev();
      if (event.key === "ArrowRight") next();
    }
    const el = rootRef.current;
    el?.addEventListener("keydown", onKeyDown);
    return () => el?.removeEventListener("keydown", onKeyDown);
  }, [next, prev]);

  if (total === 0) return null;

  const metaFor = (agentName: string) => info.find((a) => a.name === agentName);
  const activeAgent = ordered[safeIndex];

  return (
    <section
      ref={rootRef}
      tabIndex={0}
      role="region"
      aria-label="Agents"
      className="mx-auto mt-20 flex max-w-3xl flex-col items-center gap-8 px-6 pb-24 outline-none"
    >
      <h2 className="self-start font-mono text-xs uppercase tracking-[0.3em] text-muted">
        Agents
      </h2>

      <motion.div
        ref={trackRef}
        drag="x"
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={reduceMotion ? 0 : 0.18}
        dragMomentum={false}
        onDragEnd={(_, dragInfo) => {
          if (dragInfo.offset.x < -50) next();
          else if (dragInfo.offset.x > 50) prev();
        }}
        className="relative h-56 w-full cursor-grab touch-pan-y active:cursor-grabbing sm:h-64"
      >
        <AnimatePresence mode="popLayout">
          {ordered.map((result, index) => {
            const pos = ringPosition(index, safeIndex, total, radius.x, radius.y);
            if (!pos) return null;

            const isActive = index === safeIndex;
            const agentMeta = metaFor(result.agent);

            return (
              <motion.button
                key={result.agent}
                type="button"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{
                  x: pos.x,
                  y: pos.y,
                  scale: pos.scale,
                  opacity: pos.opacity,
                  zIndex: pos.zIndex,
                }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={
                  reduceMotion
                    ? { duration: 0.01 }
                    : { duration: 0.65, ease: [0.22, 1, 0.36, 1] }
                }
                onClick={() => {
                  setActiveIndex(index);
                  setPeekAgent(result);
                }}
                aria-label={`${agentMeta?.display_name ?? result.agent} — ${statusLabel(result)}`}
                aria-current={isActive ? "true" : undefined}
                className={`glass absolute left-1/2 top-1/2 flex h-28 w-40 -translate-x-1/2 -translate-y-1/2 flex-col items-start justify-between rounded-2xl p-4 text-left transition-shadow duration-300 sm:h-32 sm:w-48 ${
                  isActive
                    ? "border-parchment/25 shadow-[0_20px_60px_-12px_rgba(0,0,0,0.55)]"
                    : "shadow-[0_8px_24px_-4px_rgba(0,0,0,0.35)] hover:border-parchment/15"
                }`}
                style={{ transformOrigin: "center center" }}
              >
                <span
                  className={`font-mono text-[10px] uppercase tracking-[0.2em] ${
                    result.error ? "text-critical" : "text-muted"
                  }`}
                >
                  {statusLabel(result)}
                </span>
                <div>
                  <h3
                    className={`font-display leading-tight ${
                      isActive ? "text-base text-parchment" : "text-sm text-parchment/80"
                    }`}
                  >
                    {agentMeta?.display_name ?? result.agent}
                  </h3>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.15em] text-muted">
                    {agentMeta?.category ?? result.agent}
                  </p>
                </div>
              </motion.button>
            );
          })}
        </AnimatePresence>

        {/* Anchored inside the track, not the whole section — the section
            also contains the controls row below, and this used to sit on
            top of that too (see AgentCarousel's note above and the plan's
            bug list). */}
        <motion.div
          key={activeAgent.agent}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0.01 : 0.4, ease: "easeOut" }}
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
        >
          <span className="font-display text-5xl leading-none text-parchment/90">
            {String(safeIndex + 1).padStart(2, "0")}
          </span>
          <span className="mt-1 font-mono text-xs text-muted">
            of {String(total).padStart(2, "0")}
          </span>
        </motion.div>
      </motion.div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={prev}
          aria-label="Previous agent"
          className="glass flex h-10 w-10 items-center justify-center rounded-full text-muted transition-colors hover:text-parchment"
        >
          <Chevron direction="left" />
        </button>

        <div className="flex items-center gap-1.5">
          {ordered.map((result, i) => (
            <button
              key={result.agent}
              type="button"
              onClick={() => goTo(i)}
              aria-label={`Go to ${metaFor(result.agent)?.display_name ?? result.agent}`}
              aria-current={i === safeIndex ? "true" : undefined}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === safeIndex
                  ? "w-6 bg-parchment/80"
                  : "w-1.5 bg-parchment/20 hover:bg-parchment/40"
              }`}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={next}
          aria-label="Next agent"
          className="glass flex h-10 w-10 items-center justify-center rounded-full text-muted transition-colors hover:text-parchment"
        >
          <Chevron direction="right" />
        </button>
      </div>

      <AgentPeekDialog
        result={peekAgent}
        info={peekAgent ? metaFor(peekAgent.agent) : undefined}
        scanId={scanId}
        onClose={() => setPeekAgent(null)}
      />
    </section>
  );
}

export default AgentCarousel;
