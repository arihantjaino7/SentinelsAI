# Sentinels — working conventions

AI-powered **passive** website security auditor. URL in → 8 agents scan concurrently →
0–100 score + A–F grade + plain-language report, in under 60 seconds.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the 18-achievement build order and current position.

## Non-negotiable: scope

Sentinels does two different things to two different kinds of resource. Keep them apart.

**Targets are observed passively, never touched.** Reading response headers, TLS config,
DNS records, and GET requests to public paths. Never send attack traffic — no SQLi, no
brute force, no fuzzing, no DoS, no automated form submission. This is a
defensive/educational tool. If a feature idea requires sending something harmful, it's
out of scope.

**Connected repositories may be written to, but only with explicit authorization.**
A repo the user has deliberately connected (GitHub App installation) can receive a
branch, a commit, and a pull request. That is not a contradiction of the rule above —
it is a write to the user's *own* resource, requested by them, reviewed by them before
it merges. Everything about how those writes are allowed to happen is in the
remediation non-negotiable below.

## Non-negotiable: bounded probing

Every agent declares a hard cap on how many requests it may issue against a target,
and a wall-clock deadline (see `backend/agents/probe.py`'s `Budget`). No check may
loop over an unbounded list. Caps are constants at the top of each agent file so
they can be read in five seconds. Exhausting a budget stops further probing and
reports itself honestly (`*-scan-partial`) — it is never a silent truncation.

## Non-negotiable: confidence is stated, never implied

Any finding that can't be proven from what was observed says so — in its title
("Potential…"), in its wording ("manual verification recommended"), and in
`Finding.confidence` (0.0–1.0, `None` = certain/not applicable). A guess is never
upgraded into a claim. A CNAME pointing at a known hosting provider, for example,
is never on its own a "takeover" — see `backend/agents/takeover_signatures.py`.

## Non-negotiable: remediation (autofix)

See [`docs/PLAN-v5.md`](docs/PLAN-v5.md) for the build order. These ten rules govern
every line of `backend/remediation/`:

1. **The LLM never generates a security patch.** Not a diff, not a config block, not a
   line rewrite. It writes explanations only.
2. **Fixes are deterministic.** A fixer is plain Python: same finding, same repo state,
   same patch, every time — and unit-testable with no network and no model.
3. **No deterministic fixer means suggest-only.** A finding without one keeps the AI
   explanation and nothing else. Never force an autofix because it would look impressive.
4. **Never commit to a default branch.** Sentinels creates its own `sentinels/…` branch
   or it does nothing.
5. **Always a pull request.** Never a direct push, never a merge, never a force-push,
   and never a write to a branch Sentinels did not create.
6. **Always preview before pushing.** The exact diff is shown and the user explicitly
   approves. Silent application does not exist.
7. **Drift aborts.** If a file's blob SHA changed since the plan was made, stop and ask
   for a re-plan. Never overwrite work that arrived after planning.
8. **Uncertain findings are never auto-applied.** Anything with a `confidence` set, any
   `*-scan-partial`, and every Tier 3/4 finding is manual-only.
9. **Every PR says what it does *not* fix.** Especially secret removal: removing a
   committed secret does not rotate it and does not erase it from git history, and the
   PR body must say so in full.
10. **Every write is audited.** Who, which repo, which branch, which files, which
    finding, what happened — one row, every time.

## Non-negotiable: verification closes the loop

A fix is not "done" when a PR opens. After the merge, re-run the responsible agent and
show the real result: FAIL → PASS, and the score delta from the untouched deterministic
`calculate_score`. Never report a fix as working on the strength of having written it.
Never let a model compute the score.

## Non-negotiable: every change gets explained

This project is a learning exercise as much as a build. **No code lands without its
learning note.**

- One note per achievement: `docs/learning/AN-name.md`
- Format is defined in [`docs/learning/00-how-to-use-these-notes.md`](docs/learning/00-how-to-use-these-notes.md) — follow it exactly
- Every new concept needs a **tiny standalone example** (3–10 lines, runnable alone,
  about something ordinary — not about security) *before* the real code is shown
- Show rejected alternatives and why they lost, not just the final choice

## Calibration for this developer

- **Python:** comfortable with normal Python. **async/await, the event loop, and
  coroutines are new** — explain those from first principles, every time they appear.
  Don't re-explain functions, loops, or basic classes.
- **JavaScript/React:** new to both. When Act 4 starts, explain JS syntax and React
  concepts (components, state, props, hooks) from the ground up.
- **Workflow:** Claude writes the code and the note together; the developer reads,
  runs, and asks. Explain before writing, not after.

## Code style

- Comments explain **why**, not what. Assume the reader knows Python syntax but not
  the security domain — so `# HSTS missing means a downgrade attack is possible` is
  useful, `# loop through the headers` is noise.
- Agents must never crash the scan. Every agent catches its own exceptions and reports
  them via `AgentResult.error`.
- Scoring stays **deterministic** — no model in the loop. Same site, same score, always.
- The AI layer only *enriches*. If `GROQ_API_KEY` is missing or the call fails,
  the scan must still produce a complete report.

## Working discipline

- **Don't modify unrelated code.** Touch what the task needs and nothing else. No
  drive-by refactors, no reformatting a file you happened to open, no "while I'm here"
  changes to UI or tests that the task didn't ask about.
- **Run the tests after every stage**, not just at the end:
  `cd backend && ./.venv/Scripts/python.exe -m pytest tests -q`. A stage isn't finished
  until they're green. Never weaken or delete an existing test to make a new one pass.
- **The plan document is the specification.** When implementation reality conflicts with
  [`docs/PLAN-v5.md`](docs/PLAN-v5.md), say so and get the conflict confirmed, then
  update the plan. Never silently change the architecture to route around a surprise.
- **Keep responses concise.** Report what changed and what it cost. Skip the preamble,
  the recap of what was just read, and the list of options not taken.

## Layout

```
backend/    FastAPI app, agents/, ai/, remediation/, auth/, report/
frontend/   Next.js App Router + Tailwind
docs/       ROADMAP.md + PLAN-v5.md + learning/ notes
```
