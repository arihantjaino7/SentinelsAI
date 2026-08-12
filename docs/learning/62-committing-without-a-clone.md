# 62 — Committing without a clone

> **Status:** done. `backend/remediation/github.py`, `pr_body.py`, `apply.py`,
> migration 12, and `POST /scans/{id}/fix/apply`. Verified against a mocked
> GitHub; the real-PR run is still to do.

## What we built

The write half of Stage B. A saved `FixPlan` becomes a branch, one commit,
and one pull request — with no `git clone`, no temp directory, and no `git`
binary involved anywhere.

## The one big idea: git is four kinds of object

Everything here follows from understanding what a commit actually *is*.
Git stores four things:

- **blob** — one file's bytes. No name, no path. Just content, and a SHA.
- **tree** — a directory listing: names, and the SHAs they point at.
- **commit** — a pointer to one tree, plus a parent, an author, a message.
- **ref** — a *movable name*, like `refs/heads/main`, pointing at a commit.

A commit made by hand is just those four, built bottom-up. GitHub exposes an
endpoint per kind, so the whole sequence is five HTTP calls:

```
blob(s)  →  tree  →  commit  →  ref  →  pull request
```

A tiny standalone version, no git involved:

```python
contents = {"a1": "hello"}            # blobs, keyed by content id
listing  = {"greeting.txt": "a1"}     # a tree
snapshot = {"tree": listing, "parent": None, "msg": "first"}
branches = {"main": snapshot}         # a ref: a name pointing at a snapshot
```

Notice that nothing is ever overwritten. Each step *creates* a new immutable
object, and only the last one introduces a name anybody will see. That has a
nice consequence: if the flow fails at step 3, the blobs and tree already
uploaded have no ref pointing at them, so they're unreachable and GitHub
garbage-collects them. A failure before `create_ref` genuinely leaves nothing
behind.

## The subtlety that would delete your repository

```python
base_tree = await writer.get_commit_tree(base_sha)
tree_sha = await writer.create_tree(base_tree, entries)
```

`create_tree` takes a `base_tree`, which means *"the repository as it already
is, with these paths replaced."* Leave it out and the new tree contains only
the files you listed — so the pull request shows every other file in the repo
as **deleted**.

And `base_tree` wants a **tree** SHA, while every other part of this flow
speaks in **commits**. They're different objects; a commit is a wrapper
around a tree. So there's an extra lookup to go from one to the other, and a
test asserting it happens:

```python
async def test_tree_is_built_from_the_base_commits_tree_not_the_commit(...):
```

## The method that doesn't exist

CLAUDE.md's remediation rule 5 says: always a pull request, never a direct
push, never a force-push, never a write to a branch Sentinels didn't create.

`GitHubWriter` has `create_ref`. It does **not** have `update_ref`, and there
is a test asserting that:

```python
assert not hasattr(writer, "update_ref")
assert not hasattr(writer, "merge")
```

The strongest version of "this program never moves an existing branch" isn't
a check — it's that the code to move one was never written.

## `apply.py`: every refusal happens before the first write

This is the only place in Sentinels that writes to somebody's repository, so
the whole file is one readable sequence of things that can say no:

| # | Check | Why |
|---|---|---|
| 1 | Scan ownership | Your scan. Not "any signed-in user's". |
| 1 | Installation ownership | Checked *separately* — passing one never implies the other. |
| 2 | Idempotency | Already has an open PR? Return that one, don't open a second. |
| 3 | Re-validate every plan | A stored plan is not trusted just because it passed once. |
| 4 | Cross-plan batch checks | No two plans may touch the same file. |
| 5 | Drift | Every file's blob SHA re-read and compared. |
| 6 | Budgets | Max 3 PRs per scan, 10 per hour. |
| 7 | **`dry_run` stops here** | Everything checked. Nothing written. |

Two of these are worth dwelling on.

**Drift aborts the whole batch, not the bad part.** Each patch records the
blob SHA the file had when it was planned. If the file changed since, the
diff no longer describes reality and applying it would overwrite whatever
arrived after planning. One mismatch anywhere stops everything — a pull
request containing three good patches and one stale one is not something to
open and hope somebody notices.

