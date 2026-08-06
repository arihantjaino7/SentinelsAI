"use client";

/* Bottom-right entry point into the chatbot.

   Chat used to live as a tab next to Overview/Checklist — but it's a side
   conversation, not another view of the scan, so it doesn't belong in the
   same row. `fixed` pulls it out of the page's normal flow entirely: it stays
   pinned to the viewport corner regardless of scroll position, which is
   exactly what a "floating" control means. Low opacity at rest is what keeps
   it from competing with the report — it's meant to be noticed, not to shout. */

import Link from "next/link";

export function FloatingChatButton({ scanId }: { scanId: string }) {
  return (
    <Link
      href={`/scan/${scanId}/chat`}
      aria-label="Ask about this scan"
      className="glass fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full text-muted opacity-60 transition-all hover:opacity-100 hover:text-parchment hover:bg-white/8"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="h-5 w-5"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"
        />
      </svg>
    </Link>
  );
}
