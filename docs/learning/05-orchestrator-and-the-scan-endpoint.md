# A5 — Orchestrator v1

> **Status:** done. `POST /scan` normalizes a URL, runs `HeadersAgent` against it, and
> returns a real `ScanReport`. Verified against the golden path, an empty URL, a
> missing field, an unsupported scheme, and an unresolvable domain — five different
> failure shapes, none of them a crash.

## What we built

Three small pieces that together make the first true end-to-end request:

- **`ScanRequest`** (`models.py`) — the shape of the JSON body a client sends:
  `{"url": "..."}`.
- **`normalize_url()`** and **`run_scan()`** (`orchestrator.py`) — turn whatever string
  the user typed into one canonical URL, run every registered agent against it (for now
  just `HeadersAgent`), and assemble a `ScanReport`.
- **`POST /scan`** (`main.py`) — the endpoint. Accepts a `ScanRequest`, calls
  `run_scan()`, returns a `ScanReport`, and turns a bad URL into a clean `400` instead of
  a crash.

`curl -X POST localhost:8000/scan -d '{"url":"example.com"}'` now returns a real report
with real findings inside it.

## The one big idea: URL normalization

People type URLs inconsistently — `example.com`, `EXAMPLE.com/`, `https://example.com`
are all "the same site" to a human but three different strings to a computer. If we
scanned them as different targets, the same site could get scanned differently just
because of how someone capitalized it.

```python
from urllib.parse import urlsplit

parsed = urlsplit("https://Example.COM/Path?x=1")
print(parsed.scheme)   # 'https'
print(parsed.netloc)   # 'Example.COM'
print(parsed.path)     # '/Path'
```

`urlsplit` breaks a URL into its named pieces instead of us hand-writing regexes to find
where the host ends and the path begins. `normalize_url()` lowercases the scheme and
host (both are case-insensitive by spec) but leaves the path alone (`/Path` and `/path`
really can be different pages on a real server).

## The request lifecycle, and why some failures are 400 and some are 422

Different kinds of bad input get caught at different stages, and that's exactly what
decides the HTTP status code:

- **`{}`** (no `url` key at all) — caught by Pydantic before our code even runs. That's
  a **422**: the request isn't even shaped like a valid request.
- **`{"url": "   "}`** or **`{"url": "ftp://x.com"}`** — shaped correctly, but
  `normalize_url()` rejects the value itself (empty string, unsupported scheme). That's
  a **400**: our own code checked it and said no.
- **A URL that can't resolve** (bad DNS) — this isn't even an error at the endpoint
  level. `HeadersAgent`'s request fails, A3's `run()` catches it, and the scan still
  returns a normal `200` with the failure recorded inside `agents[0].error`.

```python
try:
    return await run_scan(request.url)
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

`HTTPException` is FastAPI's way of saying "stop, and send back this exact status code
and message" instead of a generic crash. `from exc` keeps the original error attached
underneath in the traceback, so a 400 months from now still shows *why* — it doesn't
just say "rejected," it shows the real `ValueError` message that caused it.

## A real bug, briefly

The first version of the scheme check only matched `http://` or `https://` at the start
of a URL, to decide "does this already have a scheme?" That meant `ftp://example.com`
looked like it had *no* scheme, so the code prepended `https://` — producing the
nonsense URL `https://ftp://example.com`, which then failed with a confusing DNS error
several steps later instead of a clean rejection. The fix widens the check to recognize
*any* `word://` prefix, so an unsupported scheme like `ftp` is correctly detected and
rejected with a clear `400` instead of silently mangled.

## The actual code

```python
async def run_scan(raw_url: str) -> ScanReport:
    url = normalize_url(raw_url)
    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=10.0) as client:
        context = ScanContext(url=url, client=client)
        agent_results = [await agent_cls().run(context) for agent_cls in AGENTS]

    findings = [finding for result in agent_results for finding in result.findings]
    ...
```

- `timeout=10.0` matters here for real: without it, `httpx` waits indefinitely for a
  hung server, and one slow site could stall a scan forever.
- The last line flattens a list of lists (each agent's own `findings`) into one flat
  list for the report — read it as nested loops: for each agent's result, for each
  finding in it, collect it.

```python
@app.post("/scan", response_model=ScanReport)
async def scan(request: ScanRequest) -> ScanReport:
    try:
        return await run_scan(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

`response_model=ScanReport` does two things: validates whatever `run_scan()` returns
against the `ScanReport` shape before sending it (so a bug that returns the wrong thing
is caught immediately, not shipped to a client), and documents the exact response shape
in `/docs`.

This is also the first endpoint that genuinely needs `async def` — unlike `/health`,
`/scan` actually awaits something (`run_scan`, which awaits a real HTTP request inside
`HeadersAgent`). A plain `def` endpoint can't contain an `await` at all.

## Try it

Start the server and run the golden path:

```bash
curl -X POST localhost:8000/scan -H "Content-Type: application/json" -d "{\"url\": \"example.com\"}"
```

Notice the response's `"url"` comes back as `"https://example.com/"` even though you
typed no scheme.

Try each of these and check the status code: `{}` (expect 422), `{"url": "   "}`
(expect 400), `{"url": "ftp://x.com"}` (expect 400 with a clear message), and an
unresolvable domain (expect 200, with the error inside `agents[0].error`).

## Words worth knowing

- **URL normalization** — reducing equivalent-but-differently-typed URLs to one
  canonical string.
- **422 vs 400** — 422 means the request body isn't even shaped right (caught
  automatically before our code runs); 400 means it's shaped right but the value inside
  is invalid by our own rules.
- **`HTTPException`** — FastAPI's way of stopping a request with a specific status code
  and message instead of a generic crash.
- **`response_model`** — tells FastAPI to validate the returned object's shape and
  document it in the API docs.

---

**Next:** A6 — Scoring. A pure function that turns a list of findings into a 0–100
score and an A–F grade, deterministically.
