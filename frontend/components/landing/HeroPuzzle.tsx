"use client";

/* The hero: a wordmark that shrinks into a header, a tagline that flies up
   from the bottom of the screen to sit under it, and a photo that assembles
   itself out of scattered tiles — all driven by one scrubbed scroll.

   HOW THE TILING WORKS — the whole trick is one image used as a sprite
   sheet. Every tile is an empty div carrying the *same* background image,
   blown up to N times the container in both axes, then offset so only its
   own square shows:

     background-size:     (cols*100)% (rows*100)%
     background-position: (col/(cols-1))*100%  (row/(rows-1))*100%

   The `N-1` is the part that's easy to get wrong. `background-position`
   percentages don't position the image's top-left corner — they align the
   *same percentage point* of the image with that percentage point of the
   box. So 100% means "right edge of image to right edge of box", not
   "shifted right by 100%". With N columns there are only N-1 gaps between
   first and last, so the step is 1/(N-1). Use 1/N and every tile is
   subtly, maddeningly misaligned.

   The tiles are also sized 101%, not 100%. At fractional device pixel
   ratios a 100% tile leaves a hairline of background showing between
   neighbours, and that reads as a grid drawn over the photo. The extra 1%
   overlaps its neighbour and the seams vanish.

   HOW THE MOTION WORKS — one GSAP timeline scrubbed by ScrollTrigger, so
   every position is a pure function of scroll: scroll down and it builds,
   scroll up and it un-builds, stop and it holds. Nothing loops, nothing
   plays on its own.

   Every value animated is `transform` or `opacity`, both of which the
   compositor handles without touching layout or paint. `filter: blur` is
   the one exception and it is genuinely expensive — see BLUR_MAX_PX. */

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

/** 7 x 4 = 28 tiles — the reference's own grid, not a guess. Reading
    produx.design's live DOM showed `background-size: 700% 400%` on its
    tiles, which is 7 columns by 4 rows.

    This replaced an 8x8. Sixty-four tiles is nearly a screen-door: each
    piece is small enough that arrivals read as static rather than as
    individual pieces of a picture. At 28 each piece is a legible fragment
    of the photo, which is what makes the assembly look like a puzzle
    solving itself instead of a progress bar filling in. */
const GRID_COLS = 7;
const GRID_ROWS = 4;
/** Native size of /public/hero.jpg — fixes the container aspect so the
    sprite maths can't distort the photo. */
const IMAGE_W = 1280;
const IMAGE_H = 853;
/** How much of the available height the assembled photo takes.

    The brief asks for the photo to end up around 70% of the screen. That
    is a *width* target, and on a short viewport it simply cannot be met
    without either distorting the photo or overflowing the pinned screen —
    at 1280x720 the height available under the logo caps the width around
    62%. So this fills nearly all the height that exists and lets the
    aspect ratio decide the width: on the taller screens people actually
    use (900px+) that lands at 70-76%, and on short ones it degrades to
    "as large as fits" rather than breaking the layout. */
const GRID_FILL = 0.92;

/* ── ACT ONE: the wordmark and the tagline, locked together ──────────────

   The brief on this one is exact: the wordmark shrinking to logo size and
   the tagline flying up from the bottom-left "should start at the same
   time and end at the same time. There should be no delay."

   So both tweens are placed at position 0 with the *same* duration, and
   both use `ease: "none"`. Easing is the subtle trap here — two tweens can
   share a start and an end and still visibly drift apart in the middle if
   one accelerates and the other doesn't. Linear on both means the tagline
   is always exactly as far along its travel as the wordmark is along its
   shrink, which is what "no delay" actually looks like in motion. It also
   ties both directly to scroll position, so they feel attached to the
   gesture rather than chasing it. */
const ACT_ONE_END = 0.18;
/** Gap between the tagline's resting position and the bottom of the screen
    at the start of the scroll. */
const TAGLINE_BOTTOM_INSET_PX = 48;

