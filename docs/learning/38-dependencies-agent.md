# 38 — The Dependencies agent

> **Status:** done. `backend/agents/repo/dependencies.py` checks a repo's
> pinned package versions against OSV.dev and reports any known CVEs.

## What we built

A new repo agent, `DependenciesAgent`, that reads `requirements.txt`,
`package.json`, `package-lock.json`, and `pyproject.toml`, pulls out exact
package versions, and asks **OSV.dev** — a free, public vulnerability
database — whether any of them have known security issues. If OSV.dev can't
be reached, the scan still finishes; it just says so instead of pretending
everything's fine or crashing.

## The one big idea: asking about 100 packages in one request

If a repo pins 100 packages, asking one-question-per-package would mean 100
separate HTTP round trips. OSV.dev has a **batch** endpoint instead — one
request, carrying a whole list of questions, gets back a matching list of
answers:

```python
questions = ["capital of France", "capital of Japan", "capital of Egypt"]
# One-by-one: 3 separate round trips.
# Batched: one call, one list in, one list of answers out, same order.
answers = ask_batch(questions)   # ["Paris", "Tokyo", "Cairo"]
```

`_query_osv` does exactly this: it builds one list of `{name, ecosystem,
version}` dicts, POSTs it once to `/v1/querybatch`, and zips the response
back up against the original list by position:

```python
response = await client.post(_OSV_URL, json={"queries": queries}, timeout=15.0)
data = response.json()
for dep, result in zip(deps, data.get("results", [])):
    ids = [v["id"] for v in (result.get("vulns") or []) if "id" in v]
```

`zip()` pairs the *n*-th question with the *n*-th answer — OSV guarantees
the results come back in the same order they were asked.

## The second idea: "couldn't check" is a valid answer, not a crash

`ai/client.py`'s `call_groq` already established a rule for this project: if
an external service you don't control fails, return `None` and let the
caller decide what to do — never raise. `_query_osv` follows the identical
shape:

```python
try:
    response = await client.post(_OSV_URL, json={"queries": queries}, timeout=15.0)
    response.raise_for_status()
    data = response.json()
except Exception:
    return None
```

The caller (`scan()`) checks for that `None` and, instead of an empty
result, returns one honest finding: *"N dependencies found, but OSV.dev
couldn't be reached to check them."* That's the difference between
"verified clean" and "never actually checked" — a distinction worth keeping
visible rather than collapsing into the same "no findings" result.

Parsing the four manifest formats themselves is mostly bookkeeping — regex
for `requirements.txt`, `json.loads` for the two npm files, `tomllib.loads`
(built into Python 3.11+) for `pyproject.toml`. One small judgment call
worth knowing about: when both `package.json` and `package-lock.json` list
the same package, the lockfile's version wins, since it's the version that
actually got installed — `package.json`'s `^1.2.3` is just a range.

## Try it

```bash
cd backend && .venv/Scripts/python.exe -c "
import httpx, asyncio
from agents.repo.dependencies import DependenciesAgent, Dependency

async def main():
    async with httpx.AsyncClient(timeout=20.0) as client:
        vulns = await DependenciesAgent()._query_osv(client, [Dependency('django', '1.11.0', 'PyPI', 'requirements.txt')])
        print(vulns)

asyncio.run(main())
"
```

- Pin a very old, well-known package (`django==1.11.0`, `requests==2.6.0`)
  in a fixture `requirements.txt` and run the agent — it comes back with
  real GHSA ids from OSV.dev.
- Run the same scan again passing `client=None` — instead of an error, you
  get one finding saying the versions couldn't be verified.
- Add an unpinned line like `flask>=2.0` — it's silently skipped, since
  there's no single exact version to ask OSV about.

## Words worth knowing

- **OSV.dev** — Open Source Vulnerabilities, a free public database of
  known security issues in open-source packages.
- **Batch request** — one HTTP call carrying a list of questions, answered
  as a matching list, instead of one call per question.
- **Graceful degradation** — when a dependency (here, an external website)
  fails, doing something reasonable instead of crashing.

---

**Next:** R6 — the Repo config agent, checking `.gitignore`, Dockerfiles,
and CI workflow files for common misconfigurations.
