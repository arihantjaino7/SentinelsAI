# 65 — A badge that costs one cheap request

> **Status:** done. `backend/remediation/registry.py` (`fixable_findings`),
> `models.FixSummary`, `GET /scans/{id}/fix/summary`, and
> `FixCountBadge` on the scan overview page. 378 tests green (4 new); verified
> live against the real repo scan and a URL scan.

## What we built

The scan overview page — the one you actually land on after a scan — showed
severity counts and a "main issue" callout, with no sign that some of those
problems could be fixed with one click. Now it shows a fourth badge:

```
AUTOFIX
5
fixes available →
```

Clicking it goes straight to the first fixable finding's agent page.

## The one big idea: `handles()` and `plan()` are not the same question

A Fixer answers two different questions, and they cost two very different
amounts:

- **`handles(finding)`** — "is this finding's *id* one I know?" A string
  comparison. No network, no repo, instant.
- **`plan(finding, files)`** — "given the repo as it actually is right now,
  what's the patch?" Reads GitHub's Contents API. Real latency, real rate
  limit.

The overview page needs an answer for every finding in the scan, on every page
load. Calling `plan()` that many times would be the exact rate-limit problem
`FixPlanPanel`'s manual "Check for automatic fix" button already exists to
avoid — multiplied by however many findings a scan has.

So the new endpoint only ever calls `handles()`:

```python
def fixable_findings(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.status != Status.PASS and fixer_for(f) is not None]
```

`fixer_for` loops the five registered Fixers and asks each one `handles()`.
Nothing here touches the network, so this function can run on every scan
overview page load without a second thought.

## The honest hedge in the docstring

The count this produces means "might be fixable," not "is fixable right now."
A Fixer can still say `None` inside `plan()` once it actually looks — the file
might have been fixed since the scan ran, or (for `repo-env-example-present`)
there might be no `.env` to read variable names from. `fixable_findings`
doesn't know either of those things; it only knows the finding's *id* matches
a Fixer that exists.

That gap is fine, and it's the same gap `FixPlanPanel`'s button already lives
with — "Check for automatic fix →" can come back "no automatic fix" even
though the badge that led you there. A live plan preview is still the only way
to know for sure; this badge is a pointer toward that, not a promise.

## A tiny standalone version of the split

```python
def could_be_a_word(s: str) -> bool:
    return s.isalpha()          # cheap: just looks at the characters

def is_a_real_word(s: str, dictionary: set[str]) -> bool:
    return s in dictionary      # expensive-ish: an actual lookup
```

Counting "how many of these strings *could* be words" only needs the first
function on every string. You'd only run the second, real dictionary lookup on
the ones you're about to act on.

## Where the count is computed, and why not on the scan report itself

The obvious place to add a field is `ScanReport` — but that model is built once,
at scan time, and stored as history (PLAN-v5.md conflict #6: scans are
immutable). `fixable_findings` isn't something to compute once and freeze; a
scan that gets partly fixed and re-verified should show the count go down
without anyone re-scanning. So it's a small separate endpoint,
`GET /scans/{id}/fix/summary`, computed fresh from the stored findings on every
call — the same shape `GET /scans/{id}/checklist` and `GET /scans/{id}/files`
already use for "answer a specific question about this scan without carrying
it on the main object."

## Why the frontend doesn't just check `finding.id` itself

The five fixable id patterns (`gitignore-present`, `ci-unpinned-action-*`,
`docker-root-user-*`, ...) are a fixed, small table. It would be easy to copy
them into `lib/api.ts` and skip the network call entirely.

It would also be wrong the moment someone adds a sixth Fixer and forgets the
frontend copy exists. Nothing would catch it — the badge would just quietly
undercount forever. The backend is where `FIXERS` is defined; the frontend's
job is to render what the backend says, the same discipline `FixPlanPanel`
already follows (it never guesses tier or fixability, it asks).

## Try it

- `pytest tests/test_remediation_registry.py -q` — the four new
  `fixable_findings` tests, including one proving a passing finding never
  counts and one proving a URL scan's findings (`missing-hsts`, `missing-csp`)
  come back empty with no special-casing needed.
- Register a sixth Fixer for some finding id and re-run the tests with no
  other change — the count picks it up for free, because `fixable_findings`
  is built on `fixer_for`, not on its own copy of the id list.
- On the real repo scan (`arihantjaino7/some-action-v1`), `GET .../fix/summary`
  returns `fixable_count: 5` (`.gitignore`, the workflow pin, the Dockerfile
  `USER` line, the missing README, and the missing `.env.example`) — one more
  than the three visible on the `repo-config` agent page alone, because the
  other two live on `repo-hygiene`. The badge correctly links there, not to
  `repo-config`.

## Words worth knowing

- **Hedge** — a claim that's honest about its own limits ("might be fixable,"
  not "is fixable"). Comes up constantly in this codebase's confidence
  handling.
- **Idempotent read** — this endpoint is one; calling it twice in a row costs
  nothing extra and can't leave anything in a different state.

---

**Next:** merge the real pull request, run Verify, and watch this badge's
count actually drop.
