"use client";

import { useState } from "react";
import { type ChecklistItem } from "@/lib/api";
import { ChecklistRow } from "./ChecklistRow";

interface Section {
  label: string;
  description: string;
  tier: ChecklistItem["tier"];
}

const SECTIONS: Section[] = [
  {
    label: "Auto-verified",
    description: "Sentinels confirmed these directly from scan data.",
    tier: "auto",
  },
  {
    label: "Passively inferred",
    description:
      "Weak signals — not conclusive. Useful hints, not hard evidence.",
    tier: "inferred",
  },
  {
    label: "Self-attested",
    description:
      "Sentinels cannot test these passively. Mark each one done or not done.",
    tier: "self_attested",
  },
];

interface Props {
  items: ChecklistItem[];
  scanId: string;
}

export function ChecklistTable({ items: initial, scanId }: Props) {
  const [items, setItems] = useState(initial);

  function handleUpdate(updated: ChecklistItem) {
    setItems((prev) =>
      prev.map((it) => (it.item_key === updated.item_key ? updated : it)),
    );
  }

  return (
    <div className="space-y-14">
      {SECTIONS.map((section) => {
        const sectionItems = items.filter((it) => it.tier === section.tier);
        if (sectionItems.length === 0) return null;
        return (
          <section key={section.tier}>
            <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted">
              {section.label}
            </h3>
            <p className="mt-2 font-mono text-xs text-muted/70">
              {section.description}
            </p>
            <ul className="mt-6">
              {sectionItems.map((item) => (
                <ChecklistRow
                  key={item.item_key}
                  item={item}
                  scanId={scanId}
                  onUpdate={handleUpdate}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
