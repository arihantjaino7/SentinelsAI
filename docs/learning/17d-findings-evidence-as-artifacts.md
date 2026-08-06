# A17d — Findings evidence as artifacts

> **Status:** done. Each finding's evidence now sits inside a bordered
> "glass" box instead of plain text.

## What we built

Every finding's `evidence` field — the actual header value, cert detail, or
`robots.txt` line the scan read from the real site — used to look like just
another paragraph of text. Now it sits inside its own bordered, frosted box
with an "Evidence" label, so it visually reads as something *lifted from the
scan*, not written for the report.

## No new concepts here

This one's genuinely simple: everything used already exists elsewhere in the
codebase.

- `.glass` — the frosted-box style (background blur + hairline border)
  defined in `frontend/app/globals.css`, already used by the Agent Log panel
  and the "Download PDF" button.
- `{finding.evidence && (...)}` — conditional rendering, already the pattern
  every other optional field on `FindingRow` uses.

This step is composition, not new mechanics — taking a box style and a
rendering pattern that already exist and combining them somewhere new.

## The actual code

`frontend/components/FindingRow.tsx`, before:

```tsx
{finding.evidence && (
  <p className="mt-3 font-mono text-xs leading-relaxed break-words text-muted">
    {finding.evidence}
  </p>
)}
```

After:

```tsx
{finding.evidence && (
  <div className="glass mt-3 px-4 py-3">
    <p className="font-mono text-[9px] uppercase tracking-[0.25em] text-muted">
      Evidence
    </p>
    <p className="mt-1.5 font-mono text-xs leading-relaxed break-words">
      {finding.evidence}
    </p>
  </div>
)}
```

Three small changes: wrapping it in a `.glass` box gives it a visible
boundary; the "Evidence" label (small, heavily spaced-out text) names what's
inside before you read it; and the evidence text itself dropped
`text-muted`, since the box now does the job of marking it as secondary — the
text inside reads at normal contrast.

## Try it

- Delete the `glass` class from the wrapping `<div>` and reload a real scan —
  the evidence falls back to plain text, no visible boundary.
- Merge the label and content back into one `<p>`
  (`Evidence: {finding.evidence}`) and compare — notice how much harder it is
  to tell label from data at a glance once they're the same size and weight.
- Scan `wordpress.org` — the Recon category's "Generator meta tag" finding
  has real evidence lifted from the live homepage, rendered safely as plain
  text rather than executed as markup.

## Words worth knowing

Nothing new this note — see `learning/17b-scroll-drift-and-refs.md` for the
`.glass` utility and `learning/15-components-props-and-the-report.md` for
conditional rendering.

---

**Next:** 17e — the report's waiting/loading state as its own set piece.