/* ── ACT TWO: a few pieces, floating ─────────────────────────────────────

   The moment Act One stops, the first pieces appear — not travelling to
   their final places, but drifting to a holding position in mid-air and
   staying there. That pause is the point: it gives the eye something to
   read as depth before the picture exists, and it is what stops the
   assembly from feeling like it starts already half-finished. */
const OPENER_COUNT = 4;
const FLOAT_START = ACT_ONE_END;
/** Each opener enters a beat after the previous one. Tightened from 0.03:
    at the wider spacing only one speck existed for the first stretch after
    Act One, which read as the screen still being empty. */
const OPENER_STAGGER = 0.02;
/** How long one opener takes to drift in from the far distance. */
const FLOAT_TRAVEL = 0.085;
/** The openers fade in over a fraction of their travel rather than across
    all of it.

    This is what closes the "black screen" gap after Act One. The pieces
    already *started* at exactly the right moment — but a tile that is 4px
    wide and still half-transparent is indistinguishable from empty
    background, so the sequence looked like it began late. Bringing the
    opacity up almost immediately means the piece is legible from its first
    frame and the growth is the thing you watch, rather than the fade. */
const OPENER_FADE_IN = 0.22;

/** Where the openers hover: close enough to read as real fragments, far
    enough to still be visibly out of place. */
const HOVER_DEPTH_MIN_PX = 380;
const HOVER_DEPTH_MAX_PX = 620;
const HOVER_SPREAD_X_VW = 13;
const HOVER_SPREAD_Y_VH = 11;
const HOVER_BLUR_PX = 6;

/* ── ACT THREE: the tagline leaves, the picture assembles ────────────────  */

/** The tagline scrolls up and out while the openers are still hovering, so
    the screen is down to just the logo and the pieces before the assembly
    proper begins. */
const TAGLINE_EXIT_AT = 0.38;
const TAGLINE_EXIT_DURATION = 0.1;

const ASSEMBLY_START = 0.46;
/** Where the LAST tile begins its travel, not where it lands. Plus that
    tile's own duration this comes to exactly 1.0.

    Setting this to 1.0 (the obvious-looking value) is wrong: the last tile
    would still be flying when the timeline ended, GSAP would extend the
    total to fit, and every constant above would silently rescale to
    something earlier than it reads here. */
const CROWD_LAST_START = 0.84;

/* The rate at which pieces arrive has to accelerate, or 28 tiles landing
   at a constant rate reads as a machine filling in a progress bar. One
   exponent does it — each tile's arrival is its place in the order raised
   to ARRIVAL_CURVE:

       at = ASSEMBLY_START + (place / last) ** ARRIVAL_CURVE * span

   Below 1, that curve is steep at the start and flat at the end, so the
   *gaps* between arrivals shrink monotonically: the first pieces get room
   to be watched individually and the picture completes in a rush. */
const ARRIVAL_CURVE = 0.55;

/* Per-tile travel time, as a fraction of the whole scrubbed timeline.

   These are deliberately close together. The intuitive choice — make late
   tiles much quicker — cancels out the accelerating arrivals: pieces
   appear faster but each clears faster too, so the number in flight at
   once flatlines and the ending has no build to it. Keeping travel long
   relative to the gaps between arrivals is what makes them pile up. */
const OPENER_ASSEMBLY_DURATION = 0.24;
const CROWD_DURATION_MAX = 0.28;
const CROWD_DURATION_MIN = 0.16;

/* Scatter ranges for the crowd, taken from frames of the reference rather
   than guessed. Three things came out of actually watching it:

   NO ROTATION. The reference's start transform is
   `matrix3d(0.2, 0, 0, 0, 0, 0.2, 0, 0, ...)` — pure scale, both
   off-diagonal terms zero. Its tiles stay axis-aligned the whole way. An
   earlier version here tumbled them ±14°, which made the assembly read as
   debris blowing together rather than an image resolving into focus.

   TILES START SMALL — 0.2, not 0.55.

   And the depth does most of the work. With `perspective: 1200px`, a tile
   at `translateZ(-1000px)` is drawn at 1200/(1200+1000) ≈ 0.55 of its size
   AND pulled toward the perspective origin. That, not a large translation,
   is what displaces them. */
