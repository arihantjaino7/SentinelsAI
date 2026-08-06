# Execution plan — motion pass, then ship

> **Why this file exists:** `docs/ROADMAP.md` tracks the 18 achievements. This file
> breaks the *remaining* work — the motion/artifact-styling pass plus A18 — into small
> steps that can be done one at a time, so progress survives a cleared chat. Written
> 2026-07-31, after A17.
>
> **Source of truth for ordering:** the sequencing decision made after A17 — finish
> functional roadmap items, then the motion pass, then A18 ("hand the repo to a
> stranger"), so what the stranger receives already looks finished.

Legend — `[ ]` not started · `[~]` in progress · `[x]` done

---

## Ground rules for every step

1. **One step at a time.** Do a step, show it working, stop. Don't chain steps
   without checking in — this plan exists specifically because the work should
   *not* land in one go.
2. **Every step that changes behaviour gets verified in a real browser**, with a
   measurement where a measurement is possible — not "the code looks right."
3. **Learning notes are non-negotiable** (`CLAUDE.md`). The motion pass gets notes
   in the `17b`, `17c`, ... series (it isn't a numbered achievement); A18 gets note
   `18`. A note may cover one step or a few closely-related steps, but no concept
   ships unexplained.
4. **Passive-only scope is unchanged.** Nothing in this plan sends new traffic to
   anyone's site.

---

## Part A — Motion / artifact-styling pass

Closes the gap recorded during A16: `docs/DESIGN.md` calls for glass panels drifting
on scroll and names screen 2 "the set piece... where the animation budget goes".
Neither existed as of A17.

### `[x]` A-0 — Commit the drift hook already built
Built and verified on 2026-07-31. Committed as `e567d35`:
`frontend/lib/useScrollDrift.ts`, the hook applied to `AgentLog.tsx`, and
`docs/learning/17b-scroll-drift-and-refs.md`.
Verified live: panel `translateY` measured at exactly `scrollY × 0.06`.

### `[x]` A-1 — Give the report's other panels their own drift speeds
Built and verified 2026-07-31. The score-ring header (0.03) and each findings
category (0.08, via a new `FindingsCategory` component) now drift alongside
`AgentLog`'s existing 0.06 — three distinct, measured rates.
A real bug was found live (not just "expect to tune numbers" — it actually broke):
drifting the whole findings list as one block, uncapped, overlapped the "Agent log"
heading once scrolled to the bottom of a real report. Fixed by giving
`useScrollDrift` an optional `maxOffsetPx` clamp (backward-compatible — `AgentLog`'s
existing uncapped call is untouched) rather than tuning speeds against one report's
length. Verified live at the real bottom of a `wordpress.org` scan (`scrollY` 2464):
both new drifts read their exact cap values (32px, 48px) with a positive gap
remaining before the next heading. Note:
[`learning/17c-drift-speeds-and-clamping.md`](learning/17c-drift-speeds-and-clamping.md).

### `[x]` A-2 — Style findings evidence as inspection artifacts
Built and verified 2026-07-31. `FindingRow`'s `evidence` field now sits inside a
bordered, frosted `.glass` box with an "EVIDENCE" label above it, instead of a plain
muted paragraph — reusing the same panel utility `AgentLog` and the PDF button
already use, no new CSS. Verified live against a real `wordpress.org` scan: the
missing-CSP evidence, the `X-Content-Type-Options` evidence, and the Recon agent's
raw `<meta name="generator">` tag (rendered as literal text, not executed — the
same escaping guarantee A17 verified) all read as attached exhibits. No new
concepts needed — purely composition of `.glass` and conditional rendering, both
already covered; the note says so directly rather than manufacturing one. Note:
[`learning/17d-findings-evidence-as-artifacts.md`](learning/17d-findings-evidence-as-artifacts.md).

### `[x]` A-3 — Screen 2: the set piece
Built and verified 2026-07-31. The waiting state is now a new
`frontend/components/ScanProgress.tsx`: five glass panels, one per agent, dim and
"Waiting…" until that agent's real SSE result lands, at which point React remounts
that one panel (a deliberate `key` change from `"name-waiting"` to `"name-done"`)
and a new `materialize-in` CSS animation (`globals.css`) plays on it. No artificial
stagger — the real arrival order and timing (A11/A16) *is* the stagger. Verified
live: submitted a real scan and read `getComputedStyle` on a waiting panel mid-scan,
confirming the animation genuinely runs (`animationName: "materialize"`,
`0.55s`, the exact easing curve) rather than just having the class name present;
separately confirmed via `document.styleSheets` that the nested
`@media (prefers-reduced-motion: reduce)` override survived Tailwind's build and
sets `animation: none`. Checked both the 2-column mobile-width grid and the
5-across desktop-width grid live. Note:
[`learning/17e-the-set-piece.md`](learning/17e-the-set-piece.md).

### `[x]` A-4 — Learning note for A-1 → A-3
Superseded by writing one note per step as each was built, matching `CLAUDE.md`'s
own "one note per achievement" rule more closely than this plan's original
"maybe one combined note" guess:
[`learning/17c-drift-speeds-and-clamping.md`](learning/17c-drift-speeds-and-clamping.md) (A-1),
[`learning/17d-findings-evidence-as-artifacts.md`](learning/17d-findings-evidence-as-artifacts.md) (A-2),
[`learning/17e-the-set-piece.md`](learning/17e-the-set-piece.md) (A-3). Recorded here
so the deviation from this plan's original guess is explicit, not silent.

---

## Part B — A18: Ship it

Roadmap definition: "Hand the repo to a stranger and have them run it."
**Nothing here exists yet** — there is no root README at all.

### `[x]` B-1 — Root `README.md`
Built and verified 2026-07-31. Root `README.md` didn't exist before this step —
now covers what Sentinels is, the passive-only ethic (stated up front, with the
concrete never-list: no SQLi, no brute force, no fuzzing, no form submission,
no DoS traffic), the five-agent table, tech-at-a-glance, and a minimal run
quickstart. Two real screenshots (`docs/images/input-screen.png`,
`docs/images/report-screen.png`) were captured against the actual running
app — not mocked up — via a small Playwright script driving the real dev
frontend against the real backend, scanning `wordpress.org` end-to-end (both
screens chosen per Arihant: input screen and report screen, not just one).
The quickstart intentionally stops short of full setup detail (including the
Playwright-for-PDF gotcha) — that's B-2's job — and says so via an inline note
rather than linking a doc that doesn't exist yet.
**Done when:** someone who has never seen the repo understands what it does without
opening `docs/`. ✓

### `[x]` B-2 — Setup + run instructions
Built and verified 2026-07-31. Folded into the root README's "Running it"
section (rather than a separate doc) so B-1's "done without opening `docs/`"
bar still holds — exact Windows/PowerShell commands for both halves: create
venv, `pip install -r requirements.txt`, `playwright install chromium`,
`uvicorn main:app --reload`; then `npm install` + `npm run dev` for the
frontend.
**The gotcha was verified, not assumed:** temporarily renamed the machine's
cached `ms-playwright/chromium-*` directories, ran a real scan of
`example.com`, then POSTed the real report to `/scan/pdf` — reproduced the
exact real failure a stranger who skips `playwright install chromium` would
hit: a bare `500 Internal Server Error` with zero detail on the client side,
while the backend's own terminal log carries the real explanation
(`Executable doesn't exist at ...`, Playwright's own `playwright install`
tip). Directories restored immediately after, then `/scan/pdf` re-verified
working (real `200`, valid 3-page PDF) before moving on. This is the exact
failure text now quoted in the README.
**Full literal from-scratch verification (fresh clone, no insider knowledge)
is B-5's job** — B-2 only covers writing correct, exact commands plus proving
the one gotcha for real; not re-scoped to also do B-5's work early.
**Done when:** the instructions have been followed literally, from scratch, and work.

### `[x]` B-3 — Environment variable docs
Built and verified 2026-07-31. `backend/.env.example` rewritten from a bare
`GROQ_API_KEY=` into a commented file: what the key powers (`ai/analyst.py`'s
summary paragraph, and *only* that), where to get a free one
(`console.groq.com/keys`), and — the important part — that this is entirely
optional, cross-checked directly against `analyst.py`'s real behavior
(`os.environ.get("GROQ_API_KEY")`, empty string returned on missing key or any
API failure, never raises). Confirmed `.env` itself (not `.env.example`) is
already gitignored via the root `.gitignore` (`git check-ignore -v backend/.env`
→ matched), so no real key is at risk of being committed. No real key was
pasted anywhere, including here.
**Never:** paste a real key anywhere. `.env` stays gitignored. ✓

### `[x]` B-4 — Replace `frontend/README.md`
Built and verified 2026-07-31. Replaced the untouched `create-next-app`
boilerplate (which advertised the Geist font — never used here) with a short,
accurate local README: quick start, a real structure map (`app/page.tsx`,
`components/`, `lib/api.ts`, `lib/useScrollDrift.ts`), and the actual three
type roles this project uses (Instrument Serif / JetBrains Mono / Inter),
cross-checked directly against `app/layout.tsx` rather than assumed. Points
back to the root README for full setup instead of duplicating them, so the
two docs can't drift apart. Both relative links (`../README.md`,
`../docs/DESIGN.md`) confirmed to resolve.
**Do:** replace with something true, or delete it and let the root README cover it. ✓

### `[x]` B-5 — Verify as a stranger would
Done 2026-07-31, and it **earned its place** — it found a real bug.

Ran literally, from a genuine `git clone` (tracked files only — no `.venv`,
no `node_modules`, no `.env` carried over), following only what B-1→B-4 wrote
down: `python -m venv .venv` → `pip install -r requirements.txt` →
`playwright install chromium` → `uvicorn main:app --reload`, then
`npm install` → `npm run dev`. Both halves came up and a real scan of
`python.org` completed end-to-end in the browser (69/100, grade D).

**The bug:** the documented `uvicorn main:app --reload` silently breaks PDF
export on Windows. `--reload` makes uvicorn switch the process to
`WindowsSelectorEventLoopPolicy` (its own `uvicorn/loops/asyncio.py`, gated on
`use_subprocess`), and a Selector loop cannot start a subprocess — which is
exactly what Playwright must do to launch a browser. Result: a blank
`500 Internal Server Error`, with a bare, message-less `NotImplementedError`
visible only in the server's terminal. Isolated by testing the same clone with
and without the flag (without `--reload`: real 200, valid PDF; with it: 500).

**Fixed in code** (Arihant's call, chosen over documenting a `--reload`
caveat): `backend/report/pdf.py` now runs the Playwright work on an explicit
`asyncio.ProactorEventLoop` inside `asyncio.to_thread`, on Windows only.
Built directly rather than via `new_event_loop()` — the policy is the very
thing uvicorn overrode. Verified under the previously-failing exact command:
real 200 + valid PDF via `curl` and via the real browser's Download PDF
button. Also measured that the fix doesn't block the server: `/health`
answered 9 times at 2–3ms each *during* a 2209ms PDF render.
Two rejected alternatives were tested, not assumed — resetting the policy from
`main.py` (too late; uvicorn's loop already exists before our app is imported)
and Playwright's `sync_api` in a thread (fails identically; it builds its loop
from the same policy). Note:
[`learning/17f-event-loops-and-the-reload-trap.md`](learning/17f-event-loops-and-the-reload-trap.md).

**One environment caveat, not a project bug:** the first clone attempt was made
inside a deeply-nested temp directory and Turbopack panicked on Windows'
path-length limit. Re-run from a short path (`C:\stest`) it was clean — worth
knowing, but nothing to fix in the repo.

**Done when:** a fresh clone runs both halves and completes a real scan with no
undocumented step. Anything that needed insider knowledge goes back into the docs. ✓

### `[x]` B-6 — Learning note 18 + close out the roadmap
Done 2026-07-31.
[`learning/18-shipping-and-clean-room-verification.md`](learning/18-shipping-and-clean-room-verification.md)
covers what A18 actually taught: a README as a contract with a reader who has
none of this project's context, clean-room verification as testing the
*instructions* rather than the code (and why you can't verify your own
instructions on your own already-set-up machine), and `.gitignore` read as a
manifest of everything a clean clone has to rebuild. `docs/ROADMAP.md` marked
A18 `[x]` (18/18) with a full B-1→B-6 summary in "Current position"; the
`docs/ACTIVITY_LOG.md` entry for A18 added, covering all six steps in one
achievement-level entry to match the log's existing granularity.
**Done when:** the roadmap shows 18/18 and the project is genuinely finished. ✓

---

## Open questions to settle when we reach them

- **A-3 scope — settled.** Built as one pass (not split into A-3a/A-3b): five glass
  panels with a single mount-triggered entrance animation, staggered only by the
  real SSE arrival order. No separate "panel layout" vs "animation" step was needed
  since the two were small enough to design and verify together.
- **B-1 screenshot — settled.** Both: input screen and report screen, captured
  2026-07-31 (see B-1 above).
- **Deployment:** the roadmap's A18 says "run it," not "deploy it." Treating hosting
  as out of scope unless Arihant says otherwise.
