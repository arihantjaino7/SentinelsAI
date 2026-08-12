# 63 — Verifying a fix, and the score delta

> **Status:** done (backend). `backend/remediation/verify.py`, `states.py`,
> migration 13, `agent_for`/`repo_agent_for`, and
> `POST /scans/{id}/findings/{key}/verify`. 374 tests green; 16-check route pass
> with `TestClient`. Not wired to the frontend yet.

## What we built

The other half of the loop. Stage B opened a pull request. This stage answers
the only question that matters after it merges: **did the problem actually go
away?**

Not "did we write a patch". Not "did the PR merge". Did the agent that
complained stop complaining, when it looked again.

## The one big idea: to compare, re-run one thing and swap it in

A full re-scan would answer the question, but it would also change five other
things at once — a dependency got a new CVE, a header changed, the network was
slower. You couldn't tell what your fix did.

So: re-run **one** agent, and substitute its fresh findings into the stored
report. Everything else stays exactly as the original scan recorded it.

```python
others = [f for f in report.findings if f.agent != agent_cls.name]
before = calculate_score(report.findings, report.url)
after  = calculate_score(others + result.findings, report.url)
```

Two calls to the *same* untouched function, over two lists that differ in
exactly one agent's worth of findings. The delta is `after - before` and it
cannot be anything other than the effect of that one agent's re-run.

A tiny standalone version of the same trick — nothing to do with security:

```python
grades = {"maths": 60, "history": 80}
total = lambda g: sum(g.values()) / len(g)

before = total(grades)
after  = total({**grades, "maths": 90})   # one subject retaken, rest untouched
print(after - before)                     # 15.0
```

`{**grades, "maths": 90}` builds a *new* dict with one key replaced. The
original is never modified — which is the second idea in this stage.

## The stored scan is never touched

`scans` is history. A verification writes no new scan row and edits no old one;
it reads the stored report, computes over a copy in memory, and throws the copy
away. There's a test that does nothing but assert this:

```python
async def test_the_original_scan_is_never_modified(...):
    ...
    stored = get_scan(SCAN_ID)
    assert stored.score == 84          # still the score the scan recorded
```

If verification rewrote the scan, a report would silently mean something
different depending on when you opened it.

## The failure mode that would have lied to you

`BaseRepoAgent.run()` never raises — it catches everything and puts the message
on `AgentResult.error`. That's what stops one agent crashing a whole scan.

Here it's a trap. A crashed agent returns **zero findings**. Substitute zero
findings into the report and the score goes *up*, and Sentinels reports:
every problem in this file is fixed. From a crash.

```python
if result.error:
    raise VerifyError(f"The {result.agent} agent failed ... so nothing can "
                      "be concluded about the fix.", status=502)
```

"I couldn't check" and "it's fixed" are different answers, and only one of them
is true. The test for this builds an agent that always errors and asserts the
row stays at `merged`.

## A state machine, written down

Six states have existed since Stage A (`planned`, `pr_open`, `merged`,
`verified`, `failed`, `abandoned`) — but nothing said what *order* they were
allowed to happen in. So nothing stopped a bug marking a fix `verified` with no
pull request ever merging. The audit trail would have recorded that as fact.

`remediation/states.py` is a table and one function:

```python
ALLOWED_TRANSITIONS = {
    PLANNED:  {PR_OPEN},
    PR_OPEN:  {MERGED},
    MERGED:   {VERIFIED},
    VERIFIED: set(),      # nothing follows
    ...
}
```

A tiny standalone one, about a parcel:

```python
next_step = {"ordered": {"shipped"}, "shipped": {"delivered"}, "delivered": set()}

def move(now, then):
    if then not in next_step[now]:
        raise ValueError(f"a parcel can't go from {now} to {then}")
```

Two extra rules on top of the table, both deliberate:

- **`failed` and `abandoned` are reachable from anywhere.** An attempt can
  always end — GitHub can refuse a write, or you can close the PR unmerged.
- **A state to itself is allowed.** Re-verifying re-reads the repo and writes
  the same conclusion. That's not a state change.

`storage/remediation.py` now checks the table before every state write, so an
illegal move raises instead of being persisted.

## "Verified" means we looked, not that it passed

This is the naming decision worth arguing about. If the re-run shows the
finding *still failing*, the row still becomes `verified` — and
`target_fixed: false` carries the answer.

The alternative (only mark `verified` on success) would leave a merged fix that
didn't work sitting in `merged` forever, indistinguishable from one nobody has
checked yet. "We haven't looked" and "we looked and it didn't work" are very
different things to know.

