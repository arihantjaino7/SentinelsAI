# Continuing work on another laptop

A short checklist for picking this project back up on a different machine —
git specifics, environment setup, and where to find "what's done, what's
next." For the full local run instructions (installing dependencies,
starting the servers), see [`../README.md`](../README.md#running-it) — this
file only covers what's *different* about a second machine.

## 1. Get the code

```bash
git clone https://github.com/arihantjaino7/sentinels.git
cd sentinels
git checkout master
```

**Important — the branch you want is `master`, not `main`.** GitHub's
default branch on this repo is `main`, so a plain `git clone` checks out
`main` by default — that branch is old and doesn't have any of the v2/v3
work. All real development lives on `master`. There's also a third branch,
`github-release`, which is unrelated and can be ignored.

If you already have a clone from before, just:

```bash
git checkout master
git pull
```

## 2. Recreate the environment secrets

`.env` files are gitignored on purpose — they never get committed, so
they don't exist on a fresh clone. Recreate `backend/.env` by copying the
example and filling in your own key **directly in the file**, not in chat
(a Groq key has leaked into a commit before by being pasted where it
shouldn't have been — see `docs/ACTIVITY_LOG.md` around 2026-07-30):

```bash
cd backend
cp .env.example .env
# open .env and paste GROQ_API_KEY=... yourself
```

This is optional — the app runs fully without it, just without the AI
summary (per `CLAUDE.md`'s AI-is-optional guarantee).

## 3. Install and run

Follow [`README.md`'s "Running it" section](../README.md#running-it) exactly
— backend venv + `pip install` + `playwright install chromium`, frontend
`npm install`. Nothing about that differs machine to machine.

## 4. Find out where things stand

- **`docs/PLAN-v3.md`** — the status line at the very top says exactly what
  phase/milestone is done and what's next. This is the first thing to read.
  As of this handbook update: Phases R-A through R-D (R11) are all done —
  live URL scans and GitHub repo scans both work end-to-end, streaming
  progress included. Only **R12** (the file-tree browser) is left.
- **`docs/learning/`** — every concept, numbered in the order it was built
  (currently up to 45). Read in order the first time; use as reference after.
- **`docs/ROADMAP.md`** / **`docs/PLAN-v2.md`** — the original v1 and v2
  build plans, both fully shipped; kept for history.

## 5. Keep both machines in sync

Simple two-machine git hygiene:

- **Before starting work**, always `git pull` first, so you're not building
  on top of a stale copy.
- **Commit and push in reasonably small chunks** rather than hoarding a huge
  uncommitted diff — the whole point of pushing is that the other laptop can
  pick up mid-stream.
- **Never force-push** `master` (`git push --force`) unless you know exactly
  why — it can overwrite work sitting on the other machine that you haven't
  pulled down yet.
- If both machines somehow end up with unpushed commits at once, `git pull`
  will ask you to merge (or rebase) — resolve that before pushing, don't
  discard either side blindly.

## 6. Starting a new session

Just say what you want to work on, or say "start R12" / whatever the next
milestone in `docs/PLAN-v3.md` is — that file has enough context (what's
done, what's next, and any design decisions already made) to pick up
directly without re-explaining the whole project. Right now that's **R12,
the file-tree browser** — the last milestone in the v3 plan.

## 7. A real gotcha worth knowing before you start a session

If a live scan in the browser ever fails with **"Inspection failed — Lost
connection to the scanner"**, don't assume the code is broken — check
whether the backend on port 8000 is actually serving current code first:

```bash
curl http://localhost:8000/repo/agents
```

If that 404s, the process listening on port 8000 is stale (running old
code from before a restart) or something else already holds that port.
On Windows, if `Get-Process -Id (Get-NetTCPConnection -LocalPort 8000
-State Listen).OwningProcess` can't find the PID it just reported — a real,
reproducible quirk hit while building R11 — stop trying to kill it and
just run the backend on a different port instead (`--port 8010`), then
point the frontend at it via `frontend/.env.local`:

```
NEXT_PUBLIC_API_BASE=http://localhost:8010
```

Restart the frontend dev server (not just a page refresh) after adding
that file.
