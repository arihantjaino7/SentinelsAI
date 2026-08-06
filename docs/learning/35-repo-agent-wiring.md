# 35 — Repo agents get their own contract (R2)

> **Status:** done. `GET /repo/agents` returns the first repo agent's
> metadata; a real agent (README/LICENSE check) proved the wiring end to end,
> including a deliberately-broken agent that still can't crash the scan.

## What we built

The URL side has `ScanContext` + `BaseAgent` + a registry (note 21). This
milestone builds the exact same three pieces for repo scanning:
`RepoContext` (what a repo agent gets handed), `BaseRepoAgent` (the contract
every repo agent must follow), and `agents/repo_registry.py` (the one list of
repo agents). The first real repo agent, `HygieneAgent`, checks whether a
repo has a README and a LICENSE.

## The one big idea: copy the pattern, not the class

`BaseRepoAgent` isn't a subclass of `BaseAgent` — it's a **new class with the
same shape**, crash-proofing logic copied over on purpose. It would be
possible to write one generic base class both `ScanContext` and
`RepoContext` share, but that's solving a problem nobody has yet: there are
only two kinds of context, they're genuinely different (one holds a URL, one
holds a file tree), and this project already prefers five small, obvious
agent files over one clever configurable one. A small standalone example of
the same choice:

```python
# Two shapes that are similar but not the same thing
class EmailNotifier:
    def send(self, message: str) -> None:
        print(f"emailing: {message}")

class SmsNotifier:
    def send(self, message: str) -> None:
        print(f"texting: {message}")
```

You *could* invent a generic `Notifier[T]` base class parametrized over the
channel. For two straightforward classes, that's more machinery than the
problem needs — the duplication is small, obvious, and easy to read at a
glance. That's the same call made here: `BaseRepoAgent.run()` is a
line-for-line copy of `BaseAgent.run()`, not a shared generic.

## The actual pieces

`RepoContext` — everything a repo agent needs, built once and shared:

```python
@dataclass
class RepoContext:
    repo_url: str
    owner: str
    repo: str
    ref: str
    root: Path                 # where the extracted repo lives on disk
    files: list[RepoFile]      # the whole tree, walked ONCE
    client: httpx.AsyncClient | None = None
```

Walking the tree once and handing every agent the same `files` list is the
repo-side version of `ScanContext` sharing one `httpx.AsyncClient` — nobody
re-does the same expensive work five times.

`HygieneAgent` follows the exact same PASS/WARN-with-a-Finding pattern
`exposure.py` already uses — one check, one `Finding` either way:

```python
class HygieneAgent(BaseRepoAgent):
    name = "repo-hygiene"
    category = "Hygiene"

    async def scan(self, context: RepoContext) -> list[Finding]:
        root_names = _root_file_names(context)
        return [self._check_readme(root_names), self._check_license(root_names)]
```

## Proving the crash-proofing works

`BaseAgent.run()`'s whole job is "never let one broken agent kill the scan"
(note 26). To actually *prove* `BaseRepoAgent.run()` does the same thing, a
temporary agent whose `scan()` always raises was run through it:

```python
class ExplodingAgent(BaseRepoAgent):
    async def scan(self, context):
        raise RuntimeError("deliberate failure")

result = await ExplodingAgent().run(context)
# result.error == "RuntimeError: deliberate failure", result.findings == []
# — the exception never left run(), the caller never crashed.
```

## Try it

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload
```

- `curl localhost:8000/repo/agents` — one agent, `repo-hygiene`, with its
  `checks` list.
- Run a real scan of a repo with no LICENSE (most personal projects) — the
  `repo-license-present` finding should come back as `warn`, not `pass`.
- Add a `LICENSE` file to a test folder and re-run the hygiene checks — the
  finding should flip to `pass`.

## Words worth knowing

- **Contract** — a shared shape (here: `name`, `scan()`, `run()`) every
  implementation must follow, so callers can treat them interchangeably.
- **Registry** — the single list a new agent gets added to; nothing else
  needs to change to discover it (note 21).
- **Crash-proofing** — catching every exception inside `run()` so one
  agent's bug never takes down the whole scan.
- **Premature abstraction** — building a general/flexible solution before you
  actually have two different cases that need it.
