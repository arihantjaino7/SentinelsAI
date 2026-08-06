/* The grade, as the report's one large moment (docs/DESIGN.md: "Grade huge").

   Note what colour this ISN'T. A score ring that turns red at 40 and green at 90
   is the obvious move and the brief rules it out: the oxidized red is reserved
   exclusively for Critical findings. A ring that changes colour would spend that
   accent on something the number already says, and then it would mean nothing
   when a real Critical finding appears. The ring is drawn in parchment at every
   score; the arc's *length* carries the information. */

const RADIUS = 68;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function ScoreRing({ score, grade }: { score: number; grade: string }) {
  // strokeDasharray makes the outline one long dash the full circumference;
  // strokeDashoffset then hides the portion we don't want drawn. Offset 0 is a
  // complete circle, offset CIRCUMFERENCE is nothing at all.
  const offset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(100, score)) / 100);

  return (
    <div className="relative h-40 w-40 shrink-0 sm:h-52 sm:w-52 lg:h-64 lg:w-64">
      {/* -rotate-90 so the arc starts at 12 o'clock instead of 3 o'clock. */}
      <svg viewBox="0 0 160 160" className="h-full w-full -rotate-90">
        <circle
          cx="80"
          cy="80"
          r={RADIUS}
          fill="none"
          strokeWidth="1"
          stroke="currentColor"
          className="text-rule"
        />
        <circle
          cx="80"
          cy="80"
          r={RADIUS}
          fill="none"
          strokeWidth="1"
          stroke="currentColor"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          className="text-parchment"
        />
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-6xl leading-none sm:text-7xl lg:text-8xl">
          {grade}
        </span>
        <span className="mt-3 font-mono text-xs uppercase tracking-[0.25em] text-muted lg:text-sm">
          {score}/100
        </span>
      </div>
    </div>
  );
}
