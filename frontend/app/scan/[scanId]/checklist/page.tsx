"use client";

/* Deployment readiness checklist for one scan.

   Three tiers (see PLAN-v2.md §0.1):
     Auto-verified   — Sentinels confirmed from scan data
     Inferred        — passive signal, not conclusive
     Self-attested   — developer answers; Sentinels never tests */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchChecklist, type ChecklistItem } from "@/lib/api";
import { ChecklistTable } from "@/components/checklist/ChecklistTable";

function ReadinessBadge({ score, status }: { score: number; status: string | null }) {
  const color =
    status === "blocked"
      ? "text-critical"
      : status === "caution"
        ? "text-[#facc15]"
        : "text-[#4ade80]";

  const label =
    status === "blocked"
      ? "Blocked"
      : status === "caution"
        ? "Caution"
        : "Ready";

  return (
    <div className="glass flex items-center gap-8 px-7 py-6 sm:gap-10 sm:px-9 sm:py-8">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted sm:text-xs">
          Readiness score
        </p>
        <p className="mt-1.5 font-display text-4xl sm:text-5xl lg:text-6xl">
          {score}
        </p>
      </div>
      <div className="h-10 w-px bg-rule sm:h-14" />
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted sm:text-xs">
          Deployment status
        </p>
        <p
          className={`mt-1.5 font-mono text-sm uppercase tracking-[0.15em] sm:text-base ${color}`}
        >
          {label}
        </p>
      </div>
    </div>
  );
}

export default function ChecklistPage() {
  const { scanId } = useParams<{ scanId: string }>();
  const [items, setItems] = useState<ChecklistItem[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchChecklist(scanId)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [scanId]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-24">
        <p className="animate-pulse font-mono text-xs uppercase tracking-[0.35em] text-muted">
          Loading…
        </p>
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-24">
        <div className="mx-auto max-w-md text-center">
          <p className="font-mono text-xs uppercase tracking-[0.35em] text-muted">
            Not available
          </p>
          <p className="mt-4 font-display text-2xl">
            No checklist for this scan.
          </p>
          <Link
            href={`/scan/${scanId}`}
            className="glass mt-8 inline-block px-6 py-3 font-mono text-xs uppercase tracking-[0.2em] transition-colors hover:bg-white/8"
          >
            Overview
          </Link>
        </div>
      </div>
    );
  }

  // Compute readiness from auto items only (same logic as backend evaluator)
  const autoItems = items.filter((it) => it.tier === "auto");
  const passingAuto = autoItems.filter((it) => it.state === "pass").length;
  const readinessScore =
    autoItems.length > 0 ? Math.round((passingAuto / autoItems.length) * 100) : 100;

  const hasBlockingFail = items.some(
    (it) =>
      it.tier === "auto" &&
      it.state === "fail" &&
      ["https_enforced", "cert_valid", "no_env_exposure", "no_git_exposure"].includes(
        it.item_key,
      ),
  );
  const hasCaution = items.some(
    (it) =>
      it.tier !== "self_attested" && (it.state === "fail" || it.state === "warn"),
  );

  const status = hasBlockingFail ? "blocked" : hasCaution ? "caution" : "ready";

  return (
    <article className="mx-auto w-full max-w-7xl px-6 py-20 sm:px-8">
      <header className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-muted">
            Deployment checklist
          </p>
          <h1 className="mt-3 font-display text-3xl sm:text-4xl lg:text-5xl">
            Readiness review
          </h1>
          <p className="mt-2 font-mono text-xs text-muted sm:text-sm">
            {items.length} checks across three tiers
          </p>
        </div>
        <Link
          href={`/scan/${scanId}`}
          className="glass px-4 py-2 font-mono text-[10px] uppercase tracking-[0.2em] transition-colors hover:bg-white/8"
        >
          Overview
        </Link>
      </header>

      <div className="mt-10">
        <ReadinessBadge score={readinessScore} status={status} />
      </div>

      {/* Capped short of the article's full width — each row is a line of
          prose once expanded, and a checklist table stretched to 7xl would
          make every explanation an uncomfortably long line to read. */}
      <div className="mt-16 max-w-4xl">
        <ChecklistTable items={items} scanId={scanId} />
      </div>
    </article>
  );
}
