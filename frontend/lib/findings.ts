/* Ordering and grouping logic for findings.

   Kept out of the components on purpose: this is decision-making, they are
   drawing. It also means the ordering rules can be reasoned about (and changed)
   without reading any JSX. */

import type { Finding, Severity } from "./api";

// Mirrors the ordering implied by SEVERITY_PENALTY in backend/models.py.
// Higher number = worse. Used for sorting only — never for scoring, which
// stays entirely on the backend and entirely deterministic (see A6).
const SEVERITY_RANK: Record<Severity, number> = {
  Critical: 4,
  High: 3,
  Medium: 2,
  Low: 1,
  Info: 0,
};

/** Severities worth showing as a headline count, worst first. */
export const HEADLINE_SEVERITIES: Severity[] = [
  "Critical",
  "High",
  "Medium",
  "Low",
];

export function isProblem(finding: Finding): boolean {
  // WARN and FAIL both count as problems — the same call backend/scoring.py
  // makes when deducting points, kept consistent so the list a reader sees
  // matches the list that produced the score.
  return finding.status !== "pass";
}

export interface CategoryGroup {
  category: string;
  problems: Finding[];
  passed: Finding[];
}

/**
 * Group findings by category, worst category first.
 *
 * Categories are ordered by their most severe problem rather than by a
 * hardcoded list, so the thing most worth reading is always at the top —
 * whichever agent happened to find it.
 */
export function groupByCategory(findings: Finding[]): CategoryGroup[] {
  const groups = new Map<string, CategoryGroup>();

  for (const finding of findings) {
    let group = groups.get(finding.category);
    if (!group) {
      group = { category: finding.category, problems: [], passed: [] };
      groups.set(finding.category, group);
    }
    (isProblem(finding) ? group.problems : group.passed).push(finding);
  }

  for (const group of groups.values()) {
    group.problems.sort(
      (a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity],
    );
  }

  return [...groups.values()].sort((a, b) => {
    const worst = (g: CategoryGroup) =>
      g.problems.length ? SEVERITY_RANK[g.problems[0].severity] : -1;
    // Tie-break on problem count so two equally-severe categories still have a
    // stable, meaningful order rather than depending on iteration order.
    return worst(b) - worst(a) || b.problems.length - a.problems.length;
  });
}
