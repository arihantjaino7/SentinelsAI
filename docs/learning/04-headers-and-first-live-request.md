# A4 — First real agent

> **Status:** done. `backend/agents/headers.py` makes one real, live HTTP GET request
> and checks four security-relevant response headers. Verified against
> `https://example.com` (fails all four — it sets none of them) and `https://github.com`
> (passes all four, with real header values captured as evidence).

## What we built

`HeadersAgent`, the first subclass of `BaseAgent` (from A3) that actually does
something. It makes one HTTP GET request to the target URL, checks four response
headers that browsers use to enforce security rules, and produces one `Finding` per
header — `FAIL` if it's missing, `PASS` if it's present, with the real header value
kept as evidence either way.

The four headers: `Content-Security-Policy`, `Strict-Transport-Security`,
`X-Content-Type-Options`, `X-Frame-Options`. All four are read-only observations from a
normal page load — nothing here sends anything a regular visitor's browser wouldn't
already send.

This is also the first code in the project that talks to the real internet, and the
first real test of A3's `run()`/`scan()` contract: if the request fails (DNS error,
timeout, connection refused), `scan()` raises and A3's `run()` catches it automatically
— nothing new had to be written for that.

## The one big idea: HTTP response headers

When a server answers a request, it doesn't just send back a page — it sends a block of
`Name: value` lines first, called headers. They carry metadata: how big the response
is, what type of content it is, and — what this project cares about — instructions to
the browser about what security rules to enforce.

Try it yourself:

```bash
curl -I https://example.com
```

```
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Length: 1256
```

A security header is just one more line in that same block —
`Strict-Transport-Security: max-age=31536000` is structurally no different from
`Content-Type: text/html`. The server doesn't do anything special to send one; what
makes it a "security" header is what the **browser** promises to do when it sees that
name (refuse to load in a frame, refuse to downgrade to HTTP, etc). It's an instruction
to the browser, not something the server enforces itself.

## Making the actual request

```python
response = await context.client.get(context.url, follow_redirects=True)
headers = response.headers
```

`context.client` is the shared `httpx.AsyncClient` from `ScanContext` (A3) — the thing
that actually speaks HTTP. `await client.get(...)` is a real network wait: exactly the
kind of pause A3's egg example was standing in for. While this one request is in
flight, the event loop is free to run the other four agents' requests at the same time.

Two details worth knowing:

- **`follow_redirects=True`** — by default `httpx` does *not* follow redirects; a GET to
  a URL that responds `301 Moved Permanently` just hands back that redirect, not the
  page it points to. Redirect responses rarely set meaningful security headers, so
  without this we'd sometimes grade the wrong page.
- **`response.headers` is case-insensitive.** HTTP header names officially don't care
  about case, and different servers really do send them differently
  (`X-Frame-Options` vs `x-frame-options`). `headers.get("x-frame-options")` works no
  matter how the server capitalized it — a plain Python `dict` would not do this for
  you.

## The actual code

```python
async def scan(self, context: ScanContext) -> list[Finding]:
    response = await context.client.get(context.url, follow_redirects=True)
    headers = response.headers
    return [
        self._check(headers, "content-security-policy", id_="missing-csp", ...),
        self._check(headers, "strict-transport-security", id_="missing-hsts", ...),
        self._check(headers, "x-content-type-options", ...),
        self._check(headers, "x-frame-options", ...),
    ]
```

One request, four checks against the same response — faster than four separate
requests, and it matches what one real page load actually looks like.

```python
@staticmethod
def _check(headers, header_name, *, id_, title, severity, description="", remediation=""):
    value = headers.get(header_name)
    if value is None:
        return Finding(..., status=Status.FAIL, severity=severity,
                        evidence=f"No '{header_name}' header in the response.")
    return Finding(..., status=Status.PASS, severity=Severity.INFO,
                    evidence=f"{header_name}: {value}")
```

Worth noticing:

- We return a `Finding` for **PASS as well as FAIL**. If we only reported problems, the
  report couldn't tell "we checked this and it was fine" from "we never checked this at
  all" — and a report that's a wall of failures with nothing passing also just looks
  broken.
- The `*` before `id_` makes every argument after it keyword-only — you must call
  `_check(headers, name, id_="x", title="y", ...)`, not positionally. `_check` takes
  seven arguments; without this, swapping `title` and `id_` by accident wouldn't error,
  it would just quietly produce a finding with the wrong label.
- `@staticmethod` because `_check` doesn't touch `self` — it's a plain function that
  happens to live on the class.

## Try it

Run `HeadersAgent` against `https://example.com` (fails everything) and then
`https://github.com` (passes everything) and compare the findings.

Point it at a URL that can't resolve at all, e.g.
`https://this-domain-does-not-exist-zzzz.invalid`, and confirm you get a clean
`AgentResult` back with `error` set and `findings=[]` — not a crash. That's A3's `run()`
catching a *real* failure for the first time.

Compare the raw headers with `curl -sI https://github.com` against what the agent
reports as evidence — they should match exactly.

## Words worth knowing

- **HTTP response header** — a `Name: value` metadata line sent before a response
  body; some names are instructions the browser is expected to enforce.
- **`httpx.AsyncClient`** — the async HTTP client this project uses; one shared instance
  per scan, passed in via `ScanContext`.
- **`follow_redirects`** — an `httpx` option; without it, a redirecting URL hands back
  the redirect itself, not the page it points to.
- **Keyword-only arguments** (`*` in a signature) — arguments after it can only be
  passed by name, turning an argument-order mistake into an immediate error.

---

**Next:** A5 — Orchestrator v1. A real `/scan` POST endpoint that normalizes a URL,
runs `HeadersAgent`, and returns a real `ScanReport` — the first end-to-end
request/response cycle in the project.
