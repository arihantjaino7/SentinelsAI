# 45 — Repo launcher and live progress

> **Status:** done. `/repo` is a real launcher now, not a "coming soon" page.
> Typing a public GitHub URL there streams the five repo agents live, the same
> way `/url` already streams the five website agents, and lands on the same
> `/scan/[scanId]` report page. Verified end-to-end against `octocat/Hello-World`
> — all five `repo-*` agents lit up, then landed on a real B/80 report with a
> correct 17-item repo checklist and a correct "Repo Config" agent detail page.

## What we built

`GET /repo/stream` — the repo-side sibling of A16's `GET /scan/stream` — plus
the frontend pieces that call it: `streamRepoScan()`, and a `targetType` prop
threaded through `ScanLauncher` and `ScanProgress` so both components can
drive either scan kind. `app/repo/page.tsx` went from a static placeholder to
a working form.

## The one big idea: a prop instead of a duplicate component

`ScanLauncher` already worked for URL scans. The repo side needed the exact
same behavior — type something, stream progress, navigate to the report — so
the temptation is to copy the whole component into `RepoScanLauncher.tsx` and
tweak a few lines. That's how two components quietly drift apart over time:
someone fixes a bug in one copy and forgets the other exists.

Instead, `ScanLauncher` gained one new prop:

```tsx
targetType?: "url" | "repo";  // defaults to "url"
```

and one `if`:

```tsx
const stream = targetType === "repo" ? streamRepoScan : streamScan;
```

Every existing caller (`/url`, the landing page) never sets this prop, so it
silently keeps behaving exactly as before — the default *is* the old
behavior. Only `/repo` passes `targetType="repo"`. `ScanProgress` got the
same treatment: instead of always calling `fetchAgents()` (the URL agent
list), it now picks `fetchAgents` or `fetchRepoAgents` based on the same prop.

A tiny everyday version of the same idea: a thermostat app has one
`<TemperatureDisplay unit="celsius">` component rather than a separate
`FahrenheitDisplay` copy-pasted from it. One component, a prop that picks
which data it reads, a sensible default so old call sites don't need to
change.

## The actual code

`backend/repo_orchestrator.py` — `run_repo_scan_stream`, mirroring
`orchestrator.run_scan_stream` almost line for line: same `asyncio.as_completed`
loop yielding `("agent", result)` as each of the five repo agents finishes,
then one `("done", report)` at the end. Both `run_repo_scan` and the new
streaming version now share one `_finalize()` helper — the same refactor
`orchestrator.py` already used for A16, so scoring/checklist/persistence logic
lives in exactly one place instead of two copies drifting apart.

```python
# backend/main.py — the repo-side sibling of GET /scan/stream
@app.get("/repo/stream")
async def repo_scan_stream(url: str) -> StreamingResponse:
    async def events():
        try:
            async for event_name, payload in run_repo_scan_stream(url):
                yield _sse(event_name, payload.model_dump_json())
        except ValueError as exc:
            yield _sse("failed", json.dumps({"detail": str(exc)}))
    return StreamingResponse(events(), media_type="text/event-stream")
```

`frontend/lib/api.ts` — `streamRepoScan()`, identical shape to `streamScan()`,
pointed at `/repo/stream` instead of `/scan/stream`.

`frontend/components/ScanProgress.tsx` — the fallback agent names are now
keyed by target type, since the five repo agent names (`repo-secrets`,
`repo-hygiene`, ...) are nothing like the five URL agent names:

```tsx
const FALLBACK_NAMES: Record<TargetType, string[]> = {
  url: ["headers", "recon", "tls", "exposure", "dns"],
  repo: ["repo-hygiene", "repo-secrets", "repo-dependencies", "repo-config", "repo-patterns"],
};
```

One more small fix while verifying: the per-agent detail page
(`app/scan/[scanId]/agents/[agentName]/page.tsx`) looked up an agent's
display name/purpose only in the URL agent list, so a repo scan's agent page
would've silently shown the raw slug (`repo-config`) instead of "Repo
Config". It now tries `fetchAgents()` first and falls back to
`fetchRepoAgents()` if the name isn't found there.

## Try it

- Start both servers, open `localhost:3000/repo`, and scan a small public
  repo like `github.com/octocat/Hello-World` — watch the five `repo-*` tiles
  light up one at a time instead of all at once.
- After it lands on the report page, click into the "Repo Config" agent —
  its title and "what this agent checks" list should read as real English,
  not a raw slug.
- Open `/url` again afterward and scan a normal website — it should behave
  exactly as it did before this note, proving the shared components' default
  behavior never changed.

## Words worth knowing

- **Default prop value** — `targetType = "url"` in the function signature
  means any caller that doesn't pass `targetType` gets `"url"` automatically,
  which is what keeps every existing call site working untouched.
- **Discriminator** — a field like `target_type` whose only job is telling
  otherwise-identical code which of two shapes it's looking at.

---

**Next:** R12 — the file-tree browser (`/scan/[scanId]/files`), the last
piece of `docs/PLAN-v3.md`.
