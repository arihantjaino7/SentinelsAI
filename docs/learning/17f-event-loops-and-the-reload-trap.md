# 17f — Two event loops on Windows, and the `--reload` trap

> **Status:** done. `backend/report/pdf.py` now works under
> `uvicorn main:app --reload` on Windows. This note is about a real bug
> that was found and fixed, not a hypothetical.

## What we built

The README says to start the backend with `uvicorn main:app --reload`.
Following that literally on a fresh clone, everything worked — scanning,
scoring, the AI summary — except **PDF export**, which failed with a blank
`500 Internal Server Error`. The cause had nothing to do with our PDF
code: on Windows, `--reload` quietly switches the whole process to a kind
of event loop that can't start another program. Playwright's entire job is
to start another program (a browser). Fixed in `backend/report/pdf.py` by
giving the PDF work its own, correct kind of loop, on its own thread.

## The one big idea: an event loop is a specific thing, and Windows has two

You've already met `async`/`await` as "the event loop juggles many waiting
tasks at once" — like tending a toaster and a pot of water at the same
time instead of standing and staring at one. That's still true. What's new
here: "the event loop" isn't one single thing. It's an actual object, and
Python ships more than one version of it for Windows:

| Loop | Can run coroutines? | Can start another program? |
|---|---|---|
| **Proactor** (Windows default) | yes | **yes** |
| **Selector** (the other one) | yes | **no** |

Both loops can `await` things just fine. Only Proactor can start a
**subprocess** — another program your program launches and talks to.
Playwright needs exactly that: a real Chromium browser, running as its own
separate process, not a Python library.

Here's the trap: uvicorn's own code (`uvicorn/loops/asyncio.py`) does this
when `--reload` is on, on Windows:

```python
if sys.platform == "win32" and use_subprocess:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

`--reload` needs to manage its own worker processes, so it deliberately
switches Windows to the Selector loop — the one that *can't* start
subprocesses. That's a reasonable choice for uvicorn's file-watching, but
it quietly takes away an ability our PDF code depends on. Try to start a
subprocess on that loop and you get a bare `NotImplementedError`, no
message at all — which is exactly what showed up as our blank 500.

## The fix: build the right loop by hand, on a spare thread

A loop belongs to whichever thread runs it, and our server's main thread is
already busy running uvicorn's (Selector) loop. So the fix moves the PDF
work to a separate thread, and builds a Proactor loop directly on it:

```python
def _render_pdf_on_own_loop(html: str) -> bytes:
    loop = asyncio.ProactorEventLoop()      # built directly, not asked for
    try:
        return loop.run_until_complete(_render_pdf(html))
    finally:
        loop.close()


async def generate_pdf(report: ScanReport) -> bytes:
    html = render_html(report)

    if sys.platform != "win32":
        return await _render_pdf(html)

    return await asyncio.to_thread(_render_pdf_on_own_loop, html)
```

- **`asyncio.ProactorEventLoop()` directly**, not `asyncio.new_event_loop()`.
  The normal way of asking for a loop goes through the *policy* — a
  process-wide setting for "what kind of loop to hand out" — and the
  policy is exactly what uvicorn overrode. Asking it would just hand back
  another broken Selector loop. Building the class directly skips that.
- **`asyncio.to_thread`** hands the work to a spare thread that's free to
  run its own loop, and `await`s the result without freezing the server.
  Same tool the TLS agent (A8) already uses to keep a blocking handshake
  off the main loop.
- **The `sys.platform != "win32"` check** — this whole Selector-vs-Proactor
  split is Windows-only, so Linux/macOS just take the normal path.

## Try it

- On the fresh clone, start the backend as `uvicorn main:app` (no
  `--reload`) and download a PDF — it works, because the default loop
  never got swapped out.
- Start it again with `--reload`, before the fix — blank 500 in the
  browser, `NotImplementedError` in the server's terminal.
- With the fix in place, hit `/health` repeatedly while a PDF is
  generating. Measured: it answered in 2-3ms each time, proving the PDF
  work is really on a separate thread, not blocking the server.

## Words worth knowing

- **Event loop** — the object that actually runs coroutines. More than one
  implementation exists.
- **Subprocess** — another program your program starts and talks to.
- **Event loop policy** — a global setting deciding which loop kind gets
  built; anyone in the process can change it.
- **`asyncio.to_thread`** — run a blocking function on a spare thread and
  `await` the result, keeping the main event loop free.

---

**Next:** [`18`](18-shipping-and-clean-room-verification.md) — how this bug
was actually found: testing the setup instructions themselves, on a
genuinely fresh clone.