const SPREAD_X_VW = 16;
const SPREAD_Y_VH = 14;

/* Two sets of start values, because the openers and the crowd have
   opposite jobs. THE OPENERS come from much further away than the
   reference does — the brief is that the first few sit right back against
   the black, then grow. At z = -2400 with a 1200px perspective a tile is
   drawn at 1200/(1200+2400) = 0.33 of its size, and the 0.12 scale on top
   puts it near 4% of final — a speck. That is the point: there has to be
   somewhere to grow *from*.

   THE CROWD lands on the reference's own measured numbers. By the time
   twenty tiles are moving together, extra distance stops reading as depth
   and starts reading as noise. */
/* Brought forward from 2000-2600 / 0.08-0.16. At those values the first
   opener rendered about 4px across, which is a dot rather than a piece of
   a photo — the other half of why the screen read as black after Act One.
   These still start it "right back" (a 1700px push with a 1200px
   perspective is 41% foreshortening, so it enters around 8% of final size
   and has plenty of room to grow) while being visible from frame one. */
const OPEN_DEPTH_MIN_PX = 1700;
const OPEN_DEPTH_MAX_PX = 2200;
const OPEN_SCALE_MIN = 0.13;
const OPEN_SCALE_MAX = 0.2;

const CROWD_DEPTH_MIN_PX = 900;
const CROWD_DEPTH_MAX_PX = 1500;
const CROWD_SCALE_MIN = 0.2;
const CROWD_SCALE_MAX = 0.34;

/* Blur is the one non-composited property here: each frame re-rasterises
   every blurred tile, so it is the single thing most able to cost frames.
   It stays affordable because the stagger means only a handful of tiles
   are ever blurred at the same moment, and because each tile's blur
   resolves in the first fraction of its travel. */
const BLUR_MAX_PX = 40;

/** How far the wordmark shrinks, per breakpoint.

    The brief asks for "very small, like a logo size" — something that
    reads as site chrome rather than a heading. These ratios land it near
    26px at every breakpoint: 13vw x 0.16 = 2.08vw (26.6px at 1280),
    17vw x 0.20 = 3.4vw (26px at 768), 20vw x 0.28 = 5.6vw (21px at 375).

    Read as a function rather than a constant so `invalidateOnRefresh` can
    re-evaluate it when the viewport crosses a breakpoint. */
function titleTargetScale(): number {
  const w = window.innerWidth;
  if (w < 640) return 0.28;
  if (w < 1024) return 0.2;
  return 0.16;
}

type TileStart = {
  x: number;
  y: number;
  z: number;
  scale: number;
  blur: number;
  /** Where this tile's travel home begins on the 0-1 timeline. */
  at: number;
  /** How long that travel lasts, in timeline units. */
  duration: number;
  /** One of the far-back openers that floats before assembling. */
  isOpener: boolean;
  /** Openers only: the mid-air position they hold before assembling. */
  hover?: { x: number; y: number; z: number; scale: number };
  /** Openers only: when they first fade in out of the distance. */
  floatAt?: number;
};

/** Deterministic per-index pseudo-random in [0,1).
    A plain Math.random() would also work (this only ever runs in an
    effect, so there's no hydration risk), but a stable hash means the
    scatter is identical across reloads and hot-reloads — which makes it
    possible to actually judge the composition instead of re-rolling it
    every save. */
function rand(index: number, salt: number): number {
  const n = Math.sin(index * 127.1 + salt * 311.7) * 43758.5453;
  return n - Math.floor(n);
}

