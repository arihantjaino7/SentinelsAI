# A8 — TLS agent

> **Status:** done. `backend/agents/tls.py` — `TLSAgent`, the third real agent, checks
> a site's TLS certificate and protocol version.

## What we built

`TLSAgent` is the first agent that doesn't use HTTP at all. Instead of `httpx`, it
opens a raw TCP socket and does a real TLS handshake itself, using Python's built-in
`ssl` module — the same layer HTTPS has been quietly running on top of the whole time.

Three checks:

- **Is this site even using HTTPS?** If the URL is plain `http://`, that's an instant
  `Critical` finding — there's no certificate to check at all.
- **Certificate verification** — does a real handshake succeed (trusted chain,
  correct hostname)? If not, one finding explains why: expired, self-signed, or wrong
  hostname.
- **Expiry and protocol version** — if the handshake succeeds, read the real expiry
  date and the negotiated TLS version off the certificate.

Verified against `badssl.com` (a public test site with deliberately broken
certificates) covering expired, self-signed, and hostname-mismatch cases, plus real
sites and a plain-HTTP target.

## The one big idea: blocking code would freeze the event loop

Everything before this agent used `httpx`, which was built to cooperate with
`asyncio` — `await client.get(...)` pauses politely and lets other agents run while it
waits. `socket` and `ssl`, by contrast, are old-school **blocking** APIs: once you call
`sock.recv()` or `wrap_socket()`, nothing else in the program runs until it finishes.

If we called them directly inside `async def scan()`, the entire server would freeze
for the whole handshake — every other agent's `await` would just sit there stuck
behind it.

`asyncio.to_thread` fixes this: it runs an ordinary blocking function on a separate
background thread, and hands back something you *can* `await`. From the event loop's
point of view it behaves like any other well-behaved async call, even though the
function itself has no idea `asyncio` exists.

```python
import asyncio, time

def blocking_nap(seconds):
    time.sleep(seconds)      # a REAL block, not asyncio.sleep
    return f"slept {seconds}s"

async def ticker():
    for i in range(10):
        print("tick", i)
        await asyncio.sleep(0.1)

async def main():
    # run both AT THE SAME TIME
    await asyncio.gather(asyncio.to_thread(blocking_nap, 1), ticker())

asyncio.run(main())
```

The ticks keep printing steadily during that whole second — proof the blocking
`time.sleep` didn't freeze anything else. This is exactly the mechanism `TLSAgent`
relies on to do a real ~400ms handshake without stalling the rest of the scan.

## The actual code

```python
def _fetch_certificate(hostname, port, timeout):
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            return ssock.getpeercert(), ssock.version()
```

A plain, ordinary function — no `async`/`await` inside it at all. That's on purpose:
it's the function we hand to `to_thread`, which expects a normal blocking callable to
run on another thread. `ssl.create_default_context()` checks the certificate against
trusted CAs and the hostname, just like a browser would. If that check fails, this
function never returns — it raises `ssl.SSLError` instead.

```python
try:
    cert, protocol_version = await asyncio.to_thread(_fetch_certificate, hostname, port, 10.0)
except ssl.SSLError as exc:
    return [Finding(id="tls-cert-invalid", ..., evidence=str(exc), ...)]
```

Notice the arguments come *after* the function name — `to_thread(func, arg1, arg2)` —
not `to_thread(func(arg1, arg2))`, which would call the function immediately on the
main thread and defeat the whole point.

Only `ssl.SSLError` is caught here, deliberately narrow. A DNS failure (unresolvable
hostname) raises a completely different exception, `socket.gaierror`, which is left to
propagate up to the agent's outer `run()` wrapper (from A3) instead — a DNS failure
isn't a fact about this site's TLS setup, it's a fact about whether the site could be
reached at all.

```python
not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
```

`cert["notAfter"]` comes back as a fixed-format string like `'Aug 29 21:41:26 2026
GMT'`. `strptime` reads a string according to a template and turns it into a real
`datetime` — each `%`-code names one piece (`%b` = abbreviated month, `%Y` = year, and
so on).

One thing worth knowing: a certificate's days-until-expiry genuinely changes every
day, so this finding can flip from `PASS` to `WARN` tomorrow with zero code changes.
That's not a bug — A6's "same input, same score" rule is about the *scoring function*,
not about the world staying frozen. The facts change; the rule connecting facts to a
score doesn't.

## Try it

```bash
cd backend
./.venv/Scripts/python.exe -c "
import asyncio, httpx
from agents.base import ScanContext
from agents.tls import TLSAgent

async def main():
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in ['https://example.com', 'https://expired.badssl.com',
                    'https://self-signed.badssl.com', 'http://example.com']:
            ctx = ScanContext(url=url, client=client)
            result = await TLSAgent().run(ctx)
            for f in result.findings:
                print(url, '->', f.status.value, f.title)

asyncio.run(main())
"
```

- `badssl.com` hosts deliberately broken certificates purpose-built for testing tools like this.
- Paste the `blocking_nap`/`ticker` example above into a file, run it, then remove
  `to_thread` (bare `time.sleep(1)` inside the coroutine) and watch the ticks stop
  appearing during that second — that contrast is the whole concept.

## A couple of words worth knowing

- **Socket** — an OS handle for one end of a network connection, identified by `(host, port)`.
- **TLS handshake** — the negotiation where a server presents a certificate before any data flows.
- **`ssl.SSLError`** — raised when certificate verification fails; the message names the real reason.
- **`asyncio.to_thread`** — runs a blocking function on a background thread so it doesn't freeze the event loop.
- **`strptime`** — parses a string into a `datetime` using a format template.

---

**Next:** A9 — Exposure agent. Detecting a publicly exposed `/.env` file, safely.
