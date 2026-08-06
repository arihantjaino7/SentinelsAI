# A3 — The contract

> **Status:** done. `backend/agents/base.py` defines `ScanContext` and `BaseAgent`.
> Verified: a bare `BaseAgent()` refuses to instantiate, a working subclass returns a
> populated `AgentResult`, and a subclass whose `scan()` raises still returns a clean
> `AgentResult` with the error captured instead of crashing.

## What we built

Five agents (Headers, Recon, TLS, Exposure, DNS) are coming. They all need to look the
same from the outside — same inputs, same output — or the orchestrator that calls them
would need a special case for each one. `backend/agents/base.py` is that shared shape:

- **`ScanContext`** — a small bundle of "everything an agent needs" (the target URL and
  a shared HTTP connection), built once per scan and handed to all five agents.
- **`BaseAgent`** — a base class that *requires* every subclass to write a `scan()`
  method, and in return gives it a `run()` method for free that adds timing and
  crash-proofing.

No real scanning yet — this is just the socket every future agent plugs into.

## The one big idea: async and await

Normal Python runs one line, waits, runs the next. That's fine until a line means "wait
for the network" — that can take hundreds of milliseconds, during which a normal
program just sits frozen. If we're running five agents, we don't want four of them
stuck waiting for the fifth to finish its network call before they even start theirs.

`async`/`await` lets Python pause a function at the exact point it's waiting on
something, and go do other work in the meantime. Standalone example, nothing to do with
security — boiling two eggs:

```python
import asyncio

async def boil_egg(name, seconds):
    print(f"{name}: water on")
    await asyncio.sleep(seconds)   # "wait", without freezing everything else
    print(f"{name}: done")

async def main():
    await asyncio.gather(
        boil_egg("egg A", 2),
        boil_egg("egg B", 2),
    )

asyncio.run(main())
```

This takes about **2 seconds total, not 4** — both eggs "boil" during the same window.
There's still only one thread doing one thing at a time; what's really happening is
that while egg A is waiting, Python lets egg B start, and hops back and forth between
them at each `await`. `asyncio.gather` is what says "start all of these, and let them
take turns waiting" — that's the entire trick behind five agents finishing in about the
time of the slowest one, not the sum of all five.

`scan()` is declared `async def` because every real agent's version of it will `await`
a real HTTP call (starting next note). This file has no network code yet, so nothing
here proves the speedup — that comes later once there are real requests to time.

## The other new idea: abstract base classes

We want Python itself to enforce "every agent must have a `scan()` method" — not a
comment we hope people read. Standalone example, nothing about security:

```python
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float: ...

class Square(Shape):
    def __init__(self, side):
        self.side = side
    def area(self) -> float:
        return self.side ** 2

Shape()           # TypeError: can't instantiate abstract class Shape
Square(4).area()  # 16 — fine
```

If a subclass forgets to write `area()`, trying to create it raises a `TypeError`
immediately — not later, with a confusing error from whoever eventually calls
`.area()`. `BaseAgent` uses the same pattern: `scan()` is `@abstractmethod`, so a
subclass that forgets it can't even be constructed.

## The actual code

```python
@dataclass
class ScanContext:
    url: str                    # normalized target, e.g. "https://example.com"
    client: httpx.AsyncClient   # one shared connection pool for all 5 agents
```

`@dataclass` just auto-generates `__init__` from the two fields above — no need to
write it by hand. `ScanContext` is built once per scan and passed to every agent, so no
agent opens its own connection or re-figures-out the target URL.

```python
class BaseAgent(ABC):
    name: str = "base"

    @abstractmethod
    async def scan(self, context: ScanContext) -> list[Finding]:
        raise NotImplementedError

    async def run(self, context: ScanContext) -> AgentResult:
        start = time.perf_counter()
        error: str | None = None
        findings: list[Finding] = []
        try:
            findings = await self.scan(context)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = int((time.perf_counter() - start) * 1000)
        return AgentResult(
            agent=self.name, findings=findings, duration_ms=duration_ms, error=error,
        )
```

- Subclasses only ever write `scan()`. They inherit `run()` unchanged — so timing and
  error-catching happen exactly the same way for every agent, instead of five people
  each having to remember to write their own `try/except`.
- `except Exception` is deliberately broad. That's the whole point: whatever goes wrong
  inside one agent (a DNS error, a timeout, a bug we didn't anticipate), it must never
  take down the other four agents' scans. That's the CLAUDE.md rule: agents never crash
  the scan.
- `findings` starts as `[]` before the `try`, so even if `scan()` raises immediately,
  `run()` still has a valid (empty) list to return.

## Try it

Write a subclass that deliberately raises inside `scan()`, call `.run()` on it, and
check you get a clean `AgentResult` back with `error` set and `findings=[]` — no
traceback, no crash.

Then write a subclass that forgets to define `scan()` at all and try to instantiate it —
confirm you get `TypeError: Can't instantiate abstract class ... without an
implementation for abstract method 'scan'`.

Paste the `boil_egg` example above into a file and run it, then change
`asyncio.gather(...)` to `await boil_egg(...)` twice in a row instead — watch the total
time roughly double.

## Words worth knowing

- **Coroutine** — a function defined with `async def`; calling it doesn't run it, it
  hands back a paused "plan" that something else has to drive.
- **`await`** — the only point a coroutine can pause, so other work can run during a
  wait.
- **Abstract base class (ABC)** — a class that can't be instantiated until every
  `@abstractmethod` has been overridden by a subclass.
- **Dependency passing** — building a shared resource (like the HTTP client) once, from
  the outside, and handing it in, instead of letting every agent build its own.

---

**Next:** A4 — First real agent. `HeadersAgent` becomes the first subclass of
`BaseAgent` that does something real: an actual HTTP request against a live site,
checking for missing security headers.
