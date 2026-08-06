# 24 — Scan routes and shareable URLs (M6)

> **Status:** done. Every finished scan lives at `/scan/<uuid>`. Hard-refreshing the page fetches the report from the database and shows it — no re-scan, no lost data.

## What we built

Before this step, a finished scan existed only in React state on the home page — refresh the page and it was gone. M1-M2 saved every scan to SQLite and exposed `GET /scans/{id}`. M6 connects those to the frontend: when a scan finishes, the browser navigates to `/scan/<uuid>`. The new page fetches the stored report from the backend and renders it. The URL is now the scan's identity, not a by-product of a running component.

## New concepts

### Client-side navigation with `useRouter`

In a normal web page, navigating to a URL means a full-page reload. In Next.js (and React apps generally), you can navigate without reloading using the router — it swaps the component tree instead of refreshing the page.

```tsx
// Small standalone example — nothing to do with security
import { useRouter } from "next/navigation";

function Redirect() {
  const router = useRouter();

  return (
    <button onClick={() => router.push("/dashboard")}>
      Go to dashboard
    </button>
  );
}
```

`router.push("/dashboard")` changes the URL and renders the matching page component, all without a network round-trip for the HTML. The user sees an instant transition.

In our code: after `onDone` fires, we call `router.push(\`/scan/\${finishedReport.id}\`)`. The home page returns to idle; the scan page loads and fetches the stored report.

### Dynamic routes in Next.js App Router

A folder named `[scanId]` in the app directory creates a dynamic route. Any URL that matches `/scan/<anything>` renders the page inside it, and the `<anything>` part is available as the `scanId` parameter.

```
app/
  scan/
    [scanId]/
      page.tsx    ← renders for /scan/abc, /scan/xyz, any UUID
```

Inside the page, `useParams<{ scanId: string }>()` returns the actual value from the URL:

```tsx
const { scanId } = useParams<{ scanId: string }>();
// If the URL is /scan/4a8f..., scanId === "4a8f..."
```

This is exactly what lets a hard-refresh work: the URL carries the ID, the component reads it, and `fetchScan(scanId)` gets the stored report.

### Layouts in App Router

A `layout.tsx` file wraps every page inside its folder. Our scan layout renders a nav bar (the "Sentinels" link and optional breadcrumbs) and then `{children}`, which is whatever page is currently active.

```
app/scan/[scanId]/
  layout.tsx   ← nav bar wrapper, always rendered
  page.tsx     ← dashboard, rendered at /scan/{id}
  agents/
    [agentName]/
      page.tsx ← agent detail, rendered at /scan/{id}/agents/{name}
```

The layout renders once and stays while you navigate between sub-pages. It's like a frame that doesn't change while the content inside it does.

## The actual code

`app/page.tsx` (home) used to set a `report` state variable and show `<Report>` inline. Now `onDone` just calls `router.push(...)`:

```tsx
onDone: (finishedReport) => {
  router.push(`/scan/${finishedReport.id}`);
},
```

The scan is already in the database (the backend persists before emitting `done`), so there's no race condition — the new page can fetch immediately.

`app/scan/[scanId]/page.tsx` fetches the report on mount:

```tsx
useEffect(() => {
  fetchScan(scanId)
    .then(setReport)
    .catch(() => setNotFound(true))
    .finally(() => setLoading(false));
}, [scanId]);
```

`fetchScan` calls `GET /scans/{id}`, which reconstructs the full `ScanReport` from the database. Whatever the backend returns here is what the page shows — identical to what `POST /scan` originally returned.

## Try it

- Run a scan. Watch the URL change to `/scan/<uuid>` when the agents finish.
- Hard-refresh that URL. The report should reappear with no spinner, no re-scan.
- Try `/scan/fake-id`. You should see the "This scan doesn't exist" state.

## Words you now know

- **Dynamic route**: a URL segment that can be any value, captured as a parameter (`[scanId]`).
- **`useRouter`**: the Next.js hook for navigating between routes programmatically.
- **`useParams`**: the hook for reading dynamic URL segments inside a client component.
- **Layout**: a wrapper component in App Router that persists across page navigations inside its folder.
