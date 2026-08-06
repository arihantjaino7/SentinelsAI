# A11 — Parallel

> **Status:** done. `orchestrator.py`'s `run_scan()` now runs all five agents with
> `asyncio.gather` instead of one at a time. Measured on a real site: sequential
> took ~2597ms, parallel took ~1308ms — close to the slowest single agent, not the
> sum of all five. **Checkpoint 2 reached.**

## What we built

One change to `orchestrator.py`:

```python
# before: one at a time
agent_results = [await agent_cls().run(context) for agent_cls in AGENTS]

# after: all five, together
agent_results = await asyncio.gather(
    *(agent_cls().run(context) for agent_cls in AGENTS)
)
```

Nothing about any individual agent changed — every agent already worked with
`await`. Only the *order of waiting* changed: instead of "wait for agent 1, then
start agent 2," it's now "start all five, then wait for whichever finishes last."
The result: a full scan roughly halved in time.

## The one big idea: doing things one-at-a-time vs. starting them together

Imagine making tea and toast, one person, no helpers.

**One at a time:** put the kettle on, wait for it to boil, pour the tea. *Then*
put bread in the toaster, wait for it to pop, butter it. Total time = boiling time
+ toasting time.

**Started together:** put the kettle on. *While it's boiling*, put the bread in
the toaster. Now both are happening during the same stretch of time — you're not
doing two things at the exact same instant, but you're not sitting idle waiting
for the kettle either. Total time is roughly whichever one takes longer, not both
added up.

That's the whole idea behind `asyncio.gather`. Each agent spends most of its time
*waiting* — for a web server or a DNS server to reply. Running them "one at a
time" means waiting for agent 1's network reply before even starting agent 2's
request. Running them together means all five requests go out immediately, and
Python just waits for whichever one takes longest, while the other four wait in
the background. There's still only one Python thread doing this — it's not
literally doing five things at the same instant, just overlapping the waiting.

## The actual code

```python
async with httpx.AsyncClient(timeout=10.0) as client:
    context = ScanContext(url=url, client=client)
    agent_results = await asyncio.gather(
        *(agent_cls().run(context) for agent_cls in AGENTS)
    )
```

`*(... for agent_cls in AGENTS)` builds one coroutine per agent and unpacks them
as separate arguments to `gather` — the same as writing
`asyncio.gather(HeadersAgent().run(context), ReconAgent().run(context), ...)` by
hand, just generated from the `AGENTS` list. `gather` always returns results in
the order the coroutines were given, not the order they actually finished in —
important, because the report's agent list needs to be stable, not shuffled by
network timing.

One thing worth knowing: `gather`, by default, if *any* coroutine raises an
exception, immediately throws that exception and **loses the results of every
other coroutine**, even ones that already finished successfully. That's safe here
only because every agent's `run()` (from A3) already catches its own exceptions
and never raises — so this sharp edge never actually gets triggered in practice.

## Try it

Time it yourself, sequential vs. parallel, on the same site:

```bash
cd backend
./.venv/Scripts/python.exe -c "
import asyncio, httpx, time
from agents.base import ScanContext
from orchestrator import AGENTS, normalize_url

async def timed(label, run_all):
    url = normalize_url('github.com')
    async with httpx.AsyncClient(timeout=10.0) as client:
        ctx = ScanContext(url=url, client=client)
        start = time.perf_counter()
        await run_all(ctx)
        print(label, f'{(time.perf_counter() - start) * 1000:.0f}ms')

async def sequential(ctx):
    return [await a().run(ctx) for a in AGENTS]

async def parallel(ctx):
    return await asyncio.gather(*(a().run(ctx) for a in AGENTS))

asyncio.run(timed('sequential', sequential))
asyncio.run(timed('parallel  ', parallel))
"
```

- `sequential`'s total should track the sum of all five agents; `parallel`'s
  should track just the slowest one.
- Compare the `duration_ms` at the top of a real `/scan` response against the sum
  of each agent's own `duration_ms` inside `"agents"` — the top-level number
  should sit close to the *largest* single one, not the sum of all five:
  `curl -X POST localhost:8000/scan -d "{\"url\": \"github.com\"}"`

## Words worth knowing

- **Concurrency** — overlapping the *waiting* on several things at once, without
  necessarily doing them at the literal same instant.
- **Parallelism** — actually doing two things at the same instant (needs multiple
  cores/threads); not what's happening here.
- **`asyncio.gather`** — starts several coroutines together and returns their
  results as a list, in the order they were given, once all of them are done.

---

**Checkpoint 2 reached:** a full 5-agent scan completes in about 1.3-1.5 seconds.

**Next:** A12 — AI analyst. A plain-English summary from the Claude API, layered
on top, that still works fine with no API key present.
