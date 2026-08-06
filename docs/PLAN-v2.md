# Sentinels v2 — Architecture & Incremental Implementation Plan

> **Status:** all 19 milestones shipped. Written 2026-08-02, after the original
> 18-achievement roadmap (`docs/ROADMAP.md`) was completed and shipped;
> implementation ran 2026-08-03 through this file's own Part 6, phase by phase.
>
> **Why this file exists:** Arihant asked for a full redesign/extension plan
> before any implementation — turn Sentinels from a single-scan tool into
> something that feels like an autonomous AI security team (dashboard,
> per-agent pages, AI fix suggestions, a chatbot, an evidence system, export
> formats, a deployment checklist) — broken into small, independently
> verifiable milestones, the same discipline `docs/PLAN.md` used for the
> motion pass and shipping. This file is that plan.

---

## Part 0 — Three things to decide before Milestone 1

These are real conflicts between the feature list and what the project
currently is (and is allowed to be, per `CLAUDE.md`). Surfacing them now,
not at milestone 12.

### 0.1 — Several checklist items cannot be tested passively

`CLAUDE.md`'s non-negotiable scope rule: *"Never send attack traffic — no
SQLi, no brute force, no fuzzing, no DoS, no automated form submission."*
The requested deployment checklist asks for **Input Validation**, **Rate
Limiting**, **Authentication**, **Authorization**, and **API Security**.
Four of those cannot be verified without violating that rule.

**Proposed resolution — three tiers of checklist item:**

| Tier | Meaning | Examples |
|---|---|---|
| **Auto-verified** | An agent observed this directly | HTTPS, TLS cert validity, security headers, cookie flags, sensitive file exposure |
| **Passively inferred** | Weak signal only, explicitly labelled "not conclusive" | API security (is a Swagger/OpenAPI doc publicly exposed?), auth (is a login form served over plain HTTP?) |
| **Self-attested** | Sentinels asks, the user answers, we never test | Input validation, rate limiting, authorization model |

This keeps the feature, keeps it honest, and keeps the passive-only promise
intact. **The alternative** — dropping passive-only and building an active
scanner — is a fundamentally different product with legal/authorization
implications, and is not planned unless explicitly requested.

### 0.2 — "Payloads" in the evidence system

The evidence spec lists "Payloads." Passive scanning has no attack payloads
to store. Interpreted as **request details** (method, path, headers sent)
unless corrected.

### 0.3 — "Exploitation method" in AI fix suggestions

