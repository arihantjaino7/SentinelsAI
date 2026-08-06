# A14 — It talks

> **Status:** done. Typing a URL into `localhost:3000` and clicking Inspect
> runs a real scan against the real backend and shows the score, grade, and
> findings on screen. The backend gained CORS support so the browser
> actually allows this.

## What we built

Three changes: the backend now sends CORS headers (`backend/main.py`) so
the browser will let our frontend read its responses; the frontend gained a
way to talk to the backend over HTTP (`frontend/lib/api.ts`); and
`page.tsx` became interactive — it remembers what you typed, whether a scan
is running, and what result came back.

## The one big idea: state

A component is just a function, and functions forget everything the moment
they return. But a page needs to *remember* things — what you typed,
whether a scan is running. That's what **state** is: a variable that, when
you change it, tells React "redraw the screen."

```jsx
const [count, setCount] = useState(0);
// count      -> the current value
// setCount() -> change it AND trigger a redraw
```

A plain variable doesn't work for this. If you wrote `let count = 0` inside
the component function, every redraw would call the function again from
scratch and reset it back to `0`. `useState` is what makes a value survive
between redraws, and what tells React to redraw at all when it changes.

Our page uses four of these side by side:

```jsx
const [url, setUrl] = useState("");
const [isScanning, setIsScanning] = useState(false);
const [report, setReport] = useState<ScanReport | null>(null);
const [error, setError] = useState<string | null>(null);
```

Each one answers an independent question — what's typed, are we busy, did
we get a report, did we get an error.

## Second idea: CORS — the browser's "who's allowed to ask" rule

Our frontend runs on `localhost:3000`, our backend on `localhost:8000`.
Different port means the browser treats them as completely different
websites — this is the **same-origin policy**, and it exists so a random
website you visit can't quietly read data from your bank's site just
because your browser happens to be logged in there.

Without any changes, a request from the frontend to the backend would still
run and get an answer — but the browser would throw the answer away and
report an error, because the backend never said the frontend was allowed to
read it.

**CORS** is the backend explicitly granting that permission:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

Only these two exact addresses are allowed — not `allow_origins=["*"]`,
which would let any website on the internet trigger a scan through a
visitor's browser. Worth knowing: CORS only restrains *browsers*. A tool
like `curl` ignores it completely and can call the API directly either
way — CORS isn't API security, it's a browser-only politeness rule.

## The actual code

Calling the backend uses `fetch` — the browser's built-in HTTP client:

```typescript
export async function downloadReportPdf(report: ScanReport): Promise<void> {
  const response = await fetch(`${API_BASE}/scan/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });

  if (!response.ok) {
    throw new Error(`PDF export failed (${response.status})`);
  }
  // ...save the response as a file
}
```

One surprising thing about `fetch`: it does **not** raise an error for a 404
or 500 response — only for a request that never completed at all (no
connection, DNS failure). A "bad" response still counts as success as far
as `fetch` is concerned, which is why `!response.ok` has to be checked by
hand.

The URL input is a **controlled input** — React state, not the browser,
owns what's shown in the box:

```jsx
<input
  value={url}
  onChange={(event) => setUrl(event.target.value)}
/>
```

Every keystroke calls `setUrl`, which updates state, which redraws the box
showing the new text. Submitting the form calls `event.preventDefault()`
first — without it, the browser's decades-old default behavior kicks in:
reload the whole page and throw away all your state.

## Try it

- Comment out the `add_middleware(...)` block in `main.py`, restart, and
  try a scan from the browser. It fails — but the exact same request via
  `curl` still works fine. That's the browser-only part of CORS, proven.
- Delete `onChange` from the `<input>`. Typing stops doing anything, because
  nothing updates state anymore.
- Remove `event.preventDefault()` from the submit handler. Submitting now
  reloads the whole page instead of running the scan.

## A few words worth knowing

- **State** — a variable that redraws the UI when it changes; created with
  `useState`.
- **Controlled input** — an input whose value comes from state, not from
  the browser's own memory of what you typed.
- **`fetch`** — the browser's built-in way to make HTTP requests. Doesn't
  throw on a bad status code, only on a failed connection.
- **Origin** — scheme + host + port. All three must match to count as "the
  same site."
- **CORS** — headers a server sends to tell the browser which other
  origins are allowed to read its responses.

---

**Next:** A15 — the real report screen.