/** Mix two numbers by t. */
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function buildStarts(count: number): TileStart[] {
  /* Random *order*, not row-by-row: shuffle the tile indices and use each
     tile's place in the shuffle as its start time. Sorting by a hash gives
     a shuffle that's stable across reloads for the same reason `rand` is. */
  const order = Array.from({ length: count }, (_, i) => i).sort(
    (a, b) => rand(a, 99) - rand(b, 99)
  );
  const slot = new Map(order.map((tileIndex, place) => [tileIndex, place]));
  const crowdCount = Math.max(1, count - OPENER_COUNT - 1);
  const span = CROWD_LAST_START - ASSEMBLY_START;

  return Array.from({ length: count }, (_, i) => {
    const place = slot.get(i)!;
    const isOpener = place < OPENER_COUNT;

    if (isOpener) {
      return {
        x: (rand(i, 1) * 2 - 1) * SPREAD_X_VW * 1.45,
        y: (rand(i, 2) * 2 - 1) * SPREAD_Y_VH * 1.45,
        z: -(OPEN_DEPTH_MIN_PX + rand(i, 3) * (OPEN_DEPTH_MAX_PX - OPEN_DEPTH_MIN_PX)),
        scale: OPEN_SCALE_MIN + rand(i, 6) * (OPEN_SCALE_MAX - OPEN_SCALE_MIN),
        blur: BLUR_MAX_PX * (0.75 + rand(i, 7) * 0.25),
        hover: {
          x: (rand(i, 11) * 2 - 1) * HOVER_SPREAD_X_VW,
          y: (rand(i, 12) * 2 - 1) * HOVER_SPREAD_Y_VH,
          z: -(HOVER_DEPTH_MIN_PX + rand(i, 13) * (HOVER_DEPTH_MAX_PX - HOVER_DEPTH_MIN_PX)),
          scale: 0.72 + rand(i, 14) * 0.12,
        },
        floatAt: FLOAT_START + place * OPENER_STAGGER,
        /* Openers leave their hover in the order they arrived, so the
           first piece you saw is also the first one to find its place. */
        at: ASSEMBLY_START + place * 0.02,
        duration: OPENER_ASSEMBLY_DURATION,
        isOpener: true,
      };
    }

    /* `progress` is how far through the crowd's order this tile is; `at` is
       where that lands once bent by the curve. Everything else interpolates
       along the same value, so depth, size, blur and duration resolve
       together — the picture literally comes closer and sharpens as it
       fills in, rather than every tile making an identical journey at a
       different time. */
    const progress = (place - OPENER_COUNT) / crowdCount;
    const at = ASSEMBLY_START + Math.pow(progress, ARRIVAL_CURVE) * span;

    const depthMin = lerp(CROWD_DEPTH_MAX_PX, CROWD_DEPTH_MIN_PX, progress);
    const scaleMin = lerp(CROWD_SCALE_MIN, CROWD_SCALE_MAX, progress);
    /* Later tiles converge from closer in, which is what stops twenty
       simultaneous arrivals reading as static. */
    const reach = lerp(1.0, 0.55, progress);

    return {
      x: (rand(i, 1) * 2 - 1) * SPREAD_X_VW * reach,
      y: (rand(i, 2) * 2 - 1) * SPREAD_Y_VH * reach,
      z: -(depthMin + rand(i, 3) * 300),
      scale: scaleMin + rand(i, 6) * 0.08,
      blur: BLUR_MAX_PX * (0.65 + rand(i, 7) * 0.35) * lerp(0.9, 0.5, progress),
      at,
      duration: lerp(CROWD_DURATION_MAX, CROWD_DURATION_MIN, progress),
      isOpener: false,
    };
  });
}

type HeroPuzzleProps = {
  /** Rendered inside the pinned section, above the grid. Passing the
      heading in here is what lets it stay pinned while the image
      assembles, the way the reference composes its hero. */
  header?: React.ReactNode;
};

