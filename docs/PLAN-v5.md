# Sentinels v5 — Autofix: deterministic remediation and GitHub pull requests

> **Status:** written 2026-08-11, on branch `complete-auto-fix` (cut from
> `sliding-effect`, which is 8 commits ahead of `main` — `main` predates all of v4).
>
> Same discipline as [`PLAN-v3.md`](PLAN-v3.md) and [`PLAN-v4.md`](PLAN-v4.md): small,
> independently verifiable stages; **do not start N+1 until N passes its verification**;
> one short learning note per stage (`docs/learning/`), per [`CLAUDE.md`](../CLAUDE.md).
>
> **This document is the specification.** If implementation reality conflicts with it,
> the conflict gets confirmed and *this file* gets updated — the architecture is never
> silently changed to route around a surprise.
>
> Stage 0 done, 2026-08-11. Migration `(10, _V10_SCHEMA)` adds `users`, `sessions`,
> `github_installations`, and `scans.user_id`/`scans.commit_sha`. `backend/auth/`
> (new): `session.py` (signed cookie mint/verify/expiry), `github_oauth.py`
> (GitHub as identity provider — a token is used once to read identity, then
> discarded, never stored), `deps.py` (`current_user`/`optional_user`). Four new
> routes: `GET /auth/github/{login,callback}`, `GET /auth/me`, `POST /auth/logout`.
> Every existing route except `/`, `/health`, `/agents`, `/repo/agents` now requires
> `Depends(current_user)`; `DELETE /scans/{id}` additionally checks ownership (403 on
> someone else's scan). `save_scan`/`run_scan`/`run_repo_scan` gained an additive,
> defaulted `user_id` — every prior caller and test is unaffected. Frontend:
> `app/login/page.tsx`, `lib/useSession.ts`, `credentials: "include"` (fetch) /
> `withCredentials: true` (EventSource) on every backend call, shared 401→`/login`
> redirect centralized in `lib/api.ts`. 137 tests green (36 new, `test_auth.py`);
> manually verified end to end with `TestClient` — no cookie → 401, public routes
> stay open, sign-in → protected routes serve, logout revokes immediately.
> `tsc --noEmit` clean. Note:
> [`learning/58-sign-in-with-github-and-sessions.md`](learning/58-sign-in-with-github-and-sessions.md).
>
> Stage A done, 2026-08-12. New package `backend/remediation/`: `base.py` (`Fixer`
> ABC), `source.py` (`FileSource` — current file content + blob SHA from GitHub's
> Contents API, independent of `repo/fetch.py`'s tarball), `patch.py` (`build_diff`/
> `make_patch`/`validate_plan` — the single safety gate), `tiers.py` (ID-prefix → tier
> table), `budget.py` (`MAX_FILES_PER_PR` etc.), `registry.py` (`fixer_for`),
> `planning.py` (orchestrates one plan/preview/bundle request). Four fixers: `workflows.py`
> (pins `ci-unpinned-action-*` to a commit SHA — pure line-rewrite tested separately from
> the network SHA resolver, per conflict #3), `gitignore.py` (`gitignore-present`,
> creates only), `scaffolding.py` (`repo-readme-present` and `repo-env-example-present`,
> both creates-only — the latter refuses to plan anything when no committed `.env`
> exists to read variable names from, never inventing them), `dockerfile.py`
> (`docker-root-user-*`, tier 2, base-image-aware `USER` insertion before the *last*
> `CMD`/`ENTRYPOINT`, never trusting the finding's placeholder `line=1`). Migration
> `(11, _V11_SCHEMA)` adds `fix_plans` (written by this stage), `fix_applications` and
> `audit_log` (schema-ready, unwritten until Stage B — same precedent `repo_files`/V7 set).
> New models in `backend/models.py`: `FilePatch`, `FixPlan`, `FixApplicationState`,
> `FixApplication`. Three endpoints: `GET /scans/{id}/findings/{key}/fix/plan` (live
> preview, never persisted), `POST /scans/{id}/fix/plan` (plans + saves a batch,
> per-key `fixable` result), `GET /scans/{id}/fix/bundle.zip` (every saved plan's diffs,
> zipped). Frontend: `FixPlanPanel.tsx` renders above the existing `FixSuggestionPanel`
> on repo-scan findings, gated by a new `isRepoScan` prop on `FindingRow` (a URL scan
> has no file to patch). Fixed in passing: `lib/agents.ts`'s `fetchAgentResult` was
> missing `credentials: "include"`, a Stage-0 gap that silently 401ed the agent detail
> page — where this panel lives — for every signed-in user; found and fixed during this
> stage's own live verification. 233 tests green (96 new, `tests/test_remediation_*.py`
> + `test_storage_remediation.py`), all offline/mocked except one manual live run against
> a real public repo (`octocat/Hello-World`) that planned, saved, and bundled a real
> `.gitignore` fix end to end, and one full browser pass (seeded session cookie, real
> scan, click-through of preview → save → download bundle, confirmed via network log).
> `tsc --noEmit` clean. Nothing in this stage writes to GitHub. Notes:
> [`learning/59-deterministic-fixers-and-unified-diffs.md`](learning/59-deterministic-fixers-and-unified-diffs.md),
> [`learning/60-the-diff-preview-ui.md`](learning/60-the-diff-preview-ui.md).

---

## The problem

Sentinels ends at advice. A finding goes to Groq and comes back as six paragraphs of
prose (`FixSuggestion`, `backend/models.py`). Nothing machine-actionable exists anywhere:
no file path, no diff, no target. `framework_examples` is the closest thing, and it is
free text a model invented.

## The shape of the answer

```
Finding → deterministic FixPlan → diff preview → explicit approval
       → branch + commit + PR → user merges → re-verify → PASS + score delta
```

## The governing rule

**The LLM never writes the patch.** Deterministic Python fixers produce the code change;
the LLM keeps writing only the English. This is the existing law of this codebase
("Scoring stays deterministic — no model in the loop. The AI layer only *enriches*")
extended to remediation. See CLAUDE.md's remediation non-negotiable for all ten rules.

---

## Fixability tiers

| Tier | Meaning | UI reads | Examples |
|---|---|---|---|
| 1 | Deterministic, safe to PR | **Fix available** | `ci-unpinned-action-*`, `gitignore-present`, `repo-readme-present`, `repo-env-example-present` |
| 2 | Generated, human must check | **Review required** | `docker-root-user-*`, `dependency-*`, `docker-latest-tag-*`, `secret-env-committed-*`, `ci-pull-request-target-*`, `api-cors-permissive`, `sensitive-response-cacheable`, `server-version-disclosed`, `risky-http-methods` |
| 3 | We can say exactly what to do, we cannot do it | **Manual action required** | `spf-record`, `dmarc-record`, `tls-*`, `dir-listing`, `env-file-exposed`, `git-directory-exposed`, `backup-file-exposed`, `setup-page-exposed` |
| 4 | Never auto-fix | **Suggestion only** | `pattern-*`, `subdomain-takeover-potential`, `subdomain-dangling-dns`, `*-scan-partial`, anything with `confidence` set |

`LICENSE` is deliberately **not** auto-generated. Choosing a software license is a legal
decision, not a security fix.

---

## Conflicts found during inspection

Recorded here because each one changed the design:

1. **No auth exists anywhere.** No user model, no session, no `Depends()` — 21 open
   endpoints behind a CORS allowlist, which `curl` ignores. Adding repo-write capability
   to that is unacceptable, so **Stage 0 exists** and lands before everything else.
2. **`actions/checkout@v4` can never produce a finding** — `agents/repo/config.py` skips
   `owner in ("actions","github")`. The pinning fixer targets **third-party actions only**;
   the test repo must contain one.
3. **Tag → SHA resolution needs the network.** Split into a pure line-rewrite function
   (offline-testable) plus a resolver (mocked in tests). Determinism holds: same tag,
   same SHA, no model involved.
4. **Finding IDs are lossy.** `file_slug = path.replace("/","-")` is non-injective and can
   collide. Fixers route on ID prefix but **read `Finding.file_path`** — never parse the ID.
5. **The repo tarball is deleted** (`repo/fetch.py` `shutil.rmtree`) and no file content is
   stored. Fixers must re-fetch — which is how drift protection comes for free.
6. **`_finalize` only INSERTs**; scans are immutable history. Verification must not mutate
   the original scan.
7. **`gitignore-present` lives in `config.py`**, not `hygiene.py`, and carries no `file_path`.
8. **`scans` stores no commit SHA**, so a re-plan can silently target a different commit
   than the scan saw. Fixed by a column in migration 10.

---

## Stage 0 — Identity and access

Everything downstream needs to know *who* is asking: the audit log's "who", which user an
App installation belongs to, and who may write to a repo. GitHub is the identity provider —
the same App registered for autofix also provides "Sign in with GitHub", so there are no
passwords, no reset flow, no `bcrypt`.

**Migration `(10, _V10_SCHEMA)`** — appended to `db.py`'s `MIGRATIONS`, never editing an
existing entry:

- `users` — github_id, github_login, avatar_url, created_at, last_seen_at
- `sessions` — token_hash, user_id FK CASCADE, created_at, expires_at
- `github_installations` — installation_id, user_id FK, account_login, repo_selection,
  permissions_json, created_at, revoked_at
- `scans.user_id` (nullable — pre-auth scans stay readable as legacy/unowned)
- `scans.commit_sha` (conflict #8)

**Added:** `backend/auth/{session,github_oauth,deps}.py`, `backend/storage/users.py`.

Session is a signed, HTTP-only, SameSite=Lax cookie — stdlib `hmac` + `secrets`, constant-
time compare, explicit expiry. Only the token *hash* is stored, so a leaked DB does not
yield usable sessions. **No new dependency in this stage** (`PyJWT`/`cryptography` arrive
in Stage B, where installation-token signing actually needs them).

**Endpoints:** `GET /auth/github/login`, `GET /auth/github/callback`, `GET /auth/me`,
`POST /auth/logout`. Every existing route except `/`, `/health`, `/agents`, `/repo/agents`
gains `Depends(current_user)`. `GET /scans` returns the caller's scans plus legacy ones.

**Frontend:** `app/login/page.tsx`, `lib/useSession.ts`, `credentials: "include"` on every
fetch in `lib/api.ts`, shared 401 → `/login`. CORS gains `allow_credentials=True`.

**Verification:** session sign/verify/expiry/tamper tests; protected route returns 401
without a cookie and 200 with one; the existing 101 tests stay green.
**Note:** `learning/58-sign-in-with-github-and-sessions.md`.

---

## Stage A — The patch layer (writes nothing, anywhere)

**New package `backend/remediation/`**, mirroring `backend/agents/`:

- `base.py` — `Fixer` ABC: `slug`, `handles(finding) -> bool`, `plan(finding, files) -> FixPlan | None`
- `registry.py` — ordered `FIXERS` list + `fixer_for(finding)`
- `patch.py` — `difflib.unified_diff` generation, `FilePatch` construction, `validate_plan()`
- `tiers.py` — ID-prefix → tier table
- `source.py` — current file content + blob SHA from GitHub (the drift anchor)
- `budget.py` — `MAX_FILES_PER_PR = 10`, `MAX_PRS_PER_SCAN = 3`, `MAX_PRS_PER_HOUR = 10`,
  as readable constants at the top, mirroring `agents/probe.py`'s `Budget` style

**Fixers:** `workflows.py` (`ci-unpinned-action-*`, certain), `gitignore.py`
(`gitignore-present`, certain, creates only), `scaffolding.py` (`repo-readme-present`,
`repo-env-example-present`, certain, `.env.example` keys blanked never valued),
`dockerfile.py` (`docker-root-user-*`, **review-required**, base-image detection,
insertion point found before the last `CMD`/`ENTRYPOINT` rather than trusting the
finding's placeholder `line=1`).

**Models:** `FilePatch`, `FixPlan`, `FixApplication`, `FixApplicationState`
(`planned | pr_open | merged | verified | failed | abandoned`).

**`validate_plan()` is the single safety gate** — one small testable function every plan
passes through, rather than trusting seven fixers to each be careful: tier permits
application; `len(patches) <= MAX_FILES_PER_PR`; no path traversal, no absolute paths, no
writes under `.git/`; `action="delete"` only for an explicit secret-file allowlist; every
touched path traces back to the originating finding.

**Migration `(11, _V11_SCHEMA)`** — `fix_plans`, `fix_applications`, `audit_log`.
**Storage:** `backend/storage/remediation.py`.
**Endpoints:** `GET /scans/{id}/findings/{key}/fix/plan`, `POST /scans/{id}/fix/plan`,
`GET /scans/{id}/fix/bundle.zip`.

**Frontend:** `FixSuggestionPanel` is *extended, not replaced* — the existing "Fix with AI"
button stays. A new `FixPlanPanel` renders above it when a deterministic fixer exists, with
a tier badge, a diff view, and Copy / Download Patch.

**Verification:** every fixer unit-tested offline (happy path, missing file, already-fixed,
malformed input, duplicate instruction); `validate_plan` rejection tests; diff generation
tests. Nothing in this stage touches GitHub.
**Notes:** `59-deterministic-fixers-and-unified-diffs.md`, `60-the-diff-preview-ui.md`.

---

## Stage B — GitHub writes

**Added:** `remediation/github.py` (Git Data API: ref → blob → tree → commit → ref → PR,
no local clone), `remediation/tokens.py` (`TokenProvider` interface; `AppTokenProvider`
mints 1-hour installation tokens from a JWT signed with the App private key;
`DevTokenProvider` reads `SENTINELS_GITHUB_DEV_TOKEN` and **refuses to run unless
`SENTINELS_ALLOW_DEV_TOKEN=1`**), `remediation/pr_body.py`.

**Dry-run first.** `apply(plan, dry_run=True)` returns repo, branch name, files, diff,
commit message, PR title and body, and writes nothing. The live path is not wired to the
frontend until dry run is boring against a throwaway repo.

**`POST /scans/{id}/fix/apply`** — verify installation ownership → re-check every
`original_sha` and **abort on drift** → create `sentinels/fix-{scan_short}-{n}` → one
commit → one PR carrying all selected fixes → write `fix_applications` + `audit_log`.
`GET /scans/{id}/fix/applications` polls PR state.

The installation token is also passed to `repo/fetch.py`, lifting GitHub's ceiling from 60
to 5000 requests/hour — verification re-downloads the tarball each run and would otherwise
hit the unauthenticated wall mid-demo.

**Verification:** GitHub failure injection (401, 403, 404, branch-already-exists,
PR-creation failure, commit failure), drift-abort, branch-prefix enforcement. Then a real
PR against a throwaway repo — **the flow is not reported as working until that PR URL
exists**.
**Notes:** `61-github-apps-and-installation-tokens.md`, `62-committing-without-a-clone.md`.

---

## Stage C — Verification

`POST /scans/{id}/findings/{key}/verify` re-runs **only** the responsible agent:
`parse_github_url` → `fetch_repo` → `list_repo_files` → `AgentClass().run(ctx)`. No
`_finalize`, no new scan row, the original scan untouched.

Score delta substitutes that agent's fresh findings into the stored report and calls the
**unmodified** `scoring.calculate_score`. Response: `{before, after, delta, fixed[],
still_failing[]}`, recorded on the `fix_applications` row (`state → verified`).

Needs a `{cls.name: cls}` lookup on both registries (neither has one). State transitions
validated: `planned → pr_open → merged → verified`, with `failed`/`abandoned` reachable
from anywhere; anything else raises.
**Note:** `63-verifying-a-fix-and-the-score-delta.md`.

---

## Deferred — not in this pass

**Stage D:** URL → repo bridge (`link-repo`, `stack.py`, header fixers writing into
`next.config.ts` / `vercel.json` / `netlify.toml` / `nginx.conf`).
**Stage E:** revoke UI, audit browser, remaining Tier 2 fixers (`dependencies.py`,
`dns.py`, `secret-env-committed`).

The registry and tier table are *designed for* these; they are not implemented. Three
working fixers beat twenty half-working ones.

---

## What only the developer can do

Register the GitHub App (github.com/settings/apps): name "Sentinels Autofix", callback
`http://localhost:8011/auth/github/callback`, permissions **Contents R/W, Pull requests
R/W, Metadata R, Workflows R/W** (the last only because pinning edits
`.github/workflows/*`). Generate a private key, store the `.pem` outside the repo, put the
App ID / client ID / client secret / key path in `backend/.env`. Never paste any of them
into chat.

Create a throwaway public repo containing a **third-party** GitHub Action, no `.gitignore`,
and a Dockerfile with no `USER` — the Stage B/C test target.

Merge the PR when it appears, then run Verify. Steps 12–16 of the definition of done are
the developer's; the report must say plainly which steps were run by whom.

---

## Definition of done

1. User scans a repo → 2. a fixable finding appears → 3. user clicks Fix → 4. deterministic
`FixPlan` → 5. exact diff shown → 6. explicit approval → 7. App authorization used →
8. `sentinels/…` branch created → 9. deterministic patch committed → 10. PR created →
11. PR explains the finding, the change, and what it does *not* fix → 12. user merges →
13. responsible agent re-runs → 14. FAIL → PASS → 15. score delta shown → 16. audit row exists.

Files existing is not "implemented".
