# 34 — Fetching a GitHub repo safely (R1)

> **Status:** done. `backend/repo/fetch.py` can download any small public GitHub
> repo, extract it to a temp folder, and clean up automatically — verified
> against a real repo, a nonexistent repo, and a multi-gigabyte repo.

## What we built

Sentinels can only scan a live URL so far. This is step one of teaching it to
scan a GitHub repo instead: `parse_github_url()` turns a pasted GitHub link into
`(owner, repo, ref)`, and `fetch_repo()` downloads that repo as a `.tar.gz`,
unpacks it into a fresh temporary folder, and deletes that folder again once
you're done with it — even if something goes wrong in between.

## The one big idea: `async with` for cleanup you can't forget

You've already met plain functions that return a value. A **context manager**
is a block of code with a guaranteed "set up" step and a guaranteed "tear
down" step, written as `with ...:` (or `async with ...:` for `async` code).
You've been using one already without naming it — `async with httpx.AsyncClient() as client:`
in `orchestrator.py` opens a connection pool and *always* closes it, even if
an exception happens inside the block.

Here's the same idea, standalone, with something ordinary — a borrowed library book:

```python
from contextlib import contextmanager

@contextmanager
def borrow_book(title):
    print(f"checking out {title}")
    try:
        yield title              # the block between "with...:" and its end runs here
    finally:
        print(f"returning {title}")   # ALWAYS runs, even if the block raises

with borrow_book("Dune") as book:
    print(f"reading {book}")
    raise ValueError("dropped it in the bath")
```

Run this and you'll see `checking out Dune`, `reading Dune`, **then** `returning Dune`
— the return happens even though the exception was never caught. That's the
whole trick: `yield` splits the function into a "before" half and an "after"
half, and `finally` guarantees the "after" half runs no matter what.

`fetch_repo` is exactly this, made `async` (`@asynccontextmanager`, `async def`,
`yield` once) because it awaits real network calls before yielding:

```python
@asynccontextmanager
async def fetch_repo(owner, repo, ref, client):
    tmp_dir = Path(tempfile.mkdtemp(prefix="sentinels-repo-"))
    try:
        ...download and extract into tmp_dir...
        yield RepoFetchResult(root=tmp_dir, ...)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)   # always deleted
```

Whoever calls `async with fetch_repo(...) as result:` gets `result.root` full
of real files inside the block, and the instant the block ends — normally or
via an exception — the temp folder is gone. No caller can forget to clean up,
because the cleanup isn't their job.

## The guards, briefly

A repo you don't control could be huge, or a tar entry could try to write
outside the target folder (`../../etc/passwd`-style path traversal). Three
layers stop that:

1. **Reject before downloading anything.** GitHub's `/repos/{owner}/{repo}`
   metadata includes the repo's size in KB — if it's over ~50 MB, `fetch_repo`
   raises before requesting a single tarball byte.
2. **Cap the download itself**, in case the metadata undersells the real size.
3. **`tarfile`'s `filter="data"`** when extracting each entry — a Python 3.12+
   safety feature that refuses to extract a file outside the destination
   folder, which is exactly what blocks the path-traversal attack.

## Try it

```bash
cd backend
.venv/Scripts/python.exe -c "
import asyncio, httpx
from repo.fetch import fetch_repo, parse_github_url

async def main():
    owner, repo, ref = parse_github_url('https://github.com/octocat/Hello-World')
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with fetch_repo(owner, repo, ref, client) as result:
            print('exists during the block:', result.root.exists())
        print('exists after the block:', result.root.exists())

asyncio.run(main())
"
```

- Change the repo to `torvalds/linux` — it should reject instantly (size
  check), not sit there downloading gigabytes.
- Change the repo to something made up (`octocat/this-repo-does-not-exist`) —
  it should raise `ValueError`, not crash with an ugly traceback.

## Words worth knowing

- **Context manager** — a block with a guaranteed setup and teardown step,
  written `with ...:` / `async with ...:`.
- **`@asynccontextmanager`** — turns an `async def` function with one `yield`
  into something usable with `async with`.
- **`finally`** — a block that always runs on the way out of a `try`, whether
  the code above it succeeded, failed, or `raise`d.
- **Path traversal** — a malicious file path like `../../etc/passwd` designed
  to write outside the folder it was supposed to be confined to.
