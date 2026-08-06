# 31 — Reject unreachable sites before scanning

> **Status:** done. A nonexistent or unreachable domain now fails fast with "Inspection failed — Couldn't reach {host}..." instead of silently producing a misleading report.

## The bug

Every scanner agent already catches its own exceptions — that's `BaseAgent.run`'s job, so one broken agent can't crash the whole scan (see note 26). But that safety net had a side effect nobody intended: if you typed a domain that doesn't exist, all five agents independently hit the same DNS failure, each quietly recorded it as `AgentResult.error`, and the scan still "finished." With no findings recorded (nothing ever actually ran), the report could come back looking like a clean, high-scoring site — the opposite of the truth.

## The fix: check once, before any agent runs

`orchestrator.py` already had a pattern for this exact situation: `normalize_url()` raises `ValueError` for a malformed URL, and both callers already knew how to turn that into a clear error — `POST /scan` maps it to an HTTP 400, and `GET /scan/stream` emits an `event: failed` message. The frontend was already listening for both and rendering "Inspection failed" with the message. Nothing there needed to change.

So the fix is one new function, called once, before the five agents start:

```python
async def _check_reachable(url: str, client: httpx.AsyncClient) -> None:
    try:
        await client.get(url, timeout=10.0)
    except httpx.TransportError as exc:
        host = urlsplit(url).netloc
        raise ValueError(
            f"Couldn't reach {host}. Check the address — the site may not "
            "exist or isn't responding right now."
        ) from exc
```

## New concept: exception hierarchies

`httpx.TransportError` isn't one specific error — it's a *parent* class. Several more specific exceptions (`ConnectError` for DNS/connection failures, `ConnectTimeout`, `ReadTimeout`, and others) all inherit from it. Catching the parent catches all of them at once, without listing each by name.

```python
# small standalone example
class Animal:
    pass

class Dog(Animal):
    pass

class Cat(Animal):
    pass

def greet(a):
    if isinstance(a, Animal):
        print("hello, animal")

greet(Dog())  # "hello, animal" — Dog IS an Animal, even though we only checked for Animal
```

This is also why the `except` clause here is deliberately narrower than `BaseAgent.run`'s `except Exception`. `TransportError` only matches genuine network problems — DNS failures, refused connections, timeouts. A bug elsewhere (a typo in our own code, say) is a different `Exception` subclass entirely and would NOT be caught here, so it still surfaces as a real 500 instead of being mislabeled "site unreachable."

## Where it's called

Both `run_scan` and `run_scan_stream` create the same kind of `httpx.AsyncClient` before starting any agent — that's the natural place:

```python
async with httpx.AsyncClient(timeout=10.0) as client:
    await _check_reachable(url, client)   # <- new; raises before any agent starts
    context = ScanContext(url=url, client=client)
    ...
```

One extra GET request, ~100-300ms on a real site, buys an honest failure instead of a misleading pass for a fake one.

## Try it

```bash
# Nonexistent domain — should 400, not 200
curl -s -X POST localhost:8000/scan -H "Content-Type: application/json" \
  -d '{"url":"https://this-does-not-exist-xyz123.com"}' -w "\n%{http_code}\n"

# Real site — should still scan normally
curl -s -X POST localhost:8000/scan -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' -w "\n%{http_code}\n"
```

In the browser: type a made-up domain into the home page and submit. You should see "Inspection failed" with a plain-English reason, not a scan result.

## Words worth knowing

- **Exception hierarchy** — exception classes can inherit from a shared parent; catching the parent catches every subclass too.
- **`httpx.TransportError`** — the parent class for network-level failures (DNS, connection refused, timeouts) in the `httpx` library, as opposed to a valid HTTP response with an error status code.
- **Fail fast** — checking a precondition once, up front, instead of letting five separate pieces of code each discover the same problem independently.