export function HeroPuzzle({ header }: HeroPuzzleProps) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const grid = gridRef.current;
    const section = sectionRef.current;
    if (!grid || !section) return;

    const tiles = Array.from(grid.children) as HTMLElement[];
    const titleEl = section.querySelector<HTMLElement>("[data-hero-title]");
    const taglineEl = section.querySelector<HTMLElement>("[data-hero-subtitle]");
    const stickyEl = section.querySelector<HTMLElement>("[data-hero-sticky]");

    /* Reduced motion: no scatter, no scrub — just show the finished
       picture, with the wordmark at its resting size and the tagline
       already in place. Same contract as the CSS animations and
       useScrollDrift. */
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      gsap.set(tiles, { opacity: 1, filter: "blur(0px)" });
      if (titleEl) gsap.set(titleEl, { scale: titleTargetScale() });
      if (taglineEl) gsap.set(taglineEl, { opacity: 1, y: 0 });
      return;
    }

    /* How far below its resting place the tagline starts — i.e. the offset
       that puts it at the bottom-left of the first screen.

       Measured against the sticky element rather than the viewport, and
       with the element's own transform temporarily zeroed. The sticky box
       is exactly one screen tall, so its local coordinates and the
       viewport's agree, and measuring inside it means the answer doesn't
       depend on where the page happens to be scrolled when ScrollTrigger
       refreshes. Function-based so `invalidateOnRefresh` re-measures it on
       resize, when both the viewport height and the text's wrapped height
       can change. */
    const taglineStartY = (): number => {
      if (!taglineEl || !stickyEl) return 0;
      const previous = gsap.getProperty(taglineEl, "y") as number;
      gsap.set(taglineEl, { y: 0 });
      const taglineRect = taglineEl.getBoundingClientRect();
      const stickyRect = stickyEl.getBoundingClientRect();
      gsap.set(taglineEl, { y: previous });

      const restingTop = taglineRect.top - stickyRect.top;
      const bottomTop =
        window.innerHeight - TAGLINE_BOTTOM_INSET_PX - taglineRect.height;
      return bottomTop - restingTop;
    };

    /* The tagline's one-time arrival, on the clock rather than the scroll —
       see the note on its Act One tween for why this can't live there. The
       delay lets the wordmark's own word-reveal get going first, so the two
       read as one entrance instead of a tie. */
    if (taglineEl) {
      gsap.fromTo(
        taglineEl,
        { opacity: 0 },
        { opacity: 1, duration: 0.9, delay: 0.45, ease: "power2.out" }
      );
    }

    const starts = buildStarts(tiles.length);

    /* gsap.context scopes every tween and ScrollTrigger created inside it,
       so the single revert() below cleans up all of them — the thing that
       otherwise leaks on every hot-reload and in React 18 StrictMode's
       double-effect. */
    const ctx = gsap.context(() => {
      const timeline = gsap.timeline({
        defaults: { ease: "power2.out" },
        scrollTrigger: {
          trigger: section,
          start: "top top",
          end: "bottom bottom",
          /* Number, not `true`: the timeline chases the scroll position
             over this many seconds instead of snapping 1:1 to it. With
             Lenis already smoothing the input, this longer catch-up is
             what turns a flicked trackpad into a glide. */
          scrub: 1.0,
          /* Re-evaluates the function-based values below (the target scale,
             the tagline's travel) whenever ScrollTrigger refreshes, which
             includes resize. Without it, crossing a breakpoint would leave
             the wordmark shrinking to the previous viewport's ratio and the
             tagline flying to a stale position. */
          invalidateOnRefresh: true,
        },
      });

      /* ── ACT ONE — locked together, both at position 0, both linear.
            See ACT_ONE_END above for why the easing matters as much as the
            timing here. */
      if (titleEl) {
        timeline.fromTo(
          titleEl,
          { scale: 1 },
          {
            scale: () => titleTargetScale(),
            duration: ACT_ONE_END,
            ease: "none",
          },
          0
        );
      }

      if (taglineEl) {
        /* Position only — opacity is deliberately NOT on this tween.

           The tagline has to be *visible* at the bottom-left the moment the
           page opens, and anything on a scrubbed timeline reads 0 at scroll
           position 0. Fading it in here would mean it was invisible until
           the user scrolled, which is the opposite of the brief. Its
           entrance is a separate, ordinary tween below; this one owns the
           travel and nothing else. */
        timeline.fromTo(
          taglineEl,
          { y: () => taglineStartY() },
          { y: 0, duration: ACT_ONE_END, ease: "none" },
          0
        );
      }

      /* ── ACT TWO — the openers drift in out of the distance and hold. */
      tiles.forEach((tile, i) => {
        const s = starts[i];
        if (!s.isOpener || !s.hover || s.floatAt === undefined) return;

        timeline.fromTo(
          tile,
          {
            xPercent: s.x,
            yPercent: s.y,
            z: s.z,
            scale: s.scale,
            filter: `blur(${s.blur.toFixed(1)}px)`,
          },
          {
            xPercent: s.hover.x,
            yPercent: s.hover.y,
            z: s.hover.z,
            scale: s.hover.scale,
            filter: `blur(${HOVER_BLUR_PX}px)`,
            duration: FLOAT_TRAVEL,
            /* A long, soft tail so the piece decelerates into its hover
               rather than stopping dead — that deceleration is what reads
               as "floating" instead of "parked". */
            ease: "power3.out",
          },
          s.floatAt
        );

        /* Opacity on its own, far quicker than the travel — see
           OPENER_FADE_IN. Kept as a separate tween rather than a different
           ease on the one above because the two properties genuinely want
           different timings here: the piece should be fully *there* almost
           at once, and then spend the rest of its travel growing. */
        timeline.fromTo(
          tile,
          { opacity: 0 },
          {
            opacity: 1,
            duration: FLOAT_TRAVEL * OPENER_FADE_IN,
            ease: "power1.out",
          },
          s.floatAt
        );
      });

      /* ── ACT THREE — the tagline leaves, then the picture assembles. */
      if (taglineEl) {
        timeline.to(
          taglineEl,
          {
            y: -60,
            opacity: 0,
            duration: TAGLINE_EXIT_DURATION,
            ease: "power2.in",
          },
          TAGLINE_EXIT_AT
        );
      }

      tiles.forEach((tile, i) => {
        const s = starts[i];

        if (s.isOpener) {
          /* Already on screen and hovering — this is a `to`, not a
             `fromTo`, so it picks up wherever Act Two left the tile. */
          timeline.to(
            tile,
            {
              xPercent: 0,
              yPercent: 0,
              z: 0,
              scale: 1,
              opacity: 1,
              filter: "blur(0px)",
              duration: s.duration,
              ease: "power2.inOut",
            },
            s.at
          );
          return;
        }

        timeline.fromTo(
          tile,
          {
            xPercent: s.x,
            yPercent: s.y,
            z: s.z,
            scale: s.scale,
            opacity: 0,
          },
          {
            xPercent: 0,
            yPercent: 0,
            z: 0,
            scale: 1,
            opacity: 1,
            duration: s.duration,
            ease: "power2.out",
          },
          s.at
        );

        /* Blur runs as its own, shorter tween so it clears well before the
           tile lands. Two reasons, one visual and one about cost:

           Visually, the soft focus belongs to the *approach* — a tile still
           blurred as it settles just looks out of focus, whereas one that
           sharpens on the way in reads as coming into focus.

           And because blur is the only property here that forces a repaint,
           ending it early means the final settle — the part actually being
           watched — is pure composited transform. */
        timeline.fromTo(
          tile,
          { filter: `blur(${s.blur.toFixed(1)}px)` },
          {
            filter: "blur(0px)",
            duration: s.duration * 0.7,
            ease: "power1.out",
          },
          s.at
        );
      });
    }, section);

    /* ScrollTrigger caches each trigger's start/end pixel positions at
       creation time. Here it was creating them mid-layout and caching
       `start: 0, end: null` — a dead trigger whose progress never left 0,
       which is exactly what "the tiles never assemble" looked like.

       Two refreshes fix it. The first runs after the browser has finished
       the current layout pass; the second waits for the hero image, since
       an image that decodes late changes page height and invalidates every
       cached position below it. */
    const rafId = requestAnimationFrame(() => ScrollTrigger.refresh());

    const img = new Image();
    img.src = "/hero.jpg";
    const onImgSettled = () => ScrollTrigger.refresh();
    if (img.complete) {
      onImgSettled();
    } else {
      img.addEventListener("load", onImgSettled);
      img.addEventListener("error", onImgSettled);
    }

    return () => {
      cancelAnimationFrame(rafId);
      img.removeEventListener("load", onImgSettled);
      img.removeEventListener("error", onImgSettled);
      ctx.revert();
    };
  }, []);

  const tiles = [];
  for (let row = 0; row < GRID_ROWS; row++) {
    for (let col = 0; col < GRID_COLS; col++) {
      tiles.push(
        <div
          key={`${row}-${col}`}
          style={{
            backgroundImage: "url(/hero.jpg)",
            backgroundSize: `${GRID_COLS * 100}% ${GRID_ROWS * 100}%`,
            backgroundPosition: `${(col / (GRID_COLS - 1)) * 100}% ${(row / (GRID_ROWS - 1)) * 100}%`,
            backgroundRepeat: "no-repeat",
            /* The seam-killing overlap described at the top. */
            width: "101%",
            height: "101%",
            /* Promotes each tile to its own compositor layer and stops the
               1px flicker that 3D-transformed layers get in Chrome. */
            backfaceVisibility: "hidden",
            willChange: "transform, opacity",
            /* Starts invisible so the image is never briefly whole before
               JavaScript runs — the brief is explicit that it must not
               already look complete on load. */
            opacity: 0,
          }}
        />
      );
    }
  }

  return (
    /* The scroll runway. A tall block with a sticky child is what gives the
       scrub something to scrub through: the section stays pinned while the
       timeline plays out.

       560vh is the reference's own ratio — measuring produx.design gave a
       4680px sticky wrapper against an 803px hero, which is 5.83 viewports.
       The scrub maps the whole timeline onto this height, so this number
       alone sets how slow the assembly feels; every easing curve above is
       independent of it. */
    <div ref={sectionRef} className="relative h-[560vh]">
      <div
        data-hero-sticky
        className="sticky top-0 flex h-screen flex-col"
        style={{ paddingInline: "5.5vw" }}
      >
        {header ? (
          <div className="shrink-0 pt-[6vh] pb-[2vh]">{header}</div>
        ) : null}

        {/* `min-h-0` is load-bearing: a flex child defaults to
            `min-height: auto`, which refuses to shrink below its content
            and would push the grid off the bottom of the pinned screen
            instead of fitting it. */}
        {/* Sizing the grid so it always fits AND never distorts took three
            goes, and the two obvious approaches both fail:

              height:100% + max-width  → mobile rendered 334x493 (0.677)
              width:100%  + max-height → desktop rendered 1152x554 (2.08)

            In both cases one axis was pinned while the opposite cap bound,
            and `aspect-ratio` simply loses that argument — it only holds
            when exactly one axis is constrained.

            The fix is to stop capping the second axis and instead compute
            the width from the container's OWN height. `container-type: size`
            makes this element a query container, which unlocks `cqh` (1% of
            container height) as a unit. The grid asks for
            `min(100%, <ratio>cqh, 68rem)` — never wider than its box, never
            taller than the space available, never larger than the layout
            cap. Exactly one axis is ever constrained, so the ratio always
            wins. GRID_FILL scales the height cap down off a full fit, which
            is what lands the photo at roughly 70% of the screen. */}
        <div className="flex min-h-0 flex-1 flex-col pb-[4vh]">
          <div
            className="relative min-h-0 flex-1"
            style={{ containerType: "size" }}
          >
            <div
              className="absolute inset-0 flex items-center justify-center"
              style={{
                /* The 3D depth. Without a perspective the tiles' translateZ
                   does nothing visible at all — they'd just scale. */
                perspective: "1200px",
                perspectiveOrigin: "50% 50%",
              }}
            >
              <div
                ref={gridRef}
                className="grid"
                style={{
                  aspectRatio: `${IMAGE_W} / ${IMAGE_H}`,
                  width: `min(100%, ${((IMAGE_W / IMAGE_H) * GRID_FILL * 100).toFixed(2)}cqh, 68rem)`,
                  height: "auto",
                  gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`,
                  gridTemplateRows: `repeat(${GRID_ROWS}, 1fr)`,
                  /* Children keep their own 3D space rather than being
                     flattened into this element's plane. */
                  transformStyle: "preserve-3d",
                }}
              >
                {tiles}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
