"use client";

/* The scan launcher page — one screen, one job: take a URL and start a scan.

   This used to be the site's root (`app/page.tsx`). It moved here when `/`
   became the landing page, which is the split `docs/PLAN-v3.md` R11 always
   called for: launchers at top-level `/url` and `/repo`, deliberately NOT
   `/scan/url` — that would collide with the `/scan/[scanId]` dynamic
   segment and be swallowed by it.

   The form itself now lives in `components/ScanLauncher.tsx`, because the
   landing page ends with the same working input. This page is the copy
   around it. */

import Link from "next/link";
import { ScanLauncher } from "@/components/ScanLauncher";

export default function UrlScanPage() {
  return (
    <section className="flex flex-1 items-center justify-center px-6 py-24">
      <div className="mx-auto w-full max-w-3xl">
        {/* Now a link — this page is no longer the root, so the wordmark is
            the way back to the landing page. */}
        <Link
          href="/"
          className="font-mono text-xs uppercase tracking-[0.35em] text-muted transition-colors hover:text-parchment"
        >
          Sentinels
        </Link>

        <ScanLauncher
          footnote={
            <p className="mt-16 max-w-md font-mono text-xs leading-relaxed text-muted">
              Passive inspection only. Sentinels sends ordinary GET requests to
              public paths and reads public DNS. It never sends attack traffic.
            </p>
          }
        >
          <h1 className="mt-12 font-display text-5xl leading-[1.08] sm:text-6xl">
            Every site leaves
            <br />a record.
          </h1>

          <p className="mt-7 max-w-md leading-relaxed text-muted">
            Sentinels reads it — response headers, TLS certificate, DNS
            records, robots.txt — and issues a graded inspection report.
          </p>
        </ScanLauncher>
      </div>
    </section>
  );
}