Standard and fine — OWASP itself writes this way. Framed as *conceptual
explanation* ("an attacker could inject a script tag the browser would
execute because no CSP restricts script sources"), never a copy-pasteable
working exploit.

---

## Part 1 — High-Level Architecture

### 1.1 — The single biggest change: Sentinels currently has no database

Today the entire system is **stateless**. `POST /scan` computes a report and
returns it; the frontend holds it only in React state; `POST /scan/pdf`
takes the whole report *back* as a request body because the server doesn't
remember it. Refresh the page and the scan is gone.

Four of the seven requested features require memory:
- **Dashboard** → "Recent Scan Information" needs scan history
- **Agent pages** → need a stable scan ID to navigate to
- **AI fix suggestions** → caching means nothing without storage
- **Chatbot** → conversation memory, and "understands the completed scan"
  needs the scan retrievable server-side

So **persistence is Milestone 1**, and everything else stacks on it.

### 1.2 — Target architecture

```
┌─────────────────────────── FRONTEND (Next.js App Router) ───────────────────────────┐
│  /                        scan launcher (existing input screen)                     │
│  /scan/[scanId]           dashboard        ← new main overview                      │
│  /scan/[scanId]/agents/[agent]   per-agent page                                     │
│  /scan/[scanId]/findings  full findings list                                        │
│  /scan/[scanId]/checklist deployment readiness                                      │
│  /scan/[scanId]/chat      security chatbot                                          │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       │ fetch / EventSource
┌──────────────────────────────────────▼──────────────────────────────────────────────┐
│                              BACKEND (FastAPI)                                      │
│                                                                                     │
│  main.py  ── routes only, no logic                                                  │
│      │                                                                              │
│      ├── orchestrator.py ──► agents/*  (5 today, N later, via registry)             │
│      │         │                                                                    │
│      │         ├──► scoring.py         (pure, deterministic — unchanged rule)       │
│      │         ├──► checklist/         (pure, deterministic — NEW)                  │
│      │         └──► ai/analyst.py      (enrichment only, degrades gracefully)       │
│      │                                                                              │
│      ├── storage/          NEW — SQLite persistence layer                           │
│      ├── ai/               client.py, analyst.py, fixes.py, chat.py                 │
│      └── report/           exporter registry: pdf / json / markdown / …             │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                  data/sentinels.db  (SQLite)
```

### 1.3 — Architectural rules to preserve (load-bearing, already exist)

1. **Agents never crash the scan.** `BaseAgent.run()` wraps `scan()` in
   try/except. New agents inherit this; never override `run()`.
2. **Scoring stays deterministic.** No model in the loop. The *new*
   Production Readiness Score must follow this too — derived from checklist
   evaluation, not from an LLM.
3. **AI only enriches.** No `GROQ_API_KEY` → summary is `""`, fix
   suggestions unavailable, chatbot disabled — but scanning, scoring,
   checklist, and export all still work completely.
4. **Passive-only.** Every new check must be a read.

---

## Part 2 — Data Models & Schema

### 2.1 — Why SQLite + stdlib `sqlite3`, not an ORM

**Decision: stdlib `sqlite3` with a thin repository layer.** Zero new
dependencies (the project currently has 8, all justified); the query
surface here is genuinely small (~12 queries); readable without learning a
new abstraction.

**Rejected:** Postgres (needs a server running — kills the "clone and run"
property A18 just proved), and JSON files on disk (no querying, no
concurrent-write safety).

### 2.2 — Schema

```sql
CREATE TABLE schema_version (version INTEGER NOT NULL);

CREATE TABLE scans (
    id                TEXT PRIMARY KEY,        -- uuid4
    url               TEXT NOT NULL,
    scanned_at        TEXT NOT NULL,           -- ISO 8601 UTC
    duration_ms       INTEGER NOT NULL,
    score             INTEGER NOT NULL,        -- 0-100 security score
    grade             TEXT NOT NULL,           -- A-F
    summary           TEXT DEFAULT '',         -- AI, may be empty
    readiness_score   INTEGER,                 -- NULL until M10
    deployment_status TEXT,                    -- ready | caution | blocked
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_scans_created ON scans(created_at DESC);

CREATE TABLE agent_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id     TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    agent       TEXT NOT NULL,                 -- slug: "headers"
    duration_ms INTEGER NOT NULL,
    error       TEXT,
    verdict     TEXT                           -- clean | issues_found | failed
);

CREATE TABLE findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id     TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    finding_key TEXT NOT NULL,                 -- existing Finding.id, e.g. "missing-csp"
    agent       TEXT NOT NULL,                 -- NEW: which agent produced it
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    severity    TEXT NOT NULL,
    status      TEXT NOT NULL,
    owasp       TEXT,
    evidence    TEXT DEFAULT '',               -- legacy flat string, kept
    description TEXT DEFAULT '',
    remediation TEXT DEFAULT ''
);
CREATE INDEX idx_findings_scan ON findings(scan_id);

CREATE TABLE evidence_items (                  -- M4
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id   INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,   -- request|response_headers|dns_record|certificate|html_snippet|log|screenshot
    label        TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/plain',
    collected_at TEXT NOT NULL,
    agent        TEXT NOT NULL
);
CREATE INDEX idx_evidence_finding ON evidence_items(finding_id);

CREATE TABLE fix_suggestions (                 -- M13
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id     INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    prompt_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    content_json   TEXT NOT NULL,              -- serialized FixSuggestion
    created_at     TEXT NOT NULL,
    UNIQUE(finding_id, prompt_version)         -- the cache key
);

CREATE TABLE checklist_items (                 -- M9
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id       TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    item_key      TEXT NOT NULL,
    title         TEXT NOT NULL,
    tier          TEXT NOT NULL,   -- auto | inferred | self_attested   (see 0.1)
    state         TEXT NOT NULL,   -- pass | warn | fail | unknown
    explanation   TEXT NOT NULL,
    suggested_fix TEXT DEFAULT '',
    agent         TEXT             -- responsible agent slug, NULL for self_attested
);

CREATE TABLE chat_messages (                   -- M15
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id    TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,      -- user | assistant
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_chat_scan ON chat_messages(scan_id, id);
```

### 2.3 — Pydantic model changes (`backend/models.py`)

```python
# NEW
class EvidenceKind(str, Enum):
    REQUEST = "request"; RESPONSE_HEADERS = "response_headers"
    DNS_RECORD = "dns_record"; CERTIFICATE = "certificate"
    HTML_SNIPPET = "html_snippet"; LOG = "log"; SCREENSHOT = "screenshot"

class EvidenceItem(BaseModel):
    kind: EvidenceKind
    label: str
    content: str
    content_type: str = "text/plain"
    collected_at: str
    agent: str

# CHANGED — additive only, nothing removed
class Finding(BaseModel):
    ...                                    # all existing fields unchanged
    agent: str = ""                        # NEW
    evidence_items: list[EvidenceItem] = Field(default_factory=list)   # NEW

# CHANGED
class AgentResult(BaseModel):
    ...                                    # existing
    verdict: str = ""                      # NEW: clean | issues_found | failed

# CHANGED
class ScanReport(BaseModel):
    ...                                    # existing
    id: str = ""                           # NEW
    readiness_score: Optional[int] = None  # NEW
    deployment_status: Optional[str] = None
    checklist: list[ChecklistItem] = Field(default_factory=list)

# NEW
class AgentInfo(BaseModel):
    name: str; display_name: str; purpose: str
    checks: list[str]; category: str

class ChecklistItem(BaseModel):
    item_key: str; title: str; tier: str; state: str
    explanation: str; suggested_fix: str = ""; agent: Optional[str] = None

class FixSuggestion(BaseModel):
    why_it_exists: str; security_impact: str; exploitation: str
    recommended_fix: str; best_practices: list[str]
    framework_examples: dict[str, str] = Field(default_factory=dict)
    generated_at: str; model: str
```

**Every change is additive with a default** — existing code (`pdf.py`,
`findings.ts`, `Report.tsx`) keeps working untouched throughout the rollout.

---

## Part 3 — API Surface

| Method | Endpoint | Milestone | Purpose |
|---|---|---|---|
| `POST` | `/scan` | existing | Run scan (now also persists, returns `id`) |
| `GET` | `/scan/stream` | existing | SSE live progress |
| `GET` | `/scans` | M2 | Recent scans list (dashboard) |
| `GET` | `/scans/{id}` | M2 | Full stored report |
| `DELETE` | `/scans/{id}` | M2 | Delete a scan |
| `GET` | `/agents` | M3 | Agent registry metadata |
| `GET` | `/scans/{id}/agents/{agent}` | M8 | One agent's slice of a scan |
| `GET` | `/scans/{id}/checklist` | M9 | Deployment checklist |
| `POST` | `/scans/{id}/checklist/{key}` | M11 | Answer a self-attested item |
| `POST` | `/findings/{id}/fix` | M13 | Get/generate AI fix (cached) |
| `POST` | `/findings/{id}/fix?regenerate=true` | M13 | Force regeneration |
| `POST` | `/scans/{id}/chat` | M15 | Ask chatbot a question |
| `GET` | `/scans/{id}/chat` | M15 | Conversation history |
| `GET` | `/scans/{id}/export/{format}` | M17 | Export (pdf/json/markdown) |
| `GET` | `/export/formats` | M17 | Available formats |

`POST /scan/pdf` is kept as a deprecated alias through M17, then removed.

---

## Part 4 — Folder Structure Changes

```
backend/
  main.py                    ~ thinner: routes only
  models.py                  ~ additive model changes
  orchestrator.py            ~ persist + checklist hook
  scoring.py                 = unchanged (stays pure)
  db.py                      + connection, schema init, migrations
  storage/                   + NEW
    __init__.py
    scans.py                 +   save_scan, get_scan, list_scans, delete_scan
    findings.py              +   findings + evidence read/write
    fixes.py                 +   fix suggestion cache
    chat.py                  +   conversation history
  agents/
    base.py                  ~ + metadata fields, + evidence helper
    registry.py               + NEW: AGENTS list + metadata lookup
    headers.py … dns_email.py ~ each gains structured evidence
  checklist/                 + NEW
    __init__.py
    rules.py                 +   the item definitions
    evaluator.py             +   pure: findings -> checklist -> readiness score
  ai/
    client.py                + NEW: generic Groq call (extracted)
    prompts.py                + NEW: all prompt templates
    analyst.py                ~ refactored onto client.py
    fixes.py                  + NEW
    chat.py                   + NEW
  report/
    base.py                   + NEW: Exporter protocol
    registry.py                + NEW
    html_doc.py                ~ extracted from pdf.py
    pdf.py                     ~ becomes a registered exporter
    json_export.py             + NEW
    markdown.py                + NEW
  data/sentinels.db           + gitignored

frontend/
  app/
    page.tsx                  ~ launcher only; redirects to /scan/[id]
    scan/[scanId]/
      layout.tsx              + shell: loads scan once, renders nav
      page.tsx                + dashboard
      findings/page.tsx       +
      agents/[agentName]/page.tsx +
      checklist/page.tsx      +
      chat/page.tsx           +
  components/
    Report.tsx                 ~ decomposed into dashboard pieces
    ScoreRing.tsx               = unchanged
    FindingRow.tsx              ~ + evidence panel, + fix button
    AgentLog.tsx                = unchanged
    ScanProgress.tsx            ~ driven by /agents instead of hardcoded array
    dashboard/                  + StatCard, DeploymentBadge, RecentScans, QuickActions
    evidence/                   + EvidenceList, EvidenceItem
    agent/                      + AgentHeader, AgentVerdict, AgentChecks
    checklist/                  + ChecklistTable, ChecklistRow
    chat/                       + ChatPanel, MessageList, MessageInput
    fixes/                      + FixSuggestionPanel
  lib/
    api.ts                     ~ new endpoints + types
    findings.ts                 = unchanged
    agents.ts                   + agent metadata fetching
    useScrollDrift.ts            = unchanged
```

---

## Part 5 — Key Subsystem Designs

### 5.1 — Agent registry (makes "adding agents" nearly free)

`BaseAgent` gains declarative metadata:

```python
class BaseAgent(ABC):
    name: str = "base"
    display_name: str = "Base"
    purpose: str = ""              # one sentence for the agent page
    checks: list[str] = []         # "what it checks" bullets
    category: str = ""             # Finding.category this agent owns
```

`agents/registry.py` holds the single `AGENTS` list and exposes
`agent_info()`. `GET /agents` serves it, and `ScanProgress.tsx` + agent
pages both derive from that — deleting the hardcoded `AGENT_NAMES` array in
`ScanProgress.tsx:7`.

**Result: adding a 6th agent = write the class + add one line to
`registry.py`.** No frontend change, no route change.

### 5.2 — Evidence collection

`BaseAgent` gets a helper so agents don't hand-build evidence:

```python
def evidence(self, kind, label, content, content_type="text/plain") -> EvidenceItem:
    return EvidenceItem(kind=kind, label=label, content=content,
                        content_type=content_type,
                        collected_at=datetime.now(timezone.utc).isoformat(),
                        agent=self.name)
```

**Critical constraint carried forward:** `exposure.py`'s `_check_env_file`
deliberately does *not* echo a found `.env`'s contents. That rule must
survive into structured evidence — evidence for that finding stores the
request and status code, never the body. Same for anything else that could
duplicate a leak.

The legacy `Finding.evidence` string stays populated so `pdf.py` and the
current UI keep working through the whole migration.

### 5.3 — Deployment checklist & readiness score (deterministic)

`checklist/rules.py` defines items declaratively:

```python
ChecklistRule(
    key="https_enforced",
    title="HTTPS enforced",
    tier="auto",
    agent="tls",
    # pure function: (findings) -> (state, explanation)
    evaluate=lambda f: _from_finding(f, "no-https", fail_state="fail"),
)
```

`checklist/evaluator.py` is **pure** — findings in, checklist + readiness
score out. No network, no clock, no LLM. Same discipline as `scoring.py`.

**Readiness score is separate from the security score**: security score =
severity-weighted deduction; readiness score = % of *auto-verified*
checklist items passing, with any `fail` on a blocking item forcing
`deployment_status = "blocked"` regardless of percentage.

### 5.4 — Chatbot: no RAG, and why

A finished scan is ~12-25 findings ≈ 3-6k tokens. **Stuff the whole scan
into context.** No embeddings, no vector store, no chunking.

**Rejected: vector search / RAG.** It's the reflexive answer and it's wrong
at this size — it would add a vector DB dependency, an embedding call, and
non-determinism in retrieval, all to search a document that fits in context
whole. Revisit only if scans grow 10x.

Context assembly per question:
```
system prompt (role, passive-scanner honesty rules, "say when unsure")
+ scan digest (url, score, grade, deployment status, findings w/ severity+evidence)
+ checklist state
+ last N turns of conversation (N≈10, from chat_messages)
+ user question
```

Conversation memory is DB-backed (`chat_messages`), so it survives refresh.

### 5.5 — AI fix suggestions: caching design

Cache key is `(finding_id, prompt_version)`. `prompt_version` is a constant
in `ai/prompts.py` bumped by hand whenever a prompt changes — so improving a
prompt automatically invalidates stale cached fixes without a migration.
`?regenerate=true` bypasses and overwrites.

Findings are deterministic per site, so the same finding never regenerates
unless asked.

### 5.6 — Export pipeline

```python
class Exporter(Protocol):
    format_id: str; media_type: str; extension: str
    def render(self, report: ScanReport) -> bytes: ...
```

`report/registry.py` maps `format_id → Exporter`. `GET
/scans/{id}/export/{format}` looks it up, 404s on unknown. **Adding a format
= one new file + one registry line.** `html_doc.py` (extracted from today's
`pdf.py`) is shared by both the PDF and Markdown exporters.

---

## Part 6 — Incremental Roadmap

19 milestones, each one sitting, each independently verifiable. **Do not
start N+1 until N passes its verification.**

---

### PHASE A — Persistence foundation *(no visible UI change)*

#### `[x]` M1 — SQLite storage layer
**Goal:** Every completed scan is saved to disk.
**Why now:** Four features depend on it; nothing else can start.
**Files:** `+backend/db.py`, `+backend/storage/{__init__,scans,findings}.py`,
`~backend/orchestrator.py`, `~backend/models.py` (add `ScanReport.id`),
`~.gitignore`
**Backend:** Schema creation on startup; `save_scan()`; `_finalize()`
generates a uuid and persists before returning.
**Frontend:** none. **DB:** initial schema.
**Expected output:** `POST /scan` response gains an `id`;
`backend/data/sentinels.db` exists.
**Verify:** Run a scan → `sqlite3 backend/data/sentinels.db "SELECT
id,url,score FROM scans;"` shows the row. Run a second scan → two rows.
Existing frontend still works untouched.

#### `[x]` M2 — Read endpoints
**Goal:** Fetch stored scans back out.
**Files:** `~backend/main.py`, `~backend/storage/scans.py`
**Backend:** `GET /scans` (paginated, newest first), `GET /scans/{id}`,
`DELETE /scans/{id}`.
**Expected output:** Reconstructed `ScanReport` from DB.
**Verify:** `curl localhost:8000/scans` lists M1's scans; `curl
localhost:8000/scans/{id}` returns a report **byte-identical in content** to
what `POST /scan` returned. That equality is the real test — it proves
nothing is lost in the round-trip.

#### `[x]` M3 — Agent registry + metadata
**Goal:** Agents describe themselves; frontend stops hardcoding them.
**Files:** `~backend/agents/base.py`, `+backend/agents/registry.py`, all 5
agent files (metadata only), `~backend/orchestrator.py`, `~backend/main.py`
**Backend:** Metadata fields on each agent; `GET /agents`.
**Verify:** `curl localhost:8000/agents` returns 5 entries with purpose +
checks. Full scan still returns identical findings (metadata is inert).

---

### PHASE B — Structured evidence

#### `[x]` M4 — Evidence model + Headers agent only
**Goal:** Prove the evidence shape on one agent before touching five.
**Why now:** Isolates model risk to a single agent.
**Files:** `~backend/models.py`, `~backend/agents/base.py`,
`~backend/agents/headers.py`, `~backend/storage/findings.py`, DB migration
**Verify:** Scan a site → header findings have populated `evidence_items`;
other agents' findings have `[]` and still render fine. Legacy `evidence`
string still present. PDF export unchanged.

#### `[x]` M5 — Evidence for the other four agents
**Goal:** Complete evidence coverage.
**Files:** `~backend/agents/{recon,tls,exposure,dns_email}.py`
**Critical:** `exposure.py` must **not** put leaked `.env` content into
evidence (preserve the no-echo rule).
**Verify:** Scan `wordpress.org` → every finding has ≥1 evidence item. Then
run the local `.env` fixture from A9 and confirm evidence contains the
request + status but **no secret values**.

---

### PHASE C — Frontend restructure

#### `[x]` M6 — Scan routes + shareable URLs
**Goal:** A scan lives at its own URL.
**Files:** `+app/scan/[scanId]/{layout,page}.tsx`, `~app/page.tsx`,
`~lib/api.ts`
**Frontend:** After SSE `done`, `router.push('/scan/{id}')`. The
scan-detail layout fetches from `GET /scans/{id}`.
**Verify:** Run a scan → URL becomes `/scan/<uuid>` → **hard-refresh the
page and the report is still there.** That's the whole point of M1-M2
paying off.

#### `[x]` M7 — Dashboard
**Goal:** The main post-scan overview.
**Files:** `~app/scan/[scanId]/page.tsx`, `+components/dashboard/*`
**Frontend:** Security score, scan summary, severity counts, recent scans,
quick actions. *(Readiness score + deployment status render as "not yet
evaluated" — M10 fills them.)*
**Verify:** Dashboard matches the raw JSON from `GET /scans/{id}`;
recent-scans list navigates correctly.

#### `[x]` M8 — Agent pages
**Goal:** One page per agent, generated from the registry.
**Files:** `+app/scan/[scanId]/agents/[agentName]/page.tsx`,
`+components/agent/*`, `~components/ScanProgress.tsx`, `+lib/agents.ts`,
`~backend/main.py`
**Verify:** All 5 agent pages render purpose/checks/findings/evidence/
logs/verdict. Then the real test: **temporarily add a dummy 6th agent to
`registry.py` and confirm its page appears with zero frontend edits.**
Remove it after.

---

### PHASE D — Deployment checklist

#### `[x]` M9 — Checklist evaluator (backend, pure)
**Files:** `+backend/checklist/{__init__,rules,evaluator}.py`,
`~orchestrator.py`, `~models.py`, `~storage/`, DB migration
**Backend:** Rules for the three tiers (§0.1); pure `evaluate(findings) ->
list[ChecklistItem]`.
**Verify:** `curl .../checklist` returns items with correct tiers. **Scan
the same site twice → identical checklist output** (determinism, same bar
as `scoring.py`).

#### `[x]` M10 — Readiness score + deployment status
**Files:** `~backend/checklist/evaluator.py`, `~models.py`,
`~storage/scans.py`
**Verify:** A site with a critical exposure → `blocked`. A clean site →
`ready`. Same site twice → identical score.

#### `[x]` M11 — Checklist UI + self-attestation
**Files:** `+app/scan/[scanId]/checklist/page.tsx`,
`+components/checklist/*`, `~backend/main.py`
**Verify:** Three tiers visually distinct; answering a self-attested item
persists across refresh; dashboard badge (M7) now populated.

---

### PHASE E — AI features

#### `[x]` M12 — Extract the LLM client
**Goal:** One place that talks to Groq, before three features need it.
**Files:** `+backend/ai/{client,prompts}.py`, `~backend/ai/analyst.py`
**Verify:** Summaries still generate identically with a key; **still
return `""` with the key removed** — the A12 graceful-degradation guarantee
must survive the refactor. Test both.

#### `[x]` M13 — Fix suggestions API + cache
**Files:** `+backend/ai/fixes.py`, `+backend/storage/fixes.py`, `~main.py`,
`~models.py`, DB migration
**Verify:** First `POST /findings/{id}/fix` is slow (real LLM call); second
is instant (cache hit — confirm via DB row count staying at 1).
`?regenerate=true` creates a new one. **With no API key: returns a clean
"unavailable" response, never a 500.**

#### `[x]` M14 — Fix suggestions UI
**Files:** `~components/FindingRow.tsx`,
`+components/fixes/FixSuggestionPanel.tsx`, `~lib/api.ts`
**Verify:** Expanding a finding fetches a fix, shows loading state, renders
all six sections; second expand is instant.

#### `[x]` M15 — Chatbot backend
**Files:** `+backend/ai/chat.py`, `+backend/storage/chat.py`, `~main.py`,
DB migration
**Verify:** `curl -X POST .../chat -d '{"question":"what should I fix
first?"}'` gives an answer citing real findings from that scan. Ask a
follow-up ("why that one?") → it uses history. History survives restart.

#### `[x]` M16 — Chatbot UI
**Files:** `+app/scan/[scanId]/chat/page.tsx`, `+components/chat/*`
**Verify:** Ask all six of the example questions from the feature spec;
history persists on refresh; with no API key the chat tab shows a clear
"requires GROQ_API_KEY" state rather than breaking.

---

### PHASE F — Export system

#### `[x]` M17 — Exporter registry (PDF refactor, zero behaviour change)
**Goal:** Make export pluggable without changing output.
**Files:** `+report/{base,registry,html_doc}.py`, `~report/pdf.py`,
`~main.py`
**Verify:** Generate a PDF **before** this milestone, save it. Generate
after. **They must be visually identical** — this milestone changes
structure only.

#### `[x]` M18 — JSON + Markdown exporters
**Files:** `+report/json_export.py`, `+report/markdown.py`,
`~report/registry.py`
**Verify:** All three formats download with correct MIME types; JSON
round-trips into a valid `ScanReport`; `GET /export/formats` lists three.

#### `[x]` M19 — Enrich exports with new sections
**Files:** `~report/html_doc.py`, `~report/markdown.py`,
`~report/json_export.py`
**Backend:** Add executive summary, checklist, readiness score, evidence,
cached AI fixes.
**Verify:** All three formats contain every section; **a report with no AI
fixes still exports cleanly** (graceful degradation in the export layer
too).

---

## Part 7 — Risk Notes

| Risk | Where | Mitigation |
|---|---|---|
| Evidence leaks secrets | M4/M5 | `exposure.py`'s no-echo rule is an explicit acceptance criterion in M5 |
| Model changes break PDF | M4 | All model changes additive-with-defaults; M17 has a byte-comparison check |
| Losing graceful degradation | M12-M16 | Every AI milestone verifies the no-key path explicitly |
| Scoring becomes non-deterministic | M9/M10 | Checklist evaluator is pure, imports nothing non-deterministic — same rule as `scoring.py` |
| DB migrations without a framework | M4, M9, M13, M15 | `schema_version` table + ordered migration functions in `db.py` (added in M1) |
| Frontend restructure breaks the report | M6 | M6 moves routing only; component internals untouched until M7 |

---

## Open decisions (Part 0) — resolved by implementation

All three shipped exactly as proposed; nothing was overridden along the way.

- **§0.1** — the three-tier checklist model (auto-verified / passively
  inferred / self-attested) shipped in M9-M11 exactly as proposed. Live in
  `backend/checklist/rules.py` and the `/scan/{id}/checklist` page.
- **§0.2** — "Payloads" in the evidence spec landed as request details
  (method, path, headers), never attack payloads. Live in `EvidenceItem`
  (M4/M5).
- **§0.3** — "Exploitation method" in AI fix suggestions (M13) is conceptual
  explanation only, enforced by `ai/prompts.py`'s `FIX_SYSTEM` prompt — never
  a working exploit.

## Part 8 — Closeout

All 19 milestones across Phases A-F are shipped as of 2026-08-03. Every
milestone's own `Verify` step was run for real against a live scan, not just
read through — see `docs/learning/19` through `29` for the day-by-day record,
each with what was built, the concept behind it, and how it was checked.

Nothing from this plan is left outstanding. Any further work on Sentinels —
new agents, new checklist items, a different export format — starts fresh,
either as a new plan file or as ad-hoc additions on top of this shipped
baseline.
