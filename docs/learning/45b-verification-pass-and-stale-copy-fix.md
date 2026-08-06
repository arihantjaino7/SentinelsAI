# 45b — Full R11/R12 verification pass, and a stale "Coming soon" fix

> **Status:** done. Ran `docs/PLAN-v3.md`'s own 8-item end-to-end verification
> checklist for real (not just spot-checked) and found one genuine bug along
> the way: the landing page's GitHub card still said "Coming soon" under the
> real, working launcher.

## What we built

Nothing new — this is a verification pass, run after merging in R12 (the
file-tree browser, built by a teammate). The point was to actually run
`docs/PLAN-v3.md`'s closing checklist instead of trusting the plan doc's own
"done" claim.

## What got checked, for real

A local fixture directory (fake AWS key in `.env`, `django==1.11.0` pinned in
`requirements.txt`) was fed straight into `RepoContext` — the same entry
point R4/R5 originally verified against — bypassing only the GitHub tarball
fetch, so every other step (agents, scoring, checklist, AI) ran for real:

- **Secrets + Dependencies agents**: real findings, correct `file_path`/`line`,
  real OSV.dev CVEs. The full `ScanReport.model_dump_json()` was checked for
  the raw fake key string — absent, only `AKIA...MNOP` anywhere.
- **Checklist determinism**: the same fixture scanned twice produced
  byte-identical checklist JSON and `readiness_score`.
- **No-`GROQ_API_KEY` path**: both a URL scan and a repo scan completed fully
  with the key popped from `os.environ` — empty `summary`, no crash.
- **The UI side**: loaded the fixture's scan in the real browser, opened the
  Secrets agent page, confirmed the masked evidence renders (never the real
  key), and clicked "Fix with AI" for real — it came back with a genuine fix,
  and the AI's own example code used a made-up placeholder key, never the
  real one, because the LLM was only ever handed the *masked* evidence in the
  first place.

## The one bug this pass actually found

`frontend/components/landing/scan-select/choices.ts` still had
`note: "Coming soon"` on the GitHub card, left over from before R11 shipped
the real `/repo` launcher. The card's `href` was already correct — clicking
it always worked — but the copy was actively lying to anyone who read it
before clicking. Fixed by deleting the `note` and its matching `aria-label`
suffix; `ScanChoiceCard.tsx` already renders `note` conditionally
(`{choice.note && (...)}`), so removing the field is enough — no component
change needed.

## Try it

- Open `/` — the GitHub card should read just "GitHub Repository", no
  "Coming soon" underneath.
- Run the fixture pipeline again yourself: build a directory with a fake
  `AKIA...`-shaped key in `.env` and a known-vulnerable pin in
  `requirements.txt`, hand it to `RepoContext` directly (skip
  `repo/fetch.py`), and run it through `AGENTS_REPO` + `repo_orchestrator._finalize`.

---

**Next:** nothing queued in `docs/PLAN-v3.md` — all 12 v3 milestones are
verified, not just marked done.
