"use client";

/* A deterministic fix (PLAN-v5 Stage A) -- plain Python decided every byte
   of this diff, no model involved. Renders ABOVE FixSuggestionPanel when a
   finding has one; unlike that panel, checking here can come back with
   "no automatic fix", which just means the AI explanation below is this
   finding's only option -- not an error.

   Deliberately manual-trigger, same idle/loading/error shape as
   FixSuggestionPanel: fetching a plan means Sentinels re-reads the file from
   GitHub right now, and doing that automatically for every finding a repo
   scan's findings list renders would burn through GitHub's unauthenticated
   rate limit before a user looks at a single one. */

import { useState } from "react";
import { downloadFixBundle, fetchFixPlan, saveFixPlan, type FixPlan } from "@/lib/api";

interface Props {
  scanId: string;
  findingKey: string;
}

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "unavailable" }
  | { kind: "preview"; plan: FixPlan }
  | { kind: "saving"; plan: FixPlan }
  | { kind: "saved"; plan: FixPlan }
  | { kind: "error"; message: string };

const TIER_LABEL: Record<number, string> = {
  1: "Fix available",
  2: "Review required",
};

export function FixPlanPanel({ scanId, findingKey }: Props) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [bundleError, setBundleError] = useState<string | null>(null);

  async function check() {
    setState({ kind: "loading" });
    try {
      const plan = await fetchFixPlan(scanId, findingKey);
      setState(plan ? { kind: "preview", plan } : { kind: "unavailable" });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to check for an automatic fix.",
      });
    }
  }

  async function save(plan: FixPlan) {
    setState({ kind: "saving", plan });
    try {
      const saved = await saveFixPlan(scanId, findingKey);
      setState(saved ? { kind: "saved", plan: saved } : { kind: "unavailable" });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to save the fix plan.",
      });
    }
  }

  async function copyDiff(plan: FixPlan) {
    const text = plan.patches.map((p) => p.diff).join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard permission denial is rare and non-critical here -- the
      // diff is already visible on screen to select by hand.
    }
  }

  async function handleDownloadBundle() {
    setBundleError(null);
    try {
      await downloadFixBundle(scanId);
    } catch {
      setBundleError("Couldn't download the patch bundle. Try again.");
    }
  }

  if (state.kind === "idle") {
    return (
      <button
        type="button"
        onClick={check}
        className="glass mt-4 mr-3 border-parchment/25 px-5 py-2.5 font-mono text-xs uppercase tracking-[0.2em] text-parchment transition-colors hover:bg-white/10"
      >
        Check for automatic fix →
      </button>
    );
  }

  if (state.kind === "loading") {
    return (
      <div className="glass mt-4 px-4 py-3">
        <p className="animate-pulse font-mono text-[10px] uppercase tracking-[0.25em] text-muted">
          Reading the repo…
        </p>
      </div>
    );
  }

  // No deterministic fixer for this finding -- a normal outcome, not an
  // error. Rendered as a small dismissible note rather than nothing at all,
  // so the click that got here doesn't feel like it went nowhere.
  if (state.kind === "unavailable") {
    return (
      <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
        No automatic fix for this finding — try the AI suggestion below.
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="glass mt-4 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-critical">
          {state.message}
        </p>
        <button
          type="button"
          onClick={() => setState({ kind: "idle" })}
          className="mt-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted transition-colors hover:text-parchment"
        >
          Dismiss
        </button>
      </div>
    );
  }

  const { plan } = state;

  return (
    <div className="glass mt-4 space-y-4 px-5 py-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted">
          Deterministic fix
        </p>
        <span className="font-mono text-[9px] uppercase tracking-[0.25em] text-parchment">
          {TIER_LABEL[plan.tier] ?? "Fix available"}
        </span>
      </div>

      <p className="text-sm leading-relaxed">{plan.summary}</p>

      {plan.patches.map((patch) => (
        <DiffView key={patch.path} patch={patch} />
      ))}

      <div className="flex flex-wrap gap-3 pt-1">
        {state.kind === "preview" && (
          <button
            type="button"
            onClick={() => save(plan)}
            className="border border-parchment/25 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.2em] text-parchment transition-colors hover:bg-white/10"
          >
            Save fix plan
          </button>
        )}
        {state.kind === "saving" && (
          <p className="animate-pulse font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
            Saving…
          </p>
        )}
        {state.kind === "saved" && (
          <>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
              Saved — included in the fix bundle
            </p>
            <button
              type="button"
              onClick={handleDownloadBundle}
              className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted transition-colors hover:text-parchment"
            >
              Download patch bundle
            </button>
          </>
        )}
        {bundleError && (
          <p className="w-full font-mono text-[10px] uppercase tracking-[0.2em] text-critical">
            {bundleError}
          </p>
        )}
        <button
          type="button"
          onClick={() => copyDiff(plan)}
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted transition-colors hover:text-parchment"
        >
          Copy diff
        </button>
      </div>

      {/* No GitHub write happens here (Stage B, not shipped yet) -- saving
          only persists the plan so it survives a refresh and lands in the
          bundle above. Said explicitly so "Save" never reads as "this just
          opened a pull request". */}
      <p className="font-mono text-[8px] text-rule">
        Preview only — opening a pull request isn't wired up yet. Download the patch and apply it by hand.
      </p>
    </div>
  );
}

function DiffView({ patch }: { patch: FixPlan["patches"][number] }) {
  const lines = patch.diff.split("\n").filter((line) => line.length > 0);
  return (
    <div>
      <p className="font-mono text-[9px] uppercase tracking-[0.25em] text-muted">
        {patch.action} · {patch.path}
      </p>
      <pre className="mt-2 overflow-x-auto rounded border border-rule bg-transparent px-3 py-3 font-mono text-xs leading-relaxed">
        {lines.map((line, i) => (
          <div
            key={i}
            className={
              line.startsWith("+") && !line.startsWith("+++")
                ? "text-parchment"
                : line.startsWith("-") && !line.startsWith("---")
                  ? "text-muted line-through decoration-muted/40"
                  : line.startsWith("@@")
                    ? "text-muted"
                    : "text-rule"
            }
          >
            {line}
          </div>
        ))}
      </pre>
    </div>
  );
}
