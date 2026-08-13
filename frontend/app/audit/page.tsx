"use client";

/* /audit — PLAN-v5 Stage E.

   `audit_log` has been written since Stage B (every plan, pull request, and
   verification lands a row), but nothing has ever read it back except
   tests. This is a plain reverse-chronological list of that history: no new
   design system work, the same glass/mono-label shapes /settings already
   established.

   With no `?scan=` in the URL it's the account-wide view (`GET /audit`) —
   every scan this account has ever touched. With `?scan=<id>` it narrows to
   one scan's own trail (`GET /scans/{id}/audit`), which is what the per-scan
   nav's new "Audit" entry links to. One page, one component, because the two
   only differ in which endpoint answers and whether a "back to scan" link
   makes sense. */

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchAudit, fetchScanAudit, type AuditLogEntry } from "@/lib/api";
import { useSession } from "@/lib/useSession";

const ACTION_LABELS: Record<string, string> = {
  plan_created: "Plan created",
  pr_opened: "Pull request opened",
  pr_merged: "Pull request merged",
  pr_failed: "Pull request failed",
  fix_verified: "Fix verified",
  fix_verified_unrecorded: "Verified (no open fix)",
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function AuditList() {
  const router = useRouter();
  const { user, loading: sessionLoading } = useSession();
  const params = useSearchParams();
  const scanId = params.get("scan");

  const [rows, setRows] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    let cancelled = false;

    // The scan-scoped endpoint answers oldest-first (it's a linear trail for
    // one scan); the account-wide one answers newest-first (it spans every
    // scan, so recency is the only order that makes sense). Reversing the
    // scoped result keeps this page newest-first either way.
    const load = scanId
      ? fetchScanAudit(scanId).then((r) => [...r].reverse())
      : fetchAudit();

    load
      .then((result) => {
        if (!cancelled) {
          setRows(result);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Couldn't load audit history.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sessionLoading, user, router, scanId]);

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-20 sm:px-8">
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="font-mono text-xs uppercase tracking-[0.35em] text-muted transition-colors hover:text-parchment"
        >
          Sentinels
        </Link>
        <Link
          href="/settings"
          className="font-mono text-xs uppercase tracking-[0.2em] text-muted transition-colors hover:text-parchment"
        >
          Settings
        </Link>
      </div>

      <h1 className="mt-8 font-display text-5xl sm:text-6xl">Audit</h1>

      {scanId ? (
        <p className="mt-4 font-mono text-xs uppercase tracking-[0.2em] text-muted">
          Scoped to one scan —{" "}
          <Link href="/audit" className="underline decoration-rule hover:text-parchment">
            view all activity
          </Link>
          {" · "}
          <Link
            href={`/scan/${scanId}`}
            className="underline decoration-rule hover:text-parchment"
          >
            back to scan
          </Link>
        </p>
      ) : (
        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">
          Every plan, pull request, and verification Sentinels has recorded for this
          account — who did what, on which scan, and when.
        </p>
      )}

      {error && (
        <p className="glass mt-6 px-4 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-critical">
          {error}
        </p>
      )}

      {rows === null ? (
        <p className="mt-8 animate-pulse font-mono text-[10px] uppercase tracking-[0.25em] text-muted">
          Loading…
        </p>
      ) : rows.length === 0 ? (
        <p className="mt-8 text-sm text-muted">
          {scanId
            ? "No recorded activity for this scan yet."
            : "No recorded activity yet — this fills in once a fix is planned, opened, or verified."}
        </p>
      ) : (
        <ul className="mt-8 space-y-5">
          {rows.map((row) => (
            <li key={row.id} className="border-l-2 border-rule pl-5">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <p className="text-lg leading-snug">{actionLabel(row.action)}</p>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
                  {formatTimestamp(row.created_at)}
                </p>
              </div>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
                {row.scan_id ? (
                  <Link
                    href={`/scan/${row.scan_id}`}
                    className="underline decoration-rule hover:text-parchment"
                  >
                    {row.scan_url ?? row.scan_id}
                  </Link>
                ) : (
                  "deleted scan"
                )}
                {row.finding_key && <> {" · "}{row.finding_key}</>}
              </p>
              {row.detail && <p className="mt-2 text-sm text-muted">{row.detail}</p>}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

export default function AuditPage() {
  return (
    <Suspense fallback={null}>
      <AuditList />
    </Suspense>
  );
}
