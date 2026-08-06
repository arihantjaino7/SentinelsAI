# Sentinels v3 — GitHub Repository Scanning

> **Status:** Phase R-A (R1-R3) done, 2026-08-04. Phase R-B (R4-R8, "The
> agents") done, 2026-08-04, all five in one continuous pass per Arihant's
> request. Written 2026-08-04, after all 19 v2 milestones shipped
> (`docs/PLAN-v2.md`). Same discipline as v2: small, independently verifiable
> milestones, do not start N+1 until N passes its verification. One learning
> note per milestone (`docs/learning/`), per `CLAUDE.md`.
>
> R9 done, 2026-08-04 — this is also where the first repo orchestrator
> (`backend/repo_orchestrator.py`, `POST /repo/scan`) landed, pulled forward
> from the unassigned slot the note above described, since R9's own
> verification bar needed a real end-to-end repo scan to run twice. Note:
> [`learning/42-repo-checklist-and-readiness.md`](learning/42-repo-checklist-and-readiness.md).
>
> R10 done, 2026-08-04. Phase R-C complete. Note:
> [`learning/43-repo-ai-what-you-got-wrong.md`](learning/43-repo-ai-what-you-got-wrong.md).
>
> R11 done, 2026-08-05. Note:
> [`learning/45-repo-launcher-and-live-progress.md`](learning/45-repo-launcher-and-live-progress.md).
>
> R12 done, 2026-08-05 — **all twelve v3 milestones are now complete.** Note:
> [`learning/46-file-tree-browser.md`](learning/46-file-tree-browser.md).
>
> **Resume here:** nothing left in this plan. What remains is the
> end-to-end verification pass below ("Verification (end to end, after
> R12)") — not a new milestone, just confirming the whole feature together.

## Context

Sentinels today scans one thing: a live URL. This adds a second target type —
a public GitHub repository — for the "vibe coder" who shipped something with
an AI assistant and has no idea what they got wrong. The repo scan must answer
four questions in plain English: **what's broken, what can be fixed, how to fix
it, and what mistake caused it.**

Deliberately *not* in scope: Sentinels never writes to anyone's repository. It
suggests fixes; the developer applies them. No commits, no PRs, no write scopes.

The site also gets a real front door: `/` becomes a landing page with two
choices (URL or repo) and nothing else.

**Decisions already made:** public repos only (no user-supplied tokens);
tarball snapshot now with git-history secret scanning as a later milestone;
report layout mirrors the URL side *plus* a new file-tree browser.

---

## Two new non-negotiables (add to `CLAUDE.md`)

1. **Never execute anything from a scanned repository.** No `npm install`, no
   `pip install`, no build steps, no importing repo code. Read bytes only. This
   is the repo-side equivalent of the existing passive-only rule — a `package.json`
   `postinstall` script is arbitrary code execution on your machine.
2. **Never echo a discovered secret.** `backend/agents/exposure.py:74` already
   sets this precedent — it reports that a `.env` was exposed and deliberately
   withholds the contents. Secret findings report file, line, and a masked
   match; never the value.

---

## Architecture: extend, don't fork

The existing pipeline is target-agnostic once findings exist:
`findings → scoring.py → checklist/evaluator.py → ai/ → report/`. All of it is
reused. Only *fetching* and the *agents* are genuinely new.

**Key move:** keep `ScanReport.url` as the field name (a repo URL is a URL), and
add `target_type: "url" | "repo"`. Existing frontend code reading `report.url`
keeps working untouched; the DB migration is one nullable column with a default.

| Reused as-is | New |
|---|---|
| `scoring.py` (score/grade/counts) | `repo/fetch.py` — GitHub tarball fetcher |
| `checklist/evaluator.py` (pure, gains a `rules` param) | `checklist/repo_rules.py` |
| `ai/fixes.py`, `ai/chat.py`, `ai/client.py` | repo-flavoured prompts in `ai/prompts.py` |
| `report/` exporters, `storage/` layer | 5 repo agents |
| `/scan/[scanId]`, `/agents/[agentName]`, `/checklist`, `/chat` pages | landing page, repo launcher, file-tree page |

---

## Milestones

Same discipline as `docs/PLAN-v2.md`: **do not start N+1 until N passes its
verification.** One learning note per milestone (`docs/learning/`), per CLAUDE.md.

### PHASE R-A — Foundation *(no visible UI change)*

#### R1 — GitHub URL parsing + repo fetcher
> **Status:** done. Verified against `octocat/Hello-World` (real fetch,
> populated then cleaned up), a nonexistent repo (`ValueError`, no crash), and
> `torvalds/linux` (rejected in ~1s on the metadata size check alone, no
> tarball ever downloaded). Note: [`learning/34-repo-fetcher-and-async-context-managers.md`](learning/34-repo-fetcher-and-async-context-managers.md).

**Files:** `+backend/repo/{__init__,fetch}.py`
**Backend:** `parse_github_url()` → (owner, repo, ref) with a `ValueError` for
anything that isn't a GitHub repo URL — mirrors `orchestrator.normalize_url`'s
contract exactly, so `main.py` turns it into a 400 with zero new error handling.
`fetch_repo()` calls `GET /repos/{owner}/{repo}` for metadata (size, default
branch, existence), then downloads `/tarball/{ref}` and extracts to a temp dir.

Guards, all mandatory: reject repos over a size cap (~50 MB), cap total extracted
bytes / file count / individual file size, extract with `tarfile`'s
`filter="data"` (Python 3.13 here — this is what blocks path-traversal
`../../` tar entries), skip `node_modules`/`.venv`/`dist`/`build`/binaries, and
`shutil.rmtree` in a `finally`.
**Verify:** Fetch a small public repo → temp dir populated, then cleaned up.
A nonexistent repo → `ValueError`, not a crash. A deliberately oversized repo →
rejected before download completes.

#### R2 — RepoContext + agent base + registry
> **Status:** done. `GET /repo/agents` returns `HygieneAgent` (a real
> README/LICENSE check, not a no-op — seeds R8's fuller hygiene agent). A
> deliberately-raising test agent proved `BaseRepoAgent.run()`'s
> crash-proofing matches `BaseAgent.run()`'s. Note: [`learning/35-repo-agent-wiring.md`](learning/35-repo-agent-wiring.md).

**Files:** `+backend/agents/repo/{__init__,base}.py`, `+backend/agents/repo_registry.py`
**Backend:** `RepoContext(repo_url, owner, repo, ref, root: Path, files: list[RepoFile], client)`
— the tree is walked **once** and shared by all agents, the same instinct as
`ScanContext` sharing one `httpx.AsyncClient` (`agents/base.py:24`).
`BaseRepoAgent` reuses `BaseAgent`'s crash-proofing contract verbatim (each agent
catches its own exceptions → `AgentResult.error`). One trivial agent to prove wiring.
**Verify:** `GET /repo/agents` returns the registry. A deliberately-thrown
exception inside an agent surfaces as `error`, doesn't kill the scan.

#### R3 — Model + DB generalization
> **Status:** done. Verified with a real round-trip: the same stored
> `wordpress.org` scan (12 findings) fetched via `GET /scans/{id}` on the old
> code and the new code (old code temporarily set aside with `git stash` for
> the comparison) differ in exactly two ways — `target_type: "url"` on the
> report, `file_path`/`line: null` on every finding — nothing else changed.
> Note: [`learning/36-generalizing-the-database-for-repo-scans.md`](learning/36-generalizing-the-database-for-repo-scans.md).

**Files:** `~backend/models.py`, `~backend/db.py` (migrations V6, V7),
`~backend/storage/{scans,findings}.py`, `~frontend/lib/api.ts`
**Backend:** `ScanReport.target_type`; `Finding.file_path` + `Finding.line`
(both `Optional`, null for URL scans — additive, exactly how `evidence_items`
was added in M4); new `EvidenceKind.FILE_SNIPPET` and `DEPENDENCY`; new
`repo_files` table (path, size, language, finding_count) for the R12 tree.
**Verify:** Every existing URL scan still round-trips byte-identically through
`GET /scans/{id}` — this migration must be invisible to the URL side.

### PHASE R-B — The agents

Each: one agent file + registry line + learning note. Findings carry
`file_path`/`line` so R12's tree can map them.

#### R4 — Secrets agent *(the headline feature)*
> **Status:** done. Verified against a fixture directory covering all five
> verify points below (fake AWS key in `.env`, AWS's own placeholder key in
> `.env.example`, `SECRET_KEY` vs same-value `SESSION_ID`, a lockfile-shaped
> integrity hash, and a real `octocat/Hello-World` fetch). Note:
> [`learning/37-secrets-agent.md`](learning/37-secrets-agent.md).

**New file:** `backend/agents/repo/secrets.py` — `SecretsAgent(BaseRepoAgent)`,
`name = "repo-secrets"`, `category = "Secrets"`.
**Touched:** `backend/agents/repo_registry.py` — `AGENTS_REPO = [HygieneAgent, SecretsAgent]`.

Three kinds of detection, three confidence levels:

1. **Provider-specific patterns → `Severity.CRITICAL`.** Published, well-known
   token *shapes* (not secrets), same public signatures gitleaks/trufflehog use:
   - AWS Access Key ID — `(?:AKIA|ASIA)[0-9A-Z]{16}`
   - GitHub token — `gh[pousr]_[A-Za-z0-9]{36}` and `github_pat_[A-Za-z0-9_]{22,}`
   - Groq — `gsk_[A-Za-z0-9]{20,}`
   - OpenAI — `sk-[A-Za-z0-9]{20,}` (covers `sk-proj-...` too)
   - Stripe — `(?:sk|rk)_live_[A-Za-z0-9]{24,}` (deliberately not `_test_` keys)
   - Google API key — `AIza[0-9A-Za-z\-_]{35}`
   - Slack token — `xox[baprs]-[A-Za-z0-9-]{10,}`
   - Private key block — `-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----`
2. **A committed `.env`-shaped file → `Severity.CRITICAL`**, independent of
   whether a pattern above matches inside it. Filename `.env` or `.env.<word>`
   — **excluding** `.env.example`/`.env.sample`/`.env.template`/`.env.dist`,
   which are skipped from scanning *entirely* (see false positives below).
   Repo-side sibling of `exposure.py`'s live `/.env` check.
3. **Generic high-entropy assignment → `Severity.HIGH`** (one notch below the
   confident cases). A line shaped like `SOME_KEY = "value"` where **both**
   (a) the identifier contains a secret-suggestive word
   (`key|secret|token|password|pwd|credential|auth`, case-insensitive) **and**
   (b) the quoted value is length ≥ 20 with Shannon entropy ≥ ~4.3 bits/char.
   Requiring both is deliberate — entropy alone flags commit hashes/UUIDs
   constantly; the name requirement is what keeps this from being the noisy
   fallback the Risks table below already warns about (same risk as R7).
   Shannon entropy: a 6-line pure function, `collections.Counter` +
   `-sum(p * log2(p) for p in probs)`, no new dependency.

**False positives (the other half of R4's verify bar):**
- `.env.example`/`.env.sample`/`.env.template`/`.env.dist` excluded from
  scanning entirely, not just the "committed .env" rule — AWS's own docs use
  a real placeholder (`AKIAIOSFODNN7EXAMPLE`) that genuinely matches the AWS
  pattern, so an example file using it would otherwise false-positive.
- Known lockfiles (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`,
  `poetry.lock`, `Pipfile.lock`, `composer.lock`) excluded from the *generic
  entropy* check only (npm's `"integrity": "sha512-..."` is exactly that
  shape) — provider-pattern matches inside them still fire.

**Masking (non-negotiable):**
```python
def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"
```
Every `Finding.evidence`/`description` and the `EvidenceItem(kind=EvidenceKind.FILE_SNIPPET, ...)`
use only the masked form. Verified by asserting the real secret string is
absent from `AgentResult.model_dump_json()`, not by eyeballing finding text.

**Fills in R3's new fields for the first time:** every finding sets
`file_path` (`RepoFile.path`) and `line` (1-based, `enumerate(text.splitlines(), start=1)`).

**A new problem R2's agents never had — `Finding.id` must be unique per
occurrence.** Every existing agent produces at most one finding per fixed id
slug per scan. `SecretsAgent` can find the same kind of secret in several
files, or several in one file. Reusing one static id per provider would let
two unrelated leaks collide under the same `Finding.id` — and since
`POST /scans/{id}/findings/{finding_key}/fix` looks a finding up by
`finding.id == finding_key` (`main.py:258`), a collision means "Fix with AI"
on the second occurrence would silently generate a fix for the *first* one.
Build each id as `f"secret-{provider_slug}-{file_path_slug}-L{line}"`
(`/` → `-` in the path) — unique within a scan, stable across re-scans of an
unchanged repo.

**Reading files:** `RepoFile.abs_path.read_text(encoding="utf-8", errors="ignore")`,
skip on `UnicodeDecodeError` (R1's `BINARY_EXTENSIONS` already filters the
common case). Cap total findings at 100 as a safety valve.

**No repo orchestrator exists yet** (none is required until later in
R-B/R-D) — verify the same way R2's `HygieneAgent` was: a hand-built
`RepoContext` over a local fixture directory, plus one real `fetch_repo()`
run against a known-clean repo (`octocat/Hello-World`, reused from R1/R2).

**Verify:**
1. Fixture `.env` with a fake AWS key → `CRITICAL` finding, correct
   `file_path`/`line`, and the real key string is absent from
   `result.model_dump_json()`.
2. Fixture `.env.example` with AWS's own published example key
   (`AKIAIOSFODNN7EXAMPLE`) → zero findings reference it.
3. `config.py` with `SECRET_KEY = "<random>"` → one `HIGH` finding; same file
   with `SESSION_ID = "<same random value>"` → no finding (proves name+entropy,
   not entropy alone, is doing the work).
4. Fixture `package-lock.json` with a real-shaped `sha512-` integrity hash →
   no generic-entropy finding.
5. Real `fetch_repo()` against `octocat/Hello-World` → zero findings, no crash.

#### R5 — Dependencies agent
> **Status:** done. Verified live against OSV.dev: a fixture
> `requirements.txt` pinning `django==1.11.0`/`requests==2.6.0` came back
> with real GHSA ids; the same scan with `client=None` degraded to one
> "couldn't verify" finding instead of erroring. Note:
> [`learning/38-dependencies-agent.md`](learning/38-dependencies-agent.md).

Parse `requirements.txt`, `package.json`, `package-lock.json`, `pyproject.toml`;
batch-query **OSV.dev** (`POST /v1/querybatch`) for known CVEs. Reading a public
vulnerability database — passive, in scope. Follows the `ai/client.py` graceful-
degradation contract: OSV unreachable → findings degrade to "couldn't verify",
never a failed scan.
**Verify:** A repo pinned to a known-vulnerable version → finding with the CVE.
Same scan with the network blocked → still completes, marked unverified.

#### R6 — Repo config agent
> **Status:** done. Verified with a fixture repo (`.gitignore` missing
> `.env` coverage, a Dockerfile with `FROM node:latest` + no `USER` + a
> secret-shaped `ENV`, a workflow with `pull_request_target` and one
> unpinned third-party action alongside a correctly-skipped first-party and
> SHA-pinned action) plus a real `octocat/Hello-World` fetch. Note:
> [`learning/39-repo-config-agent.md`](learning/39-repo-config-agent.md).

`.gitignore` completeness (is `.env` ignored? `*.pem`? `node_modules`?),
Dockerfile smells (running as root, `:latest`, secrets in `ENV`), CI workflow
risks (`pull_request_target`, unpinned third-party actions).

#### R7 — Code patterns agent
> **Status:** done. Verified with a "dirty" fixture (one instance of each of
> the 9 patterns, all correctly WARN, never FAIL) and a "clean" fixture
> using deliberate near-misses (`evaluate()`, `shell=False`, a parameterized
> query, `DEBUG = False`, `json.loads`) that produced zero false positives.
> Note: [`learning/40-code-patterns-agent.md`](learning/40-code-patterns-agent.md).

`eval`/`exec`, `shell=True`, SQL built by string concatenation/f-string,
`dangerouslySetInnerHTML`, `verify=False`, `DEBUG=True`, wildcard CORS,
`pickle.loads`. Mostly `WARN`, not `FAIL` — these are indicative, not conclusive,
and the checklist's existing **inferred** tier is exactly the right home for them.
**Verify:** False-positive check on a clean, well-written repo is the real test here.

#### R8 — Repo hygiene agent
> **Status:** done. Verified with a fixture repo where every signal is
> present (all PASS, plus a 2 MB file correctly flagged) and one where none
> are (all WARN, no crash, lockfile checks correctly skipped since no
> manifest exists), plus a real `octocat/Hello-World` fetch confirming R2's
> original check still passes after the class was extended. Note:
> [`learning/41-repo-hygiene-extended.md`](learning/41-repo-hygiene-extended.md).

Lockfile committed? Tests present? CI configured? `.env.example` provided?
LICENSE/README? Large binaries committed?

### PHASE R-C — Scoring, checklist, AI

#### R9 — Repo checklist + readiness score
> **Status:** done. Verified with two real scans of `octocat/Hello-World`:
> byte-identical checklist (17 items), readiness score (33/100), and
> deployment status (`blocked`, correctly — no `.gitignore` in that repo
> trips both blocking `.gitignore` rules) both times. A URL scan afterward
> still returns exactly 16 checklist items, unchanged. Note:
> [`learning/42-repo-checklist-and-readiness.md`](learning/42-repo-checklist-and-readiness.md).

**Files:** `+backend/checklist/repo_rules.py`, `~backend/checklist/evaluator.py`,
`+backend/repo_orchestrator.py`, `~backend/main.py` (`POST /repo/scan`)
`evaluate()` gains a `rules` parameter defaulting to the existing URL `RULES` —
stays pure, existing callers unchanged. Repo blocking items: secrets committed,
`.env` not gitignored, critical CVE present. Plus self-attested rows Sentinels
genuinely cannot check (secrets rotated? branch protection? 2FA?).
**Verify:** Same repo scanned twice → **identical** checklist and readiness score.
Same determinism bar as `scoring.py` and M9.

#### R10 — Repo AI: "what you got wrong"
> **Status:** done. Verified live against `octocat/Hello-World`: the summary
> correctly led with the missing `.gitignore` (the actual worst finding,
> not an invented one) and named it as the reason the repo isn't
> deployment-ready. With `GROQ_API_KEY` forced empty, the same scan still
> returned a full score/checklist/readiness_score, `summary: ""`, HTTP 200 —
> no crash. Note:
> [`learning/43-repo-ai-what-you-got-wrong.md`](learning/43-repo-ai-what-you-got-wrong.md).

**Files:** `~backend/ai/prompts.py`, `~backend/ai/analyst.py`
A repo-specific analyst prompt written for a non-expert who just shipped
AI-generated code — leads with the mistake, in plain English. A repo-flavoured
fix prompt whose `framework_examples` are code/config diffs rather than the
current Apache/Nginx blocks. Bump `PROMPT_VERSION` (invalidates the fix cache
with no migration — that mechanism already exists, `ai/prompts.py:3`).
**Verify:** Summary names the real worst problem. With `GROQ_API_KEY` removed the
scan still completes fully — the A12 guarantee must survive.

### PHASE R-D — Frontend

#### R11 — Landing page, repo launcher, live progress
> **Status:** done, 2026-08-05. The landing page's animated scan-type chooser
> (`components/landing/scan-select/`) supersedes the plan's original literal
> "two large boxes" — built separately, per Arihant's design brief, and
> already routes to both `/url` and `/repo`. `app/repo/page.tsx` is now a real
> launcher (was a static "Coming soon" page): `backend/repo_orchestrator.py`
> gained `run_repo_scan_stream` (mirrors `run_scan_stream`'s
> `asyncio.as_completed` pattern over `AGENTS_REPO`), `main.py` gained
> `GET /repo/stream` (mirrors `/scan/stream`, same in-band `event: failed`
> trick), `lib/api.ts` gained `streamRepoScan()`, and `ScanLauncher`/
> `ScanProgress` both gained a `targetType` prop (default `"url"`, so every
> existing caller is unchanged) instead of a duplicated repo-only component.
> Verified live against `octocat/Hello-World`: all five `repo-*` agents
> streamed in real completion order, landed on `/scan/{id}` with a correct
> B/80 report, a 17-item repo checklist, and a correct agent detail page
> (a `fetchRepoAgents()` fallback was added there too, since it previously
> only checked the URL agent list for display names). Note:
> [`learning/45-repo-launcher-and-live-progress.md`](learning/45-repo-launcher-and-live-progress.md).

**Files:** `~frontend/app/page.tsx` (becomes the landing page), `+app/url/page.tsx`
(today's URL launcher, moved), `+app/repo/page.tsx`, `~components/ScanProgress.tsx`,
`~app/scan/[scanId]/layout.tsx`, `~lib/api.ts`, `~backend/main.py`
`/` = two large boxes, nothing else. Launchers live at top-level `/url` and
`/repo` — deliberately *not* `/scan/url`, which would collide with the
`/scan/[scanId]` dynamic segment. New `GET /repo/stream` SSE endpoint mirrors
`/scan/stream` (`main.py:117`), including its in-band `event: failed` trick for
errors that occur after the 200 is committed. `ScanProgress` takes its agent list
as a prop so it serves both scan types.
**Verify:** Both boxes route correctly; a repo scan streams per-agent progress and
lands on `/scan/{id}`; the overview, agent pages, checklist, and chat all work for
a repo scan with **no changes to those pages**.

#### R12 — File-tree browser
> **Status:** done, 2026-08-05. Verified live against a fresh
> `MahatvaGoell/Sentinels` scan (138 files): every finding's `file_path`
> reconciled exactly against the tree's `finding_count` (e.g.
> `backend/agents/repo/patterns.py` showed 19 in both places), clicking a
> badged file in a real browser rendered its findings via the existing
> `FindingRow`, and a URL scan's nav confirmed to show no Files tab. Note:
> [`learning/46-file-tree-browser.md`](learning/46-file-tree-browser.md).

**Files:** `+frontend/app/scan/[scanId]/files/page.tsx`, `+components/files/*`,
`~backend/main.py` (`GET /scans/{id}/files`)
Collapsible tree from `repo_files`, each node badged with its finding count;
selecting a file lists that file's findings with the same `FindingRow` +
"Fix with AI" component already in use. Tab appears in the scan nav **only** when
`target_type === "repo"`.
**Verify:** Counts on the tree reconcile exactly with the agent pages; a file with
no findings is visibly clean; URL scans never show the Files tab.

---

## Risks

| Risk | Mitigation |
|---|---|
| Malicious repo contents (zip-slip, huge files, symlinks) | `filter="data"` extraction + size/count caps in R1; **never execute repo code** |
| Leaking a found secret into our own report/DB | Masked evidence only (R4), following `exposure.py`'s existing precedent |
| Code-pattern false positives making the tool feel dumb | R7 findings are `WARN`/inferred tier; clean-repo run is R7's actual acceptance test |
| Repo scan too slow for the 60-second promise | Size caps; agents run concurrently via the existing `asyncio.gather`; measure at R8 and cap file counts if needed |
| Breaking the working URL scanner | R3's verification is round-trip equality on existing scans; URL agents/rules/pages are never edited |
| OSV.dev rate limits or downtime | Graceful degradation to "unverified" (R5), same contract as the LLM layer |

---

## Verification (end to end, after R12)

> **Status:** done, 2026-08-05 — all 8 items below actually run, not just
> assumed from "R12 is marked done." Found and fixed one real bug along the
> way: the landing page's GitHub card still said "Coming soon" after R11
> shipped the real launcher (`frontend/components/landing/scan-select/choices.ts`).
> Note: [`learning/45b-verification-pass-and-stale-copy-fix.md`](learning/45b-verification-pass-and-stale-copy-fix.md).

1. Open `/` → exactly two boxes, nothing else.
2. `/repo` → scan a small public repo with a planted dummy secret and a known-
   vulnerable dependency.
3. Confirm: score + grade, readiness + deployment status, plain-English brief
   naming the real worst problem, five agent buttons.
4. Open the secrets agent → finding with correct file/line, **no full secret
   anywhere in the page or DB**; "Fix with AI" returns a code-level fix.
5. Checklist tab → three tiers, deterministic across two scans of the same repo.
6. Files tab → tree renders, counts reconcile with agent pages.
7. Scan a URL → everything on the URL side behaves exactly as before.
8. Remove `GROQ_API_KEY` → both scan types still complete, no AI sections, no 500s.
