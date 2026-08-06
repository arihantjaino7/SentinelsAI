# 41 — Extending the Repo Hygiene agent

> **Status:** done. `HygieneAgent` now checks five more things beyond
> README/LICENSE: lockfile, tests, CI, `.env.example`, large files.

## What we built

R2 shipped `HygieneAgent` with two checks, deliberately kept small to prove
the repo-agent wiring worked. This milestone adds the rest: is a lockfile
committed next to its manifest, are there any test files, is CI configured,
is a `.env.example` provided, and are there any suspiciously large files.
Same file, same class — no new concept needed, just more checks in the
same PASS/WARN shape README and LICENSE already used.

## The one idea worth naming: some checks only apply sometimes

Every check up to now ran unconditionally. The lockfile check is different:
it only makes sense if there's something to have a lockfile *for*. A pure
Python repo with no `package.json` shouldn't be dinged for missing
`package-lock.json` — there's no npm project there to have one.

```python
def check_tire_pressure(vehicle):
    if not vehicle.has_tires:   # e.g. a boat
        return None             # the check doesn't apply -- not a pass, not a fail
    return "ok" if vehicle.tire_psi > 20 else "low"
```

`_check_lockfiles` does exactly this: it only appends a finding for the npm
lockfile if `package.json` was found, and only for the Python lockfile if
`pyproject.toml`/`Pipfile` was found. If neither manifest exists, neither
finding is produced at all — not a pass, just silently not applicable.

## The other four checks, briefly

- **Tests** — any file under a `tests/`/`__tests__/` path, or named like
  `test_*.py` / `*.spec.js`, counts as "tests exist."
- **CI** — any `.github/workflows/*.yml` file, or a handful of other common
  CI configs (`.gitlab-ci.yml`, `.travis.yml`, ...).
- **`.env.example`** — same filename set R4's secrets agent already
  excludes from scanning (`.env.example`/`.env.sample`/`.env.template`/
  `.env.dist`) — here their *presence* is the good sign, not their absence.
- **Large files** — anything over 1 MB. `fetch.py`'s binary-extension list
  already filters out obvious images/videos/archives at extraction time,
  but a large `.csv`, `.pkl`, or ML model file with a less common extension
  sails right through that filter and still bloats every future clone.

## Try it

```bash
cd backend && .venv/Scripts/python.exe -c "
from agents.repo.hygiene import HygieneAgent
print(HygieneAgent.checks)
"
```

- Create a repo with only a `pyproject.toml` (no `package.json`) — the npm
  lockfile finding never appears, but a missing `poetry.lock` still does.
- Add a 2 MB file — it's flagged by path and size, even if every other
  check passes.
- Re-run against a real repo with no tests/CI/`.env.example` at all — the
  scan still completes cleanly, just with more `WARN` findings.

## Words worth knowing

- **Conditional check** — one that only runs, and only counts, when its
  precondition is actually true for this particular repo.

---

Phase R-B (the five repo agents: R4 secrets, R5 dependencies, R6 config, R7
patterns, R8 this one) is now complete. **Next:** R9 — the repo checklist
and readiness score (Phase R-C), turning these findings into the same
pass/warn/fail deployment-readiness view the URL side already has.
