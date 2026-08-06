# A16 — Live progress and Server-Sent Events

> **Status:** done. The waiting screen now lights up each agent the instant it
> actually finishes, instead of five names pulsing together and then all
> appearing at once.

## What we built

A second way to run a scan, alongside the original `POST /scan`. `backend/orchestrator.py`
gained `run_scan_stream()`, which reports each agent's result the moment that
agent is done. `backend/main.py` gained `GET /scan/stream`, which turns that
into a live stream the browser can read. `frontend/lib/api.ts` gained
`streamScan()`, which opens that stream and updates the page as each result
arrives. `POST /scan` still exists unchanged — this is a second option, not a
replacement.

## The one big idea: `asyncio.gather` vs `asyncio.as_completed`

A11 already made the five agents run *concurrently* with `asyncio.gather` — it
starts all five at once, but only hands back results after **all** of them are
done, in the order you listed them.

`asyncio.as_completed` runs the exact same coroutines, concurrently, the same
way — but hands each one back **the moment it finishes**, in real finishing
order:

```python
import asyncio

async def task(name, delay):
    await asyncio.sleep(delay)
    return name

async def main():
    coros = [task("slow", 2), task("fast", 0.3), task("medium", 1)]
    for coro in asyncio.as_completed(coros):
        print(await coro)   # fast, medium, slow -- real finishing order

asyncio.run(main())
```

Nothing about *how fast* the work happens changes — same concurrency, same
total time. The only difference is whether you find out about each result as
it's ready, or all together at the end. That's why `run_scan_stream` uses it:

```python
coros = [agent_cls().run(context) for agent_cls in AGENTS]
for coro in asyncio.as_completed(coros):
    result = await coro
    agent_results.append(result)
    yield ("agent", result)
```

A function with both `yield` and `await` is called an **async generator** —
the consumer loops over it with `async for` instead of plain `for`.

## The other new idea: Server-Sent Events

Ordinary HTTP is "client asks once, server answers once." **Server-Sent
Events (SSE)** get around that: the server sends one HTTP response as usual,
but never closes it — it keeps writing more text into the same open
connection, and the browser reads that as a sequence of separate messages.

```
event: agent
data: {"agent": "dns", "duration_ms": 155}

event: done
data: {"score": 54, "grade": "F"}

```

Each message is an `event:` name plus a `data:` payload (just text — SSE
doesn't parse JSON for you), and a blank line ends each message.

FastAPI's `StreamingResponse` builds a response from a generator instead of one
finished value, sending each piece of text as it's produced:

```python
async def events():
    async for event_name, payload in run_scan_stream(url):
        yield _sse(event_name, payload.model_dump_json())

return StreamingResponse(events(), media_type="text/event-stream")
```

One consequence: once the first byte of a streaming response goes out, the
status code (`200`) is locked in. So a bad URL can't become a clean `400` the
way it does for `POST /scan` — instead it shows up as an `event: failed`
message inside an otherwise-`200` stream.

On the browser, `EventSource` is the built-in client for reading an SSE
stream, no library needed. Two things about it shaped the code around it: it
can only send `GET` (no body — hence `?url=...` as a query parameter instead
of JSON), and it **auto-reconnects** whenever the connection closes, even a
normal successful end. Left alone, a finished scan would silently trigger a
second scan a few seconds later — the fix is calling `source.close()` once the
`"done"` event arrives.

`streamScan()` can't just `return` one value the way A14's `runScan` did — a
scan produces six separate results over time (five agents plus a report), and
a `Promise` only ever resolves once. Instead it takes callback functions and
calls the right one as each result shows up:

```typescript
streamScan(url, {
  onAgent: (result) => setAgentResults((prev) => ({ ...prev, [result.agent]: result })),
  onDone: (report) => setReport(report),
});
```

`{ ...prev, [result.agent]: result }` copies everything already known into a
*new* object, then adds the latest agent's result — it has to be new because
React checks whether state changed identity, not its contents; mutating
`prev` in place would look like nothing happened.

## Try it

1. Run this note's `as_completed` example with delays in a "wrong" order and
   confirm `gather` prints results in declared order while `as_completed`
   prints them in actual finishing order.
2. Remove the `source.close()` call after `"done"` and watch the Network tab
   a few seconds after a scan finishes — a second request fires on its own.
3. Run `curl -D- -o/dev/null "localhost:8000/scan/stream?url=bad-scheme://x"`
   and confirm the status is still `200` — the real error is inside the stream.
4. Watch the five agent names in `page.tsx` light up one at a time, in a
   different order on different scans, matching real completion time.

## A few words worth knowing

- **`asyncio.as_completed`** — runs coroutines concurrently, same as `gather`,
  but yields each result as it finishes rather than all together at the end.
- **Async generator** — a function using both `async`/`await` and `yield`.
- **Server-Sent Events (SSE)** — a one-way stream of text messages over one
  long-lived HTTP response.
- **`StreamingResponse`** — a response built from a generator instead of one
  finished value.
- **`EventSource`** — the browser's built-in SSE client. GET-only, no body,
  auto-reconnects unless you call `.close()`.

---

**Next:** A17 — PDF export, using a real headless browser to print the report.