## Gating: merge first, then verify

Verifying while the pull request is still open would re-observe the original
problem and report the fix as broken. So:

```python
if application.state == FixApplicationState.PR_OPEN and application.pr_number:
    raise VerifyError(f"Pull request #{application.pr_number} has not been merged yet...", 409)
```

And the live PR-state refresh from Stage B runs *first*, so "merged" means
GitHub said so just now, not what we happened to see last week.

One exception, on purpose: a finding with **no** application row at all can
still be verified. Someone may have fixed it by hand. There's just no audit row
of ours to close out, so the result comes back `recorded: false` — and the
audit log gets a `fix_verified_unrecorded` row saying exactly that.

## `async with`, and how the test fakes a repository

`fetch_repo` is an **async context manager**. A normal `with` block runs setup,
gives you a value, and guarantees teardown. An async one is the same shape,
except setup and teardown are allowed to `await` — to do network work while the
event loop gets on with other things:

```python
async with fetch_repo(owner, repo, ref, client) as fetched:
    ...            # inside: the repo is extracted on disk at fetched.root
# outside: the temp directory has already been deleted
```

The teardown here matters: `repo/fetch.py` deletes the extracted tarball on the
way out and stores no file content anywhere. Annoying for most purposes,
perfect for this one — there is no cached copy that could show the repository as
it looked *before* the merge, so verification physically cannot verify stale
data.

Building one for a test is three lines:

```python
@contextlib.asynccontextmanager
async def fake_fetch_repo(owner, repo, ref, client):
    yield RepoFetchResult(root=tmp_path, owner=owner, repo=repo,
                          ref=ref or "main", default_branch="main")
```

Everything before the `yield` is setup, everything after is teardown, and the
decorator turns it into something `async with` accepts. Now "the repository
after the merge" is just a folder the test wrote two files into — and the whole
verify suite runs offline, against the **real** `ConfigAgent` and the **real**
`calculate_score`. Those two are exactly what must not be faked.

## Getting from a stored string back to a class

A saved `Finding` remembers its agent as a *name*: `"repo-config"`. To re-run
it we need the class. Both registries got the same three lines:

```python
AGENTS_REPO_BY_NAME = {cls.name: cls for cls in AGENTS_REPO}

def repo_agent_for(name: str):
    return AGENTS_REPO_BY_NAME.get(name)
```

Derived from the existing list, never written out a second time — a hand-kept
copy would eventually disagree with it. `.get()` rather than `[...]` because a
finding saved by an older version can name an agent that no longer exists, and
that deserves a 409 with a readable message, not a `KeyError`.

## Migration 13 is one line

```sql
ALTER TABLE fix_applications ADD COLUMN verification_json TEXT;
```

Compare migration 12, which rebuilt the whole table. The difference: 12 changed
a **foreign key**, and SQLite can't alter one in place. Adding a nullable column
changes no constraint, so the simple form works and every existing row just
gets `NULL`.

Why JSON on the row instead of a `verifications` table? It's one-to-one with an
application and never queried across rows. It isn't a separate record — it's
the *evidence* for that row's `verified` state, so it lives on the row.

## Try it

- `pytest tests/test_remediation_verify.py -q` — 19 tests, no network.
- Open `test_a_crashed_agent_refuses_instead_of_claiming_success` and delete the
  `if result.error:` block in `verify.py`. The test now fails with `delta == 8`
  — the exact lie it exists to prevent.
- `pytest tests/test_remediation_states.py -q` and read the parametrized
  `test_verified_is_only_reachable_from_merged`.
- Change `FIXED_GITIGNORE` in the verify tests to `"node_modules\n"` and re-run:
  the `.env` check fails again, `target_fixed` flips to `False`, and the delta
  drops. The scoring wasn't hardcoded anywhere.

## Words worth knowing

- **Score delta** — the difference between two runs of the same pure scoring
  function over two lists of findings.
- **State machine** — a written-down table of which states can follow which.
- **Async context manager** — `async with`; setup and teardown that may await.
- **Idempotent** — re-running it lands you in the same place (why
  `verified → verified` is legal).
- **`ALTER TABLE ADD COLUMN`** — the cheap migration; only works when no
  constraint changes.

---

**Next:** wiring apply + verify into the UI (a `/settings` page to connect a
repo, a Fix → Preview → PR → Verify path on the finding row), then Stage D's
URL → repo bridge.
