# 43 — Repo AI: "what you got wrong"

> **Status:** done. Repo scans now get a plain-English summary that leads
> with the single worst mistake, and "Fix with AI" on a repo finding returns
> a before/after code diff instead of an Apache/Nginx config block. Verified
> live against `octocat/Hello-World`: the summary correctly named the
> missing `.gitignore` as the worst problem, and with `GROQ_API_KEY` removed
> the same scan still completed fully (score, checklist, readiness score —
> only `summary` came back empty).

## What we built

Two new prompts in `ai/prompts.py` — `REPO_ANALYST_SYSTEM` and
`REPO_FIX_SYSTEM` — and one new parameter on an existing function,
`ai/analyst.py`'s `summarize(..., target_type="url")`. No new files beyond
that, and nothing in `ai/fixes.py` or `ai/chat.py` changed at all.

## The one idea worth naming: branch inside the shared function, not at every call site

The URL analyst prompt and the repo analyst prompt genuinely need different
wording — PLAN-v3 was explicit that the repo summary should "lead with the
mistake, in plain English," written for someone who shipped AI-generated
code and doesn't know what's wrong with it. That's a different opening
sentence than the URL side's "mention the most serious problem if one
exists." So there have to be two system prompts. The question is: where does
the decision of *which one* live?

Standalone example — the same shape, about ordering a coffee instead of a
security scan:

```python
def make_receipt(item, size, is_member=False):
    header = "MEMBER RECEIPT" if is_member else "RECEIPT"
    return f"{header}\n{size} {item}"
```

`make_receipt` doesn't ask its caller to pick between two receipt-printing
functions — it takes one extra fact (`is_member`) and decides internally.
Every existing caller that doesn't pass `is_member` keeps getting the
regular receipt, unchanged.

`summarize()` does the same thing with `target_type`:

```python
async def summarize(url, score, grade, findings, target_type: str = "url") -> str:
    messages = (
        build_repo_analyst_messages(url, score, grade, findings)
        if target_type == "repo"
        else build_analyst_messages(url, score, grade, findings)
    )
    result = await call_groq(messages, max_tokens=800, reasoning_effort="low")
    return result or ""
```

`orchestrator.py` (the URL side) never changed — it still calls
`summarize(url, score, grade, findings)` exactly as before, so it silently
keeps getting `build_analyst_messages`. `repo_orchestrator.py` (note 42) is
the one caller that passes `target_type="repo"` explicitly.

## The fix prompt takes a different branching signal: the data itself

`build_fix_messages(finding)` has only ever taken one argument — the
finding — so there's no `target_type` to pass through here even if we wanted
one. Instead it reads a fact the finding already carries:

```python
def build_fix_messages(finding: Finding) -> list[dict]:
    is_repo_finding = finding.file_path is not None
    ...
    return [
        {"role": "system", "content": REPO_FIX_SYSTEM if is_repo_finding else FIX_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]
```

`models.Finding.file_path` was already documented, back in note 36/R3, as
"`None` for URL-scan findings" — every repo finding sets it, every URL
finding never does. That's a real, load-bearing distinction already baked
into the data, so re-deriving it from a passed-in flag would just be
duplicating information the `Finding` already has. `ai/fixes.py`'s one call
site (`build_fix_messages(finding)`) needed zero changes for this to work.

## Why framework_examples needed new wording, not a new field

`FixSuggestion.framework_examples` (a `dict[str, str]`) was designed for the
URL side to hold things like `{"Apache": "...", "Nginx": "..."}` — server
config blocks. A repo finding isn't missing a server header; it's one wrong
line in one real file already sitting in front of the reader. Reusing the
same field for `{"Before": "<vulnerable line>", "After": "<fixed line>"}`
needed no model change at all — just telling the LLM, in `REPO_FIX_SYSTEM`,
that this field means something different for a repo finding:

> "framework_examples MUST be a Before/After code diff for the exact file
> given, not a generic server config — this is a source-code finding, not a
> live-server one."

## Try it

```bash
curl -s -X POST localhost:8000/repo/scan -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/octocat/Hello-World"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['summary'])"
```

Real output from this exact run:

> "The single most important mistake is the absence of a .gitignore file,
> which is located in the repository root... Overall the codebase is in
> fair shape but not deployment-ready..."

That's the real worst finding in that repo (a `MEDIUM`-severity
Configuration `FAIL` — see note 42) — the AI didn't invent a more dramatic
problem that isn't there.

- Stop the backend, unset `GROQ_API_KEY` (or set it to an empty string —
  see note "gotcha" below), restart, and re-run the same scan: it still
  returns 200 with a full score/checklist/readiness, `summary: ""`.
- Call `POST /scans/{id}/findings/{key}/fix` on a repo secrets finding and
  check `framework_examples` — it should be a `Before`/`After` pair showing
  the masked line, not an Apache block.

**A real gotcha hit while verifying this milestone, worth knowing about:**
`uvicorn --reload` on Windows can leave an orphaned worker process alive
after you think you've stopped it — killing the reloader doesn't always
kill its spawned child, and that child keeps answering on the port with
whatever `.env` it loaded at its own startup. If a "no API key" test keeps
returning results *with* a summary, check `netstat -ano` for more than one
process actually listening on the port before assuming the code is wrong.

## Words worth knowing

- **Internal branching vs. a second function** — when two variants of a
  behaviour share almost everything and differ only in wording/prompt, one
  function with a parameter (or a fact read off the input, like
  `file_path`) keeps every existing caller working, instead of forcing every
  caller to choose between `summarize_url()` and `summarize_repo()`.

---

Phase R-C (R9 checklist/readiness, R10 this note) is now complete. **Next:**
Phase R-D — R11 gives the site a real front door (`/` becomes a
url-or-repo landing page, with a `GET /repo/stream` SSE endpoint mirroring
`/scan/stream`), then R12 adds the file-tree browser.
