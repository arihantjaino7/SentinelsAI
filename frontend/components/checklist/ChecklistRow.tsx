"use client";

import { useState } from "react";
import { answerChecklistItem, type ChecklistItem } from "@/lib/api";

const STATE_LABEL: Record<string, string> = {
  pass: "Pass",
  warn: "Warning",
  fail: "Fail",
  unknown: "Not answered",
};

const STATE_COLOR: Record<string, string> = {
  pass: "text-[#4ade80]",
  warn: "text-[#facc15]",
  fail: "text-critical",
  unknown: "text-muted",
};

const STATE_DOT: Record<string, string> = {
  pass: "bg-[#4ade80]",
  warn: "bg-[#facc15]",
  fail: "bg-critical",
  unknown: "bg-rule",
};

const TIER_LABEL: Record<string, string> = {
  auto: "Auto-verified",
  inferred: "Passively inferred — not conclusive",
  self_attested: "Self-attested",
};

interface Props {
  item: ChecklistItem;
  scanId: string;
  onUpdate: (updated: ChecklistItem) => void;
}

export function ChecklistRow({ item, scanId, onUpdate }: Props) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  async function answer(state: "pass" | "fail") {
    setSaving(true);
    try {
      const updated = await answerChecklistItem(scanId, item.item_key, state);
      onUpdate(updated);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="border-b border-rule last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-4 px-0 py-5 text-left"
      >
        {/* State dot */}
        <span
          className={`mt-1 h-2 w-2 flex-shrink-0 rounded-full ${STATE_DOT[item.state]}`}
          aria-hidden="true"
        />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
            <span className="font-mono text-sm sm:text-base">{item.title}</span>
            <span
              className={`font-mono text-xs sm:text-sm ${STATE_COLOR[item.state]}`}
            >
              {STATE_LABEL[item.state]}
            </span>
          </div>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.15em] text-muted">
            {TIER_LABEL[item.tier]}
          </p>
        </div>

        <span className="font-mono text-xs text-muted">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="pb-6 pl-6">
          <p className="font-mono text-xs leading-relaxed text-parchment/80 sm:text-sm">
            {item.explanation}
          </p>

          {item.suggested_fix && (
            <div className="mt-4">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
                Suggested fix
              </p>
              <p className="mt-2 font-mono text-xs leading-relaxed text-parchment/70 sm:text-sm">
                {item.suggested_fix}
              </p>
            </div>
          )}

          {/* Self-attestation buttons */}
          {item.tier === "self_attested" && (
            <div className="mt-5 flex gap-3">
              <button
                type="button"
                disabled={saving}
                onClick={() => answer("pass")}
                className={`glass px-4 py-2 font-mono text-[10px] uppercase tracking-[0.2em] transition-colors hover:bg-white/8 disabled:cursor-not-allowed disabled:text-muted ${
                  item.state === "pass" ? "ring-1 ring-[#4ade80]/40" : ""
                }`}
              >
                {saving ? "Saving…" : "Done"}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => answer("fail")}
                className={`glass px-4 py-2 font-mono text-[10px] uppercase tracking-[0.2em] transition-colors hover:bg-white/8 disabled:cursor-not-allowed disabled:text-muted ${
                  item.state === "fail" ? "ring-1 ring-critical/40" : ""
                }`}
              >
                {saving ? "Saving…" : "Not done"}
              </button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
