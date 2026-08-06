# 42 — Repo checklist and readiness score

> **Status:** done. Every repo scan now produces a 17-item deployment
> checklist, a readiness score, and a deployment status — the same
> pass/warn/fail/blocked view the URL side has had since note 27, reusing
> the exact same pure evaluator underneath. Verified with two real scans of
> `octocat/Hello-World`: identical checklist, readiness score, and
> deployment status both times.

## What we built

`backend/checklist/repo_rules.py` — 17 rules covering secrets, `.env`
hygiene, vulnerable dependencies, README/LICENSE/tests/CI presence, risky
code patterns, Dockerfile/CI hardening, and four self-attested questions
Sentinels genuinely can't check passively (branch protection, 2FA, ...).
`evaluator.py`'s `evaluate()` and `compute_readiness()` both gained a `rules`
parameter so the same pure functions serve both scan types. And — the part
`docs/PLAN-v3.md` flagged up front but didn't assign a milestone to — a
repo scan needed something to actually *run* end to end before any of this
could be verified, so this milestone also adds `repo_orchestrator.py` and
`POST /repo/scan`, the repo-side sibling of `orchestrator.py` and `POST /scan`.

## The one idea worth naming: not every check has one fixed name

Every URL-side checklist rule looks up *one* finding by its exact,
always-the-same id — `missing-csp` is always `missing-csp`. Repo findings
aren't so tidy: the secrets agent gives every leaked key its own id
(`secret-aws-key-.env-L3`, `secret-groq-key-config.py-L12`, ...), because two
different leaks are two different problems, not one. There's no single fixed
id for "this repo has secrets" to look up.

Standalone example — the difference between "find one thing" and "find any
matching thing":

```python
students = [
    {"id": "alice", "grade": "A"},
    {"id": "bob-quiz-3", "grade": "F"},
    {"id": "bob-quiz-7", "grade": "F"},
]

# "find THE one with this exact id" -- works when there's only ever one
def find_alice(students):
    return next((s for s in students if s["id"] == "alice"), None)

# "find ANY that failed" -- works when there can be zero, one, or many
def any_failing(students):
    return [s for s in students if s["grade"] == "F"]
```

`checklist/rules.py`'s `_from_finding` is `find_alice` — one exact id in,
one state out. `repo_rules.py` adds `_any`, which is `any_failing` with two
extra filters (`category`, `id_prefix`) so it can answer "does this repo
have *any* Secrets finding at all" or "any Dockerfile issue" without caring
how many or what their ids happen to be:

```python
def _eval_no_secrets(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, category="Secrets")
    if not hits:
        return "pass", "No committed secrets were found.", ""
    return "fail", f"{len(hits)} possible secret(s) committed...", "..."
```

Three of the four inferred-tier rules (`repo_dockerfile_hardened`,
`repo_ci_workflow_safe`, `repo_no_large_files`) use the same `_any` with an
`id_prefix` instead of a `category`, since a Dockerfile issue and a CI issue
both live under `category="Configuration"` but need to be counted separately
— the id prefixes (`docker-` vs `ci-`) are what tell them apart.

## A second, smaller wrinkle: "fail" can mean "the thing that would tell us is missing"

`ConfigAgent._check_gitignore` (R6) has a branch: if there's no `.gitignore`
file *at all*, it emits one `gitignore-present` finding and stops — it never
gets to emit `gitignore-env` or `gitignore-private-keys`, because there's
nothing to check a pattern against. A naive `_from_finding(findings,
"gitignore-env")` would see that id is simply absent and default to `"pass"`
— which is backwards. No `.gitignore` is the *worst* case for ".env is
gitignored," not a pass.

```python
def _eval_env_gitignored(findings):
    missing = _find(findings, "gitignore-present")
    if missing is not None and missing.status == Status.FAIL:
        return "fail", "This repository has no .gitignore file at all, ...", "..."
    return _from_finding(findings, "gitignore-env")
```

This is exactly what the real `octocat/Hello-World` scan below hits — it has
no `.gitignore`, so both `repo_env_gitignored` and
`repo_private_keys_gitignored` correctly came back `"fail"`, which is what
pushed `deployment_status` to `"blocked"` (both are `blocking=True`).

## Threading a `rules` parameter through a pure function

```python
def evaluate(findings: list[Finding], rules: list[ChecklistRule] = RULES) -> list[ChecklistItem]:
    ...
```

Note 22 already covered why `Field(default_factory=list)` exists — a mutable
default is dangerous *when the function mutates it*. `evaluate` never
mutates `rules`, only iterates it, so a plain `= RULES` default is fine here:
every URL-side caller that already calls `evaluate(findings)` keeps working
with zero changes, and `repo_orchestrator.py` is the one caller that passes
`rules=REPO_RULES` explicitly. `compute_readiness` got the identical
treatment — it used to `import RULES` from inside the function body just to
look up each item's `blocking` flag; now that lookup uses whichever `rules`
list the caller passed in.

## Try it

```bash
# Scan the same repo twice, diff the parts that must be identical
curl -s -X POST localhost:8000/repo/scan -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/octocat/Hello-World"}' > scan1.json
curl -s -X POST localhost:8000/repo/scan -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/octocat/Hello-World"}' > scan2.json
python3 -c "
import json
a, b = json.load(open('scan1.json')), json.load(open('scan2.json'))
print(a['readiness_score'] == b['readiness_score'])   # True
print(a['deployment_status'] == b['deployment_status'])  # True
print(a['checklist'] == b['checklist'])                # True
"
```

Real result from this exact run: score 80/100 (grade B), readiness 33/100,
`deployment_status: "blocked"` — because Hello-World has no `.gitignore` at
all, tripping both blocking `.gitignore` rules. Every one of the 17 checklist
rows matched byte-for-byte between the two runs.

- Scan a URL afterward (`POST /scan`) and confirm it still returns exactly
  16 checklist items, same as before this milestone — `rules` defaulting to
  `RULES` means the URL path is untouched.
- Try a repo with a `package.json` but no lockfile — `repo_no_large_files`
  and friends still evaluate cleanly even though that particular manifest
  check lives in a different agent (R8) than the checklist rule reading it.

## Words worth knowing

- **id prefix matching** — grouping several dynamically-generated finding
  ids (`docker-latest-tag-...`, `docker-root-user-...`) under one checklist
  row by checking `finding.id.startswith("docker-")` instead of an exact match.
- **Fallback evaluation** — checking a *different, prior* finding first
  (`gitignore-present`) to correctly interpret the *absence* of the finding
  you actually wanted (`gitignore-env`).

---

Phase R-C continues with **R10** — a repo-flavoured AI summary that leads
with the real mistake, and a fix prompt whose examples are code diffs
instead of Apache/Nginx config blocks.
