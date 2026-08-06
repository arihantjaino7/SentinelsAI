# A12 — AI analyst

> **Status:** done. `backend/ai/analyst.py` asks an LLM (Groq's free API) to
> write a short, plain-English summary of a scan. If there's no API key, or
> the call fails for any reason, the scan still returns a complete report —
> the summary field is just empty.

## What we built

One function, `summarize()`. It takes a scan's URL, score, grade, and
findings, and asks a language model to turn them into 2-4 plain sentences a
non-expert could read. It's called right after scoring, and it's the only
place in the whole project that touches an LLM.

(Side note: this was originally built against Anthropic's API. Arihant asked
to switch to Groq instead, since its free tier needs no credit card. The
shape of the code didn't change at all — just which URL it calls.)

## The one big idea: graceful degradation

A feature "degrades gracefully" when losing it doesn't break anything else —
you just get a slightly plainer result. Think of a restaurant's specials
board: if the person who writes it calls in sick, you don't close the
restaurant, you just serve the regular menu without today's specials.

`summarize()` is built exactly like that:

```python
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    return ""
...
except Exception:
    return ""
```

No API key? Return an empty string. The call fails for any reason at all —
bad key, network blip, rate limit? Also return an empty string. Every single
path through this function returns *something* usable, and the rest of the
report (score, grade, every finding) was already fully computed before this
line even runs. Worst case, the user loses one paragraph — nothing else.

## The actual code

```python
async def summarize(url, score, grade, findings) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return ""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": _MODEL,
                    "max_completion_tokens": 800,
                    "reasoning_effort": "low",  # keep it fast and cheap
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": _build_prompt(url, score, grade, findings)},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""
```

Calling an LLM is really just an HTTP POST — the same shape as any other API
call this project makes. `messages` has a `"system"` entry (instructions for
how the model should behave) and a `"user"` entry (the actual data — our
findings). `response.raise_for_status()` turns a bad HTTP status (401, 429,
etc.) into a Python exception, which the `except Exception` below then
swallows — one line doing what would otherwise need a manual status check.

A real bug found while testing: `max_completion_tokens` was originally 200,
and the summary kept coming back empty. Turns out this model "thinks" before
it writes, and that thinking eats into the same token budget — 200 wasn't
enough room left for the actual sentences. Raising it to 800 and setting
`reasoning_effort: "low"` fixed it.

## Try it

- Rename `backend/.env` temporarily, restart the server, and POST to
  `/scan`. Every field comes back full except `summary`, which is `""`.
- Put a real `GROQ_API_KEY` back and scan the same site again — `summary` is
  now a real paragraph, written from that scan's actual findings.
- Read `_SYSTEM_PROMPT` in `backend/ai/analyst.py` — it's just plain English
  instructions telling the model how to write, no special syntax involved.

## A few words worth knowing

- **Graceful degradation** — an optional feature can fail or be missing
  entirely without breaking the core product.
- **`os.environ`** — Python's view of environment variables; `.get()`
  returns `None` if a key was never set.
- **`.env` file** — keeps secrets like API keys out of the actual code (and
  out of git).
- **`response.raise_for_status()`** — turns a bad HTTP response into a
  Python exception you can catch, instead of checking the status by hand.

---

**Next:** A13 — Next.js up. The frontend begins.
