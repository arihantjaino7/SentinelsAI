# 39 — The Repo Config agent

> **Status:** done. `backend/agents/repo/config.py` checks `.gitignore`
> completeness, Dockerfile smells, and risky GitHub Actions settings.

## What we built

A new repo agent, `ConfigAgent`, that checks three unrelated but common
misconfigurations: whether `.gitignore` actually covers `.env`, key files,
and `node_modules`; whether a `Dockerfile` runs as root, floats on `:latest`,
or bakes a secret into an `ENV`/`ARG` instruction; and whether a GitHub
Actions workflow uses the risky `pull_request_target` trigger or pins a
third-party action to a movable tag instead of a commit.

## The one big idea: don't hand untrusted input to a full parser

PyYAML happens to already be installed in this project, so parsing the CI
workflow files "properly" was tempting. It's the wrong call here: this
agent's whole job is reading **content from a repo we don't control** — the
same reasoning that made R1's tarball extraction use `filter="data"` and
hard size caps applies again. A full YAML/Dockerfile parser is a much bigger
piece of code, written by someone else, being pointed at hostile input; a
handful of targeted regexes (`FROM`, `USER`, `uses:`) is small enough to
reason about completely and can't be tricked into doing anything but
matching text.

## The second idea: fnmatch — one glob pattern, one filename, one answer

The `.gitignore` check doesn't parse full gitignore syntax either. It just
asks: does a *representative* filename match any line in the file?

```python
import fnmatch

fnmatch.fnmatch("test.pem", "*.pem")   # True
fnmatch.fnmatch("test.pem", "*.env")   # False
```

`fnmatch` (standard library, no install needed) understands glob wildcards
like `*` and `?`. So `_check_gitignore` just tries a couple of stand-in
names — `"test.pem"`, `".env"`, `"node_modules"` — against every line in the
repo's `.gitignore` and reports whichever ones nothing matched.

## The actual checks

```python
checks = [
    ("gitignore-env", ".env", [".env", ".env.local"], Severity.HIGH),
    ("gitignore-private-keys", "private key files (*.pem/*.key)",
     ["test.pem", "id_rsa.key"], Severity.HIGH),
]
if has_js_manifest:
    checks.append(("gitignore-node-modules", "node_modules", ["node_modules"], Severity.LOW))
```

`node_modules` is only checked when a `package.json`/`package-lock.json`
exists — a pure-Python repo has nothing to gain from that pattern, so it's
skipped instead of producing a meaningless finding.

Dockerfile secrets are masked with the exact same `_mask()` idea R4's
`SecretsAgent` uses (`hunt...ter2` instead of the real value) — an `ENV
API_KEY=...` line bakes that value permanently into the image's layer
history, so it deserves the same no-echo treatment as a committed `.env`
file. CI risk detection is two independent regex checks: one literal search
for `pull_request_target` anywhere in the file, and one per `uses:` line —
if the action isn't published by `actions`/`github` and its `@ref` isn't a
40-character commit SHA, it's flagged as pinned to something that can move.

## Try it

```bash
cd backend && .venv/Scripts/python.exe -c "
import fnmatch
print(fnmatch.fnmatch('.env', '.env*'))
print(fnmatch.fnmatch('config.py', '.env*'))
"
```

- Write a `.gitignore` with only `node_modules` in it, alongside a
  `package.json` — run the agent and see `gitignore-env` and
  `gitignore-private-keys` both fail, while `gitignore-node-modules` passes.
- Write a `Dockerfile` with `FROM python:3.12` (a real tag, no `:latest`)
  and a `USER app` line — neither of those two findings should appear.
- Add `uses: actions/checkout@v4` to a workflow file — it's skipped, since
  `actions` is a trusted first-party publisher regardless of the tag.

## Words worth knowing

- **`fnmatch`** — standard-library glob-pattern matching (`*`, `?`) against
  a single string, without touching the filesystem.
- **Attack surface** — how much code an attacker's input actually gets to
  run through; a small regex has far less than a general-purpose parser.
- **Pinning** — locking a dependency (a package, a Docker base image, a CI
  action) to one exact, immutable version instead of a name that can move.

---

**Next:** R7 — the Code Patterns agent, scanning for risky constructs like
`eval`, `shell=True`, and string-built SQL.
