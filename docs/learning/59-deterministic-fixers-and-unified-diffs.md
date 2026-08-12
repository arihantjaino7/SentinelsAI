# 59 — Deterministic fixers and unified diffs

> **Status:** done. `backend/remediation/` can look at a finding, read the
> repo's current state from GitHub, and produce a real, reviewable diff —
> for four kinds of finding so far, with zero AI involved.

## What we built

A new package, `backend/remediation/`, that turns some findings into an
actual code change instead of just advice. Sentinels already had an AI
button that writes a paragraph explaining a problem (`FixSuggestion`). This
is a different, later thing: a `FixPlan` — a real diff, computed by plain
Python, that a person can read, download, and apply by hand. Four fixers
exist: pinning an unpinned GitHub Action to a commit SHA, adding a missing
`.gitignore`, adding a starter `README.md` or `.env.example`, and adding a
non-root `USER` to a Dockerfile.

## The one big idea: no model ever writes the patch

The AI fix button works by asking an LLM "explain this problem," and
whatever comes back gets shown as-is. That's fine for prose — a slightly
different sentence each time doesn't matter. It's not fine for a piece of
code that's about to be applied to someone's repository: an LLM can
hallucinate a file that doesn't exist, get a syntax detail wrong, or just
answer differently on a re-run for the exact same input.

So a `Fixer` never asks a model anything. It's an ordinary Python class with
two methods:

```python
class Fixer(ABC):
    def handles(self, finding: Finding) -> bool: ...
    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None: ...
```

`handles()` checks the finding's ID — a string match, nothing clever.
`plan()` reads whatever file content it needs and either builds a `FixPlan`
or returns `None` ("nothing I can safely do here"). Same finding, same repo
state, same answer, every single time — that's the whole point.

A tiny example of the same idea, nothing to do with security: a function
that formats a date is deterministic (`format_date(2026, 1, 1)` always
returns `"2026-01-01"`); a function that asks an LLM to "write today's date
nicely" is not — it might come back differently phrased two calls in a row.
Fixers are the first kind on purpose.

## The other idea: a diff is just two lists of lines, compared

A "unified diff" (the format `git diff` prints) looks intimidating but is
built from something small: Python's own `difflib` comparing two lists of
lines.

```python
import difflib
before = "cat\ndog\n".splitlines(keepends=True)
after = "cat\nfish\n".splitlines(keepends=True)
print("".join(difflib.unified_diff(before, after, fromfile="a", tofile="b")))
```

That prints `-dog` and `+fish` — every line that's the same is left alone,
every line that changed shows up once with a `-` and once with a `+`.
`remediation/patch.py`'s `build_diff()` is exactly this call, just fed a
file's old and new content instead of two lines.

## The actual code

`remediation/source.py`'s `FileSource.get(path)` fetches one file's current
text straight from GitHub's Contents API — not the tarball `repo/fetch.py`
downloads during a scan (that's deleted the moment the scan finishes, and
never carried a per-file ID anyway). It's `await`ed because it's a real
network call: the line `source = await files.get(finding.file_path)` pauses
right there, hands control back to the event loop until GitHub answers, then
resumes with the result — the same shape as the `await client.get(...)`
calls the scanning agents already make.

Each `FilePatch` also carries `original_sha` — the file's exact version at
the moment the plan was built. That's the "drift anchor": if the file
changes on GitHub before anyone applies the fix, that SHA is how a later
stage will notice and refuse to overwrite someone else's edit, instead of
silently applying a stale patch.

Before a `FixPlan` is ever shown to anyone, it passes through
`validate_plan()` — one function, in `remediation/patch.py`, that rejects
anything a Fixer might get wrong: a path that tries to escape the repo
(`../../etc/passwd`), a write under `.git/`, too many files at once, or a
patch that doesn't actually belong to the finding it claims to fix. A
finding with no `file_path` (like "no README exists") is only ever allowed
to *create* a brand-new file — never touch one it was never told about.

## Try it

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_remediation_patch.py tests/test_remediation_workflows.py -q
```

- Read `remediation/gitignore.py` — it's the shortest fixer, a good first
  one to trace end to end.
- Try `difflib.unified_diff` yourself in a Python shell with two short
  strings you make up.
- Look at `tiers.py` — it's just a dictionary from finding-ID to a number
  1-4, deciding which findings are even allowed to reach a Fixer at all.

## Words worth knowing

- **Fixer** — a Python class that turns one kind of finding into a `FixPlan`.
- **Unified diff** — the `-old`/`+new` text format `git diff` prints.
- **Drift anchor** — the file's blob SHA at plan time, used later to detect
  "this file changed since we planned this fix."
- **`await`** — pauses a function at a real network call and lets other work
  run until the answer comes back, instead of blocking everything.

---

**Next:** 60 — the diff preview UI, where this `FixPlan` actually gets shown
on the report page.
