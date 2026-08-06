# 28 — AI features: fix suggestions and chatbot

> **Status:** done. Every failing finding has a "Get AI fix" button that generates and caches a six-part remediation guide, and every scan has a chat page that answers questions about it, remembering the conversation.

## What we built

Three things, all built on top of the same Groq client. First, `backend/ai/client.py` and `backend/ai/prompts.py` pulled the actual "talk to the LLM" code out of `analyst.py` into one shared place, so the two new features didn't each reinvent it. Second, AI fix suggestions — click a button on a finding, get back why it's a problem, what an attacker could do, and how to fix it, generated once per finding and reused after that. Third, a chatbot page per scan that answers plain-English questions ("what should I fix first?") using that scan's actual findings, and remembers earlier questions in the same conversation.

## The one big idea: caching by more than one thing at once

The fix suggestions are expensive to generate (a real LLM call, a couple of seconds) but cheap to store. So `backend/storage/fixes.py` caches each one — but the cache key isn't just "which finding." It's **both** the finding *and* a `prompt_version` string from `prompts.py`.

Why two things instead of one? Because a cache keyed only on the finding would go stale the moment we improve the prompt — old, worse answers would sit in the database forever with nothing to invalidate them. Keying on `(finding_id, prompt_version)` fixes that: bump `PROMPT_VERSION` from `"v1"` to `"v2"` anywhere in the codebase, and every old row is instantly orphaned — not deleted, just never matched again — because new requests look for `"v2"` rows that don't exist yet, and generate fresh ones.

A small standalone version of the same idea:

```python
cache = {}

def get_or_compute(key, version, compute_fn):
    cache_key = (key, version)
    if cache_key not in cache:
        cache[cache_key] = compute_fn()
    return cache[cache_key]

get_or_compute("apple", "v1", lambda: "recipe A")   # computes, stores under ("apple","v1")
get_or_compute("apple", "v1", lambda: "recipe A")   # cache hit, same key
get_or_compute("apple", "v2", lambda: "recipe B")   # different key -> computes fresh
```

Bumping the version is a one-line change, no database migration, no cleanup script — it's the simplest possible cache-invalidation strategy for a case where "the recipe changed" is rare and deliberate.

## The second idea: give the model everything, skip the search step

The chatbot needs to answer questions about *this scan's* findings. The obvious-sounding approach — used by a lot of real chatbots — is called **RAG** (retrieval-augmented generation): store the findings as searchable chunks, and before answering, search for the ones relevant to the question, then hand only those to the model.

We skipped that entirely. `backend/ai/prompts.py`'s `build_chat_messages()` just writes out *all* the findings, the checklist, and the score as plain text and hands the whole thing to the model every time, in the system prompt. A finished scan is maybe 15-25 findings — a few thousand words, comfortably inside what the model can read in one go. RAG earns its complexity when the source material is too big to fit in context (a whole codebase, a document library); at this size, searching for the right chunk is solving a problem that doesn't exist yet, at the cost of a vector database and a step that can itself go wrong (search for the wrong chunk, miss the relevant finding).

## The actual code

`ai/client.py` — one function every AI feature calls:

```python
async def call_groq(messages, *, max_tokens=800, ...) -> str | None:
    api_key = get_api_key()
    if not api_key:
        return None
    try:
        # ... the actual HTTP call ...
        return content.strip()
    except Exception:
        return None
```

Returning `None` — never raising — is the same graceful-degradation contract note 12 introduced for the summary. Now three callers share it: `analyst.py`'s summary falls back to `""`, `fixes.py`'s fix generation returns `None` (the endpoint turns that into a 503, not a crash), and `chat.py` does the same. One rule, written once, obeyed everywhere.

`fixes.py` ties the cache together:

```python
async def get_or_generate_fix(scan_id, finding_key, finding, *, regenerate=False):
    finding_id = get_finding_db_id(conn, scan_id, finding_key)
    if not regenerate:
        cached = get_cached_fix(conn, finding_id, PROMPT_VERSION)
        if cached is not None:
            return cached
    # cache miss (or forced regenerate) -> call the LLM, then save_fix(...)
```

`chat.py`'s `answer()` loads the last ~10 turns from `chat_messages`, builds one big prompt with `build_chat_messages()`, and saves both the question and the answer to the database before returning — so a page refresh doesn't lose the conversation.

On the frontend, `FixSuggestionPanel.tsx` starts idle (just the button), fetches on click, and renders all six fields once they arrive; `FindingRow.tsx` only shows the button for `fail`/`warn` findings, since a passing check has nothing to fix. The new `/scan/[scanId]/chat` page is a plain message list plus a textbox, loading history with `fetchChatHistory` on mount.

## Try it

- Open a finished scan, click "Get AI fix" on any failing header — first click takes a couple of seconds (live call); refresh the page and click it again on the *same* finding and it's instant, because it's now a cache hit.
- Click "Regenerate" on a fix you already have — it overwrites the same cached row rather than adding a second one.
- Open a scan's `/chat` page, ask "what should I fix first?", then ask "why that one?" — the second answer should refer back to the first without you repeating yourself, because history rides along in the prompt.
- Temporarily rename `GROQ_API_KEY` in `backend/.env` to something wrong and try both features again — fix suggestions and chat should fail cleanly (a 503, a clear message), never a raw server error.

## Words worth knowing

- **Cache key** — the value(s) used to look up a stored result. Ours is a pair, not a single value.
- **Cache invalidation** — making stale cached results stop being returned. Here, done by changing what key new requests look for, not by deleting old rows.
- **RAG (retrieval-augmented generation)** — searching a large document for relevant pieces before asking a model about it. Not used here — the whole scan fits in context.
- **Graceful degradation** — a feature failing quietly into a fallback state instead of crashing the rest of the program (introduced in note 12, now shared by three features).

---

**Next:** Phase F — the export system (M17-M19): making PDF export pluggable, then adding JSON and Markdown formats.
