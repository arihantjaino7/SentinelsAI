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
>
> Stage B implemented 2026-08-12, **live-verified the same day** — real GitHub App
> (`sentinels-autofix-4309`), real installation on a throwaway public repo
> ([`arihantjaino7/some-action-v1`](https://github.com/arihantjaino7/some-action-v1):
> a third-party-Action workflow, no `.gitignore`, a `Dockerfile` with no `USER`),
> real scan (`ci-unpinned-action-*` and `docker-root-user-Dockerfile` both fired
> correctly), real dry run, then a real apply:
> [PR #1](https://github.com/arihantjaino7/some-action-v1/pull/1), branch
> `sentinels/fix-959843b8-1786538197` → `main`, exactly the two planned files
> changed (`.gitignore` created, `.github/workflows/ci.yml`'s `hashicorp/setup-
> terraform@v2` resolved to a real commit SHA and pinned), both findings recorded
> as `fix_applications` rows in state `pr_open` with a frozen `plan` snapshot. Per
> the definition of done below, this satisfies step 11 (PR explains the finding,
> the change, and what it does *not* fix) through the PR itself; steps 12–16
> (merge, re-verify, score delta, developer-run reporting) are Stage C, built in
> the block below and **run against this real PR on 2026-08-13** — see that
> follow-up entry for the actual numbers.
>
> Two things fixed or noted during this live pass, neither of which touched the
> ten Stage B rules or any test:
> - **Real bug, fixed:** `main.py`'s `load_dotenv()` searched upward from the
>   process's *working directory*, which `.claude/launch.json` sets to the repo
>   root, not `backend/` — so `backend/.env` was silently never found when run via
>   the normal launch config (every env-gated feature failed with "not
>   configured" despite a correctly filled-in `.env`). Now loads
>   `Path(__file__).parent / ".env"` explicitly. Pre-existing since Stage 0, not
>   introduced by Stage B; just first surfaced by it.
> - **Known gap, not fixed:** the install callback redirects to
>   `{frontend}/settings?installed=...`, and no `/settings` page exists in the
>   Next.js app yet — a real 404 in the browser, harmless (the backend write
>   still completes and was confirmed via direct DB read), but confusing during
>   manual testing. Building that page is frontend work for whenever Stage B gets
>   wired to the UI, not part of this stage's scope.
>
> Migration
> `(12, _V12_SCHEMA)` rebuilds `fix_applications` (SQLite cannot ALTER a FK in
> place): adds `plan_json` + `pr_number`, makes `fix_plan_id` nullable /
> `ON DELETE SET NULL`, and adds the partial unique index on
> `(scan_id, finding_key) WHERE state NOT IN ('failed','abandoned')` — all three
> of invariants #1, #2 and the idempotency backstop. New models: `GitHubInstallation`,
> `FixApplyPreview`, `FixApplyResult`; `FixApplication` gains `pr_number` and a
> `plan` snapshot. New: `backend/storage/installations.py`, `remediation/tokens.py`
> (`app_jwt` RS256/9-min, `AppTokenProvider`, `DevTokenProvider` behind two
> switches, `fetch_installation`), `remediation/github.py` (`GitHubWriter` +
> `commit_files`; deliberately has **no** `update_ref`/`merge` method — rule 5
> enforced by absence, with a test asserting it), `remediation/pr_body.py`
> (branch/commit/title/body, per-fixer "what this does *not* fix" table with a
> generic fallback), `remediation/apply.py` (the ten-step sequence; every refusal
> before the first write). `storage/remediation.py` gained the `fix_applications`
> + `audit_log` half. Six new routes: `GET /auth/github/install`,
> `GET /auth/github/install/callback`, `GET /installations`,
> `POST /installations/{id}/revoke`, `POST /scans/{id}/fix/apply` (`dry_run`
> defaults to **true**), `GET /scans/{id}/fix/applications` (live PR-state
> refresh). First new dependencies since Stage 0: `PyJWT`, `cryptography`.
> Conflict #11 recorded and resolved (token minted before the drift read).
> Found in passing: `POST .../fix/apply` needed `response_model=None` — its two
> return shapes overlap enough that a declared union let pydantic validate a
> preview *as* a result and drop the diff. 321 tests green (88 new:
> `test_remediation_{tokens,github,pr_body,apply}.py`,
> `test_storage_{installations,fix_applications}.py`), all offline/mocked, plus a
> 14-check `TestClient` pass over the new routes (auth gating, dry-run writes
> nothing, live apply opens one PR, repeat apply returns the same PR, state
> refresh to `merged`, revoke blocks apply). Nothing in this stage is wired to the
> frontend yet — deliberately, per step 7. Notes:
> [`learning/61-github-apps-and-installation-tokens.md`](learning/61-github-apps-and-installation-tokens.md),
> [`learning/62-committing-without-a-clone.md`](learning/62-committing-without-a-clone.md).
>
> Stage C implemented 2026-08-12 (backend only, per its own spec — nothing in
> this stage is wired to the frontend). New: `backend/remediation/verify.py`
> (`verify_finding` — ownership → agent resolution → live PR-state refresh →
> re-fetch → one agent → substitute → `calculate_score` twice → record) and
> `remediation/states.py` (the transition table; `failed`/`abandoned` reachable
> from anywhere, a state to itself legal so re-verifying is idempotent, nothing
> leaves a finished state). Migration `(13, _V13_SCHEMA)` is a single
> `ALTER TABLE fix_applications ADD COLUMN verification_json TEXT` — no
> constraint changes, so none of migration 12's rebuild is needed. New model
> `VerificationResult` (`before`/`after`/`delta`/`target_fixed`/`fixed[]`/
> `still_failing[]`, plus the agent, ref, application id and whether it was
> recorded); `FixApplication` gains `verification`. `storage/remediation.py`
> gained `get_fix_application`, `save_verification` (state + evidence in one
> statement), and transition enforcement inside `update_fix_application_state`.
> Both registries gained the `{cls.name: cls}` lookup (`agent_for`,
> `repo_agent_for`), derived from the existing lists. One route:
> `POST /scans/{id}/findings/{key}/verify`.
>
> Three decisions worth recording, none of them a departure from this document:
> - **A crashed agent refuses (502) instead of scoring.** `BaseRepoAgent.run`
>   never raises, so a failed re-run returns *zero* findings — which would
>   substitute in as "every problem here is fixed". "I couldn't check" and
>   "it's fixed" must not collapse into the same answer.
> - **`verified` means "we looked", not "it passed".** A merged fix that didn't
>   work still becomes `verified`, with `target_fixed=false` carrying the
>   result — otherwise it would sit in `merged` forever, indistinguishable from
>   one nobody has checked.
> - **A finding with no `fix_applications` row is still verifiable** (someone
>   may have fixed it by hand): the result comes back `recorded=false` and the
>   audit log gets a `fix_verified_unrecorded` row. An unmerged PR, by contrast,
>   is refused with 409 — verifying it would re-observe the original problem and
>   report the fixer as broken.
>
> The installation token is used for the re-fetch when the caller has one
> (header set on the client `fetch_repo` already borrows, so `repo/fetch.py`
> itself needed no change); without one the read is unauthenticated, which is
> fine for a public repo since verification writes nothing to GitHub. 374 tests
> green (53 new: `test_remediation_verify.py` (19), `test_remediation_states.py`
> (11 cases), `test_agent_lookup.py`, `test_db_migrations.py` — migration 13 on
> top of a real v12 DB with rows — plus 5 added to
> `test_storage_fix_applications.py`), all offline: `fetch_repo` is replaced by
> a fake async context manager yielding a temp directory, while the agent and
> the scorer are the real ones. Plus a 16-check `TestClient` pass over the route
> (401 unauthenticated, 404 unknown scan/finding, 409 on an open PR with the row
> untouched, 200 + `recorded=false` with no application row, 200 +
> `state=verified` + evidence attached after merge, verification visible on
> `GET .../fix/applications`, original scan score unchanged, 403 for another
> user). Steps 12–16 of the definition of done were *implementable* as of this
> block; **run against a real merge on 2026-08-13** — see the follow-up entry
> below for the actual numbers.
> Note:
> [`learning/63-verifying-a-fix-and-the-score-delta.md`](learning/63-verifying-a-fix-and-the-score-delta.md).
>
> UI wiring, 2026-08-12 — not a stage in this document (Stages B and C are both
> backend by their own scope), but the work that makes them reachable, so it is
> recorded here. New: `app/settings/page.tsx` (the page the install callback has
> always redirected to and which did not exist — the "known gap" noted in the
> Stage B block above, now closed: session identity, live/revoked installations,
> connect, disconnect, and the `?installed=`/`?install_error=` banners) and
> `components/fixes/FixApplyPanel.tsx` (dry run → open PR → merge on GitHub →
> verify, mounted by `FixPlanPanel` only once a plan exists so nothing fetches on
> page load). `lib/api.ts` gained the Stage B/C mirrors (`GitHubInstallation`,
> `FixApplication`, `FixApplyPreview`, `FixApplyResult`, `VerificationResult`,
> `FixApplicationState`), the calls (`fetchInstallations`, `revokeInstallation`,
> `githubInstallUrl`, `applyFix` with `dryRun = true` as its default,
> `fetchFixApplications`, `verifyFinding`), an `ApiError` that keeps the HTTP
> status — 403 renders a link to `/settings`, 409 an informational line, anything
> else an error — and `isApplyPreview`, the hand-written discriminator the
> overlapping union needs (the frontend twin of the `response_model=None`
> problem). Two small edits elsewhere: `FixPlanPanel`'s stale "opening a pull
> request isn't wired up yet" footnote, and a Settings link in the scan nav.
> Beyond the endpoints' own scope, one addition: the idle state offers
> "Already fixed it yourself? Verify →", because the backend supports verifying a
> finding with no application row and nothing exposed it.
>
> Live-verified in a browser against the real repository (seeded session cookie,
> since sign-in is the developer's to do): `/settings` renders the real
> `arihantjaino7` installation; the `gitignore-present` row shows the real
> [PR #1](https://github.com/arihantjaino7/some-action-v1/pull/1) as
> `pr_open` with its branch and link; Verify on it returned the real 409 ("has
> not been merged yet") **without losing the pull request from the screen** — the
> point of splitting the panel's state by question rather than by phase; a dry
> run on `docker-root-user-Dockerfile` returned the real repo/branch/files/PR
> body and wrote **no** `fix_applications` row and **no** audit row; and
> "Verify by hand" on the same finding really re-ran `repo-config` against
> `main`, reporting **64 → 64, no change, still failing** — correct, because
> nothing has been merged. `tsc --noEmit` and ESLint clean (the three pre-existing
> ESLint errors elsewhere in the app were left alone). **Not clicked:** "Open
> pull request" — a second real PR on someone's repository is the developer's
> call, not this pass's. Note:
> [`learning/64-wiring-the-fix-flow-into-the-ui.md`](learning/64-wiring-the-fix-flow-into-the-ui.md).
>
> Overview-page fix count, 2026-08-12 — also not a stage, a small piece of
> discoverability: the scan overview page (the one landed on right after a
> scan) showed severity counts and a "main issue" callout with no sign a fix
> flow existed at all. New: `remediation/registry.py`'s `fixable_findings`
> (pure — calls only each Fixer's `handles()`, never `plan()`, so it is cheap
> enough to call on every overview page load; "might be fixable," the same
> honest hedge `FixPlanPanel`'s own check button already carries, since a
> Fixer can still find nothing left to do once it actually reads the repo),
> `models.FixSummary`, `GET /scans/{id}/fix/summary` (same "computed fresh per
> call, not carried on the immutable `ScanReport`" shape as
> `GET /scans/{id}/checklist`/`.../files`), and an `Autofix` badge alongside
> `MainIssue`/`DeploymentBadge` that links straight to the first fixable
> finding's agent page. Deliberately not a hardcoded id table on the frontend
> side — the backend's `FIXERS` list is the one place that table exists, so a
> sixth Fixer is picked up automatically rather than needing a second,
> forgettable edit. 378 tests green (4 new, `test_remediation_registry.py`);
> live-verified: the real repo scan returns `fixable_count: 5` (three from
> `repo-config`, two from `repo-hygiene`) and the badge links to `repo-hygiene`,
> not the agent the main-issue callout points at; a URL scan shows no badge and
> makes no `fix/summary` request at all (checked via the network log).
> `tsc --noEmit` and ESLint clean (the one pre-existing error on this page,
> unrelated to this change, left alone). Note:
> [`learning/65-a-badge-that-costs-one-cheap-request.md`](learning/65-a-badge-that-costs-one-cheap-request.md).
>
> **The definition of done closed end to end, 2026-08-13.** [PR #1](https://github.com/arihantjaino7/some-action-v1/pull/1)
> was merged (`gh pr merge 1 --repo arihantjaino7/some-action-v1 --merge
> --delete-branch`, commit `8859186`), then `POST
> .../findings/{key}/verify` was called for real, against the real merged
> repository, for both findings the PR covered:
>
> | Finding | Before | After | Delta | `target_fixed` |
> |---|---|---|---|---|
> | `gitignore-present` | 64 | 80 | +16 | true |
> | `ci-unpinned-action-.github-workflows-ci.yml-L10` | 64 | 80 | +16 | true |
>
> Both share one `repo-config` re-run (same agent, same PR), so both report the
> same delta from the same substitution. `docker-root-user-Dockerfile` — never
> part of this PR — correctly stayed in `still_failing`. Both `fix_applications`
> rows moved `pr_open → merged → verified`
> (`91126615-…`, `43088d12-…`), `GET .../fix/applications` returns the
> verification evidence on each, and `audit_log` recorded `pr_merged` then
> `fix_verified` for both. Steps 1–16 of the definition of done are now every
> one of them a fact, not a claim — 11 through a real PR body, 12 through a
> real GitHub merge, 13–15 through this table, 16 through the audit rows above.
>
> **One real gap this pass surfaced, deliberately not patched here:** the
> overview page's Autofix badge (previous entry) still read `fixable_count: 5`
> immediately after both findings above were verified — unchanged. That's
> because `fixable_findings()` counts against `report.findings`, the scan's
> frozen original record (conflict #6: scans are immutable), and has no view of
> `fix_applications` state at all. The badge answers "how many findings did the
> *original scan* have a Fixer for," not "how many still need one" — those two
> questions happen to coincide until the first fix is verified, and diverge
> the moment they aren't. Worth fixing (the badge should probably subtract
> verified/merged findings, or a re-scan should be encouraged once fixes land),
> but that is a UI-accuracy decision for whoever picks it up next, not
> something to silently change mid-instruction.

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
9. **`fix_plans` is `INSERT OR REPLACE`d on every re-plan** (`storage/remediation.py`),
   so a re-plan gives the row a *new* autoincrement id. `fix_applications.fix_plan_id`
   was `NOT NULL REFERENCES fix_plans(id) ON DELETE CASCADE` — a re-plan of an already-
   applied finding would have cascade-deleted its `fix_applications` row, silently
   destroying audit history for a PR that might still be open or already merged. Fixed
   in migration 12: `fix_applications` gets its own frozen `plan_json` snapshot and the
   FK becomes nullable/`ON DELETE SET NULL` — an audit row must never depend on a plan
   row surviving.
10. **No GitHub App *installation* flow exists.** `github_installations` (migration 10)
    has zero reads or writes anywhere — Stage 0 only built the *sign-in* half
    (`auth/github_oauth.py`: read identity once, discard the token). Stage B cannot
    mint an installation token without first knowing which installation belongs to
    which user's which repo, so a small install-linking flow (§Stage B) has to exist
    before `tokens.py` has anything to mint against.
11. **The drift re-check needs the installation token too.** Stage B's step order
    below mints the token at step 9, immediately before the first write, with the
    step-5 drift re-check reading through `source.get_file` unauthenticated. That
    breaks on a private repository: an unauthenticated Contents API call 404s, and
    the drift check would honestly but *wrongly* report "the file was deleted".
    Resolved by minting the token right after the installation lookup and using it
    for the reads as well — minting writes nothing, so `dry_run` still touches no
    state, and step 7 still stops before the first write. Recorded here rather than
    silently reordered.

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

Designed 2026-08-12 (audited against the actual Stage A code, not just this document —
see conflicts #9–10); **required invariants below are non-negotiable for this stage**,
not optional hardening, per explicit sign-off:

> 1. `fix_applications.plan_json` is an immutable snapshot of the exact `FixPlan` applied
>    — the audit record, independent of `fix_plans` ever changing or disappearing.
> 2. `fix_applications.fix_plan_id` is nullable, `ON DELETE SET NULL` — a live-plan
>    reference when convenient, never something an audit row's survival depends on.
> 3. **Strict ownership, no exception:** `POST /scans/{id}/fix/apply` requires
>    `scan.user_id == authenticated_user.id`. Unlike `DELETE /scans/{id}` (which treats a
>    legacy unowned scan as fair game for any signed-in user), an unowned scan can
>    **never** be applied — there is no one whose installation it would even use.
> 4. **Installation ownership is checked independently of scan ownership** — an active
>    (`revoked_at IS NULL`) `github_installations` row belonging to `authenticated_user.id`
>    whose `account_login` matches the target repo's owner. Both checks must pass; neither
>    substitutes for the other.

### Two things this stage has to build that PLAN-v5 previously assumed already existed

**Installation linking** (conflict #10) — a flow distinct from sign-in, since a user can
sign in without ever granting repo-write access:

- `GET /auth/github/install` — mints a signed `state`, redirects to
  `https://github.com/apps/<app-slug>/installations/new`.
- `GET /auth/github/install/callback?installation_id&setup_action&state` — verifies
  `state` against the session (CSRF, same pattern as `auth/github_oauth.py`'s login
  flow), then persists a `github_installations` row. No OAuth token round-trip needed to
  "verify" the installation belongs to this user: GitHub only ever redirects here after
  the signed-in-on-github.com user themselves completed the install/authorize screen for
  that installation, and the `state` match ties that redirect to *this* Sentinels session.
- `GET /installations` — the caller's linked installations (for a "connect a repo" UI).
- `POST /installations/{id}/revoke` — soft-revoke on our side (`revoked_at`); the real
  revocation still happens on GitHub's side, independently, whenever the user chooses.

**`backend/storage/installations.py`** (new) — CRUD for `github_installations`: save on
callback, look up by `(user_id, account_login)`, mark revoked. Nothing here yet.

### Added

`remediation/tokens.py` — `TokenProvider` ABC; `AppTokenProvider` mints ~1h installation
tokens from a JWT (RS256, `iss=app_id`, ~9min exp) signed with the App's private key,
via `POST /app/installations/{id}/access_tokens`; `DevTokenProvider` reads
`SENTINELS_GITHUB_DEV_TOKEN` and **refuses to run unless `SENTINELS_ALLOW_DEV_TOKEN=1`**.
First new dependencies since Stage 0: `PyJWT`, `cryptography`.

`remediation/github.py` — Git Data API, no local clone: base ref (reuses Stage A's
`source.resolve_ref_sha` — the commits endpoint already accepts a branch name) → one
`git/blobs` call per changed file → one `git/trees` call (base tree + new blobs) → one
`git/commits` call (one parent) → one `git/refs` call (create the branch pointing at that
commit) → one `pulls` call. One commit, one PR, however many files.

`remediation/pr_body.py` — deterministic title/body template. Always states, per finding:
what was fixed, and **what it does not fix** (secret removal never rotates or erases
history — CLAUDE.md rule 9) — assembled from data already on the `Finding`/`FixPlan`,
never from a model.

`remediation/apply.py` — the one place that calls `github.py`, mirroring `planning.py`'s
role for the plan endpoints. Order of operations for `apply(scan, finding_keys, dry_run)`:

1. Ownership check (invariant #3) → installation lookup (invariant #4).
2. Idempotency check — an existing **non-terminal** `fix_applications` row per requested
   `finding_key`. All-already-applied → return the existing PR, not a new one.
   Mixed (some applied, some new) → reject the batch rather than silently splitting it.
3. Re-run `validate_plan()` per finding — never trust a stored plan just because it
   passed once.
4. Cross-plan batch check (new, beyond Stage A's single-plan `validate_plan`): total
   files across the *whole* selection ≤ `MAX_FILES_PER_PR`; no two plans touch the same
   path.
5. Drift re-check — re-fetch every unique path's blob SHA via `source.get_file`, compare
   to `original_sha`. **Any** mismatch aborts the **entire batch**, before any write.
6. `MAX_PRS_PER_SCAN` / `MAX_PRS_PER_HOUR` budget check (constants exist since Stage A,
   unenforced until now).
7. `dry_run=True` stops here — returns repo, branch name, files, diffs, commit message,
   PR title/body. Nothing written. The live path is not wired to the frontend until dry
   run is boring against a throwaway repo.
8. Branch name validated against `^sentinels/fix-[0-9a-f]{8}-\d+$` and checked against
   the repo's `default_branch` before the first write call — defense in depth even
   though the prefix should make collision structurally impossible.
9. Mint token → the Git Data API sequence above → one PR.
10. Write one `fix_applications` row per finding (`state="pr_open"`, `plan_json` snapshot)
    + `audit_log` rows. On PR-creation failure after the branch ref was already created:
    best-effort `DELETE .../git/refs/heads/{branch}` so a failed apply never leaves an
    orphan branch sitting in the user's repo.

**`POST /scans/{id}/fix/apply`** — body `{finding_keys: list[str], dry_run: bool}`.
**`GET /scans/{id}/fix/applications`** — lists a scan's `fix_applications`; any row still
`pr_open` gets a live `GET .../pulls/{number}` on read, updating state to `merged`/closed
as GitHub reports it — Stage C trusts this field, so it has to be accurate, not just
"we haven't checked."

The installation token is also passed to `repo/fetch.py`, lifting GitHub's ceiling from 60
to 5000 requests/hour — verification re-downloads the tarball each run and would otherwise
hit the unauthenticated wall mid-demo.

### DB — migration `(12, _V12_SCHEMA)`

```sql
ALTER TABLE fix_applications ADD COLUMN plan_json TEXT;   -- backfilled NOT NULL going forward
-- fix_plan_id's FK behavior changes from ON DELETE CASCADE to ON DELETE SET NULL
-- (SQLite can't ALTER a FK in place -- rebuilt via the standard
-- create-new-table/copy/drop/rename sequence, same as any SQLite FK change)
CREATE UNIQUE INDEX idx_fix_applications_active
    ON fix_applications(scan_id, finding_key)
    WHERE state NOT IN ('failed', 'abandoned');
```

The partial unique index is the DB-level backstop for the idempotency check in `apply.py`
step 2 — belt and suspenders, not a replacement for the application-level check (which
gives a much better error message).

### Verification

GitHub failure injection (401, 403, 404, branch-already-exists, PR-creation failure,
commit failure — all against a mocked transport, same as Stage A's tests) for every step
of `github.py` and `tokens.py`; `apply.py` tests for both required invariants (ownership
rejection, installation-ownership rejection), idempotency (repeat call, mixed-selection
rejection), drift-abort (whole batch), budget rejection, orphan-branch cleanup on
PR-creation failure. Migration 12 applies cleanly on top of an existing v11 DB and the
partial index actually rejects a duplicate active row. Then a real PR against a
throwaway repo — **the flow is not reported as working until that PR URL exists**.
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
`http://localhost:8011/auth/github/callback`, **Setup URL**
`http://localhost:8011/auth/github/install/callback` with "Redirect on update" enabled
(this is what the Stage B install flow lands on — a *different* field from the callback
URL above), permissions **Contents R/W, Pull requests R/W, Metadata R, Workflows R/W**
(the last only because pinning edits `.github/workflows/*`). Generate a private key, store
the `.pem` outside the repo, put the App ID / slug / client ID / client secret / key path
in `backend/.env` (see `backend/.env.example` for the exact variable names). Never paste
any of them into chat.

Create a throwaway public repo containing a **third-party** GitHub Action, no `.gitignore`,
and a Dockerfile with no `USER` — the Stage B/C test target.

**Done 2026-08-13.** [PR #1](https://github.com/arihantjaino7/some-action-v1/pull/1)
was merged and both findings verified — real numbers in the "definition of
done closed end to end" entry above. Merging was run via `gh pr merge`
against the real repo (`arihantjaino7`'s own account, explicit go-ahead given
in chat); Verify was run against the endpoint directly with a session cookie
minted for the same account, the same shape the UI's own fetch calls use:

```
POST http://localhost:8011/scans/{scan_id}/findings/{finding_key}/verify
```

(For reference, that was scan `959843b8-…`, finding keys `gitignore-present`
and `ci-unpinned-action-.github-workflows-ci.yml-L10`. A 409 means the pull
request hasn't merged yet — the state this section describes until 2026-08-13.)

---

## Definition of done

1. User scans a repo → 2. a fixable finding appears → 3. user clicks Fix → 4. deterministic
`FixPlan` → 5. exact diff shown → 6. explicit approval → 7. App authorization used →
8. `sentinels/…` branch created → 9. deterministic patch committed → 10. PR created →
11. PR explains the finding, the change, and what it does *not* fix → 12. user merges →
13. responsible agent re-runs → 14. FAIL → PASS → 15. score delta shown → 16. audit row exists.

Files existing is not "implemented".
