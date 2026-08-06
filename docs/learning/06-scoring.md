# A6 — Scoring

> **Status:** done. `backend/scoring.py` turns a list of findings into a 0-100 score,
> an A-F grade, and a per-severity count.

## What we built

`backend/scoring.py` — three small functions:

- **`calculate_score(findings)`** — starts at 100, subtracts a penalty for every
  finding that isn't a clean pass, and never goes below 0.
- **`grade_for_score(score)`** — turns that number into a letter grade using a fixed
  table of cutoffs (90+ is A, 80+ is B, and so on).
- **`count_by_severity(findings)`** — how many non-passing findings fall into each
  severity bucket, so the report can say "2 High, 2 Medium."

`orchestrator.py` calls all three and puts the real values into the report.

## The one big idea: pure functions

A function is **pure** if, given the same input, it always gives the same output —
and it doesn't change anything else while it runs (no printing, no saving to a file,
no checking the clock).

```python
import random

def add(a, b):
    return a + b                    # PURE: same a, b -> always same result

def add_with_bonus(a, b):
    return a + b + random.randint(0, 5)   # NOT pure: different result every call
```

`calculate_score` is written like `add`. That's exactly what CLAUDE.md means by
"scoring stays deterministic — same site, same score, always." It's not just a
promise — `scoring.py` doesn't even import anything that *could* break it (no
`httpx`, no `datetime.now()`, no AI calls). This also means you can test it with a
plain list of fake findings, no server or internet needed — see "Try it" below.

## The actual code

```python
def calculate_score(findings: list[Finding]) -> int:
    penalty = sum(
        SEVERITY_PENALTY[finding.severity]
        for finding in findings
        if finding.status != Status.PASS   # FAIL and WARN both cost something
    )
    return max(0, 100 - penalty)   # never go below 0
```

`max(0, ...)` is called "clamping" — it stops the score from going negative. Five
failed `Critical` checks would otherwise do `100 - 125 = -25`, which is meaningless
to show a user. `max()` just picks the bigger of the two numbers, so once the
subtraction goes below zero, `0` wins instead.

```python
_GRADE_THRESHOLDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D")]

def grade_for_score(score: int) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"
```

Checked **highest first**, on purpose — if the list were reversed, a score of 95
would match `>= 60` first and wrongly come back "D".

```python
def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in Severity}   # every bucket starts at 0
    for finding in findings:
        if finding.status != Status.PASS:
            counts[finding.severity.value] += 1
    return counts
```

That `{severity.value: 0 for severity in Severity}` line is a **dict comprehension**
— it pre-fills every severity (Critical, High, Medium, Low, Info) at 0 before
counting anything. Without it, a perfectly clean site would return `{}`, and the
frontend couldn't tell "everything passed" apart from "nothing was checked."

## Try it

Run scoring with zero network involved — the actual point of it being pure:

```bash
cd backend
./.venv/Scripts/python.exe -c "
from models import Finding, Severity, Status
from scoring import calculate_score, grade_for_score, count_by_severity
findings = [Finding(id='a', title='t', category='Test', severity=Severity.HIGH, status=Status.FAIL)]
score = calculate_score(findings)
print(score, grade_for_score(score), count_by_severity(findings))
"
```

- Build ten fabricated `Critical`/`FAIL` findings and confirm the score clamps at `0`.
- Temporarily reverse `_GRADE_THRESHOLDS` and call `grade_for_score(95)` — wrong grade
  comes back, proving the ordering matters. Put it back after.
- Scan the same site twice via `/scan` and confirm the score is identical both times.

## A couple of words worth knowing

- **Pure function** — same input always gives the same output, no side effects.
- **Deterministic** — one correct output per input, decided by fixed rules.
- **Clamping** — forcing a number to stay in a valid range (`max(0, ...)`).
- **Dict comprehension** — `{key: value for x in iterable}`, builds a dict in one line.

---

**Next:** Act 2 begins — A7, the Recon agent. This is where HTML parsing
(`BeautifulSoup`) enters the project for the first time.