**A mixed selection is refused, not split.** If you ask for four fixes and two
already have open PRs, Sentinels refuses rather than quietly giving you a PR
with the other two. You asked for one thing and would silently get another.

And `dry_run` defaults to `True` in the request model. A request that forgets
the flag previews; it never pushes. The dangerous option has to be typed.

## The one mess it can leave, and how it cleans up

There's exactly one window where a failure leaves something visible: the
branch is created, then the pull request fails to open. Now there's a
`sentinels/…` branch in someone's repository with nothing explaining what it
is. So:

```python
except GitHubWriteError as exc:
    removed = await writer.delete_ref(branch)
    write_audit(..., f"branch {'removed' if removed else 'could NOT be removed'}")
    raise ApplyError(...)
```

`delete_ref` returns `False` instead of raising, because it runs while another
error is already on its way up — a failed cleanup must not replace the real
cause with a less useful one.

## Migration 12: an audit row that can't be deleted out from under you

`fix_plans` is `INSERT OR REPLACE`d on every re-plan, which gives the row a
brand new autoincrement id. The original schema had:

```sql
fix_plan_id INTEGER NOT NULL REFERENCES fix_plans(id) ON DELETE CASCADE
```

So re-planning an already-applied finding would have **cascade-deleted its
audit row** — erasing the record of a pull request that might still be open,
or already merged. Migration 12 fixes it three ways:

1. `plan_json` — the application stores its own frozen copy of the plan that
   was actually pushed. Not a pointer to one.
2. `fix_plan_id` becomes nullable, `ON DELETE SET NULL`. A convenience, never
   a dependency.
3. A **partial unique index**:

```sql
CREATE UNIQUE INDEX idx_fix_applications_active
    ON fix_applications(scan_id, finding_key)
    WHERE state NOT IN ('failed', 'abandoned');
```

That `WHERE` is what makes it partial: SQLite only indexes matching rows. So
one finding can accumulate as many *failed* attempts as it likes, but only
ever one live one. It's the database-level backstop for the idempotency check
— belt and suspenders, since the Python check runs first and gives an error a
person can actually read.

SQLite can't `ALTER` a foreign key in place, so the table is rebuilt through
the standard create-new / copy / drop / rename dance.

## Every PR says what it does not fix

`pr_body.py` is a separate file, not three f-strings inside `apply.py`,
because rule 9 is a real requirement and the most important instance of it is
brutal:

> Removing a committed secret does not rotate it and does not erase it from
> git history.

A PR that quietly implied otherwise would be actively dangerous. So the
caveats live in a table keyed by fixer, a fixer with no entry still gets a
generic one, and there's a test proving that:

```python
def test_an_unknown_fixer_still_gets_the_generic_caveat():
```

Silence is never read as "nothing left to do".

## Try it

- `pytest tests/test_remediation_apply.py -q` — 28 tests, almost all of them
  asserting that a *rejection* happened and that the call log contains no
  `POST` at all.
- Open `test_a_failed_pr_deletes_the_orphan_branch` and comment out the
  `delete_ref` line in `apply.py`. The test fails, and what it's protecting
  becomes obvious.
- Change `MAX_PRS_PER_SCAN` in `remediation/budget.py` to `1` and re-run —
  `test_the_per_scan_pr_budget_is_enforced` shows you exactly which check
  fires.

## Words worth knowing

- **Blob / tree / commit / ref** — the four objects git actually stores.
- **`base_tree`** — "start from the repo as it is", the flag whose absence
  would delete everything.
- **Drift** — a file changing between planning a patch and applying it.
- **Idempotent** — running it twice has the same effect as running it once.
- **Partial index** — an index with a `WHERE` clause, so only some rows are
  covered by its uniqueness rule.
- **Orphan branch** — a branch with no pull request explaining why it exists.

---

**Next:** Stage C — merge the PR, re-run only the responsible agent, and show
FAIL → PASS with a real score delta.
