# 25 — Dashboard (M7)

> **Status:** done. The scan detail page is a proper dashboard with score, findings, agent log with clickable agent names, and a "Recent scans" panel at the bottom.

## What we built

The `/scan/[id]` page is now the dashboard: it fetches the stored scan from the backend and renders the score ring, severity counts, AI summary, findings grouped by category, the agent log (with agent names as links to their detail pages), and a compact list of recent scans. Two new quick actions sit in the header: "New scan" (links back to `/`) and "Download PDF".

No new backend work — this is entirely a frontend composition step. The data was already available from M1-M2. M7 is about making the page feel like a real tool rather than a raw data dump.

## What's different from the old Report component

The old `Report.tsx` is still in the codebase but is no longer rendered anywhere after M6's redirect. The new dashboard page is a fresh composition using the same sub-components (`ScoreRing`, `FindingRow`, `AgentLog`) but with a few additions:

- **"New scan" button**: a `<Link href="/">` in the header
- **`AgentLog` with `scanId`**: passing `scanId` to `AgentLog` makes each agent name a link to its detail page (M8)
- **`<RecentScans>`**: a new component that fetches `GET /scans?limit=10`, filters out the current scan, and shows the 5 most recent others

## The `RecentScans` component

`components/dashboard/RecentScans.tsx` fetches its own data with a `useEffect`:

```tsx
useEffect(() => {
  fetchRecentScans(10).then((all) =>
    setScans(all.filter((s) => s.id !== currentScanId).slice(0, 5)),
  );
}, [currentScanId]);
```

Why filter first, then slice? The limit at the API level (`?limit=10`) is loose — it fetches more than we need so we have room to remove the current scan and still show 5. If we fetched exactly 5, and the current scan was in that 5, we'd show only 4.

Why does it return `null` instead of an empty section when there are no other scans? Empty sections add visual weight for no information. This is the same logic that makes the AI summary section conditional on `report.summary` being non-empty — show the section when there's something to show, not when there isn't.

## Try it

- Scan a site twice. On the second scan's dashboard, the first scan appears in "Recent scans".
- Click a recent scan — it should navigate to that scan's dashboard.
- Click "Download PDF" — same behavior as before, now on the scan page instead of the home page.

## Words you now know

Nothing new here — this step is composition of concepts from earlier notes. `useEffect`, `fetch`, conditional rendering, `Link` — all introduced before.
