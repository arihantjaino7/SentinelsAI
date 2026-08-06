# 18 — Shipping: docs as a contract, and clean-room verification

> **Status:** done. Roadmap complete, 18/18. A real README exists, and the
> setup instructions in it have actually been proven to work.

## What we built

Achievement 18 was "hand the repo to a stranger and have them run it." That
meant: a real root `README.md` (what Sentinels is, the passive-only rule,
two real screenshots, setup steps), a documented `backend/.env.example`, a
proper `frontend/README.md`, and — the part that actually mattered — a
genuine clean-room test: cloning the repo fresh, onto a machine with none
of this project's history, and literally typing only the documented
commands. That test found a real bug (the event-loop trap in
[`17f`](17f-event-loops-and-the-reload-trap.md)), which got fixed and then
re-verified the same way.

## The one big idea: you can't trust your own machine to check your own instructions

Every other learning note tested whether the *code* works. This one is
about testing whether the *instructions* work — and that's a different
kind of test, because of one specific trap:

**Your own machine already has everything installed.** If the README
forgets a step, your machine won't notice, because it already has that
thing from six months of working on this project (or some other project
entirely). The gap is invisible from exactly the computer you're writing
the instructions on.

Think of it like writing a recipe from memory for a dish you've made fifty
times. You know, without needing to be told, that the pan needs greasing —
your hands just do it. So you never write "step 0: grease the pan." Someone
following your recipe exactly, for the first time, ends up with dinner
fused to the pan. The recipe isn't wrong about anything it says — it's
missing something it assumed.

You can't fix this by rereading the recipe more carefully; you already
believe it's complete. The only fix is handing it to someone (or
something) that has never greased that pan — a genuinely fresh kitchen. For
this project, that meant an actual `git clone` into a brand-new folder that
had never had `.venv` or `node_modules` in it, and running only the exact
commands the README says to run.

That's exactly how the `--reload` PDF bug in `17f` was found. Every prior
achievement's testing happened on a machine that already had Chromium
installed and had never combined `--reload` with Playwright in that
specific way — so nothing before this ever had a reason to hit it. The
clean-room run did, on the first try.

## A quick way to check your own setup docs

Everything a clean-room clone is missing is, by definition, everything
`.gitignore` lists. So a useful check is: read `.gitignore` top to bottom
and confirm each line has a matching command in the README that rebuilds
it.

```
.venv/          <- python -m venv .venv && pip install -r requirements.txt
node_modules/   <- npm install
.env            <- copy from .env.example, never committed
```

If something's gitignored but has no rebuild instruction anywhere, that's
the exact kind of gap clean-room testing exists to catch.

## Try it

- Pick any project you've had set up a while. Write its setup steps from
  memory, without opening the README. Then compare against its actual
  `.gitignore` — something will be missing. That's the point, not a
  personal failing.
- For this project, check that each `.gitignore` line above really does
  have a matching command in the root `README.md`.
- Read [`17f`](17f-event-loops-and-the-reload-trap.md) for the concrete bug
  this exact process caught.

## Words worth knowing

- **Clean-room verification** — testing written instructions by following
  them literally, on a machine that's never benefited from any undocumented
  setup already sitting on your own.
- **The invisible-step trap** — a setup step you do automatically, without
  writing it down, because your own machine already satisfies it.
- **`.gitignore` as a checklist** — every gitignored path is something a
  fresh clone won't have; each one should map to a written command that
  rebuilds it.

---

**Next:** nothing queued — the roadmap is complete (18/18).
