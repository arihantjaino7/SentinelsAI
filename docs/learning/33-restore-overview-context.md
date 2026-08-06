# 33 — Bring back the overview's context, clarify the fix button

> **Status:** done. Overview now shows a "main issue" callout and readiness/deployment status again, plus the plain-English assessment paragraph. Agent pages make the AI fix button harder to miss, and explicitly say "nothing to fix" when an agent is clean.

## What changed and why

Note 32 stripped the overview down to just score + agent buttons — reasonable in isolation, but it went one step too far: readiness/deployment status and a one-line "what's actually wrong" summary are things worth seeing without a click, they're not the same as the *full* findings list (which correctly still lives one click away, per agent). So this note adds back, between the header and the agent panel:

- **Main issue** — the single worst finding in the report, as a small clickable callout linking straight to the agent that found it.
- **Deployment** — readiness score + status (ready/caution/blocked), linking to the full Checklist tab.
- **Assessment** — the AI-generated plain-English paragraph.

Nothing from note 32's simplification of the agent panel or removal of the full findings list changed — those stay gone from the overview.

## The "missing" fix button

Not a bug — verified live by clicking "Get AI fix" end to end (network tab showed a real `POST .../fix` returning a full suggestion). The actual gap: the button **only exists when an agent has fail/warn findings**. An agent with a clean result (e.g. this scan's DNS agent — SPF and DMARC both passed) correctly shows *zero* findings and therefore zero fix buttons — but the page gave no indication that this was intentional. It just... didn't have the section other agents had. That reads exactly like "the feature is missing here."

The fix is one explicit sentence, not a code fix: when an agent has no problems, the Issues section still renders, saying so —

```tsx
{problems.length > 0 ? (
  <section>...existing Issues list with FindingRow + fix button...</section>
) : (
  !result.error && (
    <section>
      <h2>Issues</h2>
      <p>Every check passed here — nothing to fix.</p>
    </section>
  )
)}
```

Also bumped the button itself — `Get AI fix →` at `text-[10px]` was styled identically to every navigation chrome button on the site (Download PDF, New scan, etc.), so it didn't stand out as *the* thing to click on a finding. Renamed to `Fix with AI →`, bigger text, a visible border — it's the one button on the page that actually generates something, so it should look different from the ones that just navigate.

## Try it

- Open a scan's overview: header, then "Main issue" + "Deployment" side by side, then the assessment paragraph, then the agent grid.
- Open an agent with issues (e.g. `headers` on most real sites) — the "Fix with AI →" button should be clearly bigger/bolder than "Download PDF" elsewhere on the site.
- Open a clean agent (e.g. `dns` on a well-configured domain) — should read "Every check passed here — nothing to fix," not a blank gap.

## Words worth knowing

- **Discoverability vs. functionality** — a feature can work perfectly and still be "missing" from a user's perspective if there's no visible reason to notice it's absent in the one case where it doesn't apply.
