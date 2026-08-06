# 26 — Agent pages (M8)

> **Status:** done. Every agent has its own page at `/scan/{id}/agents/{name}`. The backend serves a new endpoint; the frontend fetches agent metadata and results in parallel; the page is data-driven — adding a 6th agent to `registry.py` makes its page appear automatically.

## What we built

Three pieces:

1. **Backend endpoint** — `GET /scans/{id}/agents/{name}` returns one agent's slice of a stored scan (its findings, timing, and error).
2. **`lib/agents.ts`** — two fetch functions: `fetchAgents()` (wraps `GET /agents`) and `fetchAgentResult()` (wraps the new endpoint).
3. **`app/scan/[scanId]/agents/[agentName]/page.tsx`** — the agent detail page.

The ScanProgress component on the home page was also updated to fetch its agent list from `GET /agents` instead of using a hardcoded array, so adding a 6th agent shows up in the waiting state too.

## New concept: nested dynamic routes

The agent page URL has two dynamic segments: the scan ID and the agent name. In Next.js App Router, you nest folders:

```
app/scan/[scanId]/agents/[agentName]/page.tsx
```

The page gets both parameters from `useParams`:

```tsx
const { scanId, agentName } = useParams<{
  scanId: string;
  agentName: string;
}>();
```

Each segment is independent — `scanId` comes from the outer folder, `agentName` from the inner one. You can have as many nested dynamic segments as you need.

## New concept: `Promise.all` for parallel fetches

The agent page needs two things: agent metadata (from `GET /agents`) and the agent's results (from the new endpoint). Fetching them in series wastes time — the second can start immediately, it doesn't need the first to finish.

```tsx
// Example — fetch two things at once instead of one after the other
const [userProfile, userOrders] = await Promise.all([
  fetch("/api/profile").then((r) => r.json()),
  fetch("/api/orders").then((r) => r.json()),
]);
// Both fetches ran simultaneously; you wait for the slower one only
```

`Promise.all` takes an array of promises and returns a single promise that resolves when ALL of them have resolved. The results come back in the same order as the input array. In our code:

```tsx
Promise.all([
  fetchAgents().then((agents) => agents.find((a) => a.name === agentName) ?? null),
  fetchAgentResult(scanId, agentName),
]).then(([agentInfo, agentResult]) => { ... })
```

If either fetch fails, `Promise.all` rejects and we land in the `.catch(() => setNotFound(true))` handler.

## The verdict

The agent page shows a "verdict" — Clean, Issues found, or Failed — derived from what the agent returned. There's no `verdict` field in the backend model; it's computed in the frontend from the data we already have:

```tsx
function getVerdict(result: AgentResult): "clean" | "issues_found" | "failed" {
  if (result.error) return "failed";
  if (result.findings.some(isProblem)) return "issues_found";
  return "clean";
}
```

This is the right place for this logic. The backend stores the raw facts (findings, errors). The label "Issues found" is a presentation decision that belongs in the UI, not in the database.

## The zero-frontend-change test

The milestone spec (PLAN-v2.md) says: "temporarily add a dummy 6th agent to `registry.py` and confirm its page appears with zero frontend edits." This works because:

- `ScanProgress` fetches its agent list from `GET /agents` — if there are 6 agents, 6 panels appear
- The agent log on the dashboard links to `/scan/{id}/agents/{name}` for any name the backend returns
- The agent page at `/scan/{id}/agents/{name}` fetches metadata from `GET /agents` — whatever name is in the URL, it looks it up

The only thing hardcoded is the fallback list in `ScanProgress` (`["headers", "recon", "tls", "exposure", "dns"]`) — but that's only used when `GET /agents` fails entirely, which is a backend-unreachable scenario, not a normal code path.

## Try it

- Click an agent name in the dashboard's agent log. The agent detail page should load.
- Check that purpose, checks, verdict, timing, issues, and evidence all render.
- Try `/scan/{id}/agents/fake-agent`. You should see the "Agent not found" fallback.

## Words you now know

- **`Promise.all`**: runs multiple promises in parallel and gives you all results at once.
- **Nested dynamic route**: multiple `[param]` folder segments in the same path.
- **Derived state**: a value computed from the data you already have, rather than stored separately. Verdict is derived from findings.
