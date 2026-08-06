/* Agent metadata and per-agent result fetching. */

import { API_BASE } from "./api";
import type { AgentInfo, AgentResult } from "./api";

/**
 * Fetch the metadata for every registered agent from `GET /agents`.
 * Returns an empty array on failure — callers fall back to a hardcoded list.
 */
export async function fetchAgents(): Promise<AgentInfo[]> {
  try {
    const res = await fetch(`${API_BASE}/agents`);
    if (!res.ok) return [];
    return res.json() as Promise<AgentInfo[]>;
  } catch {
    return [];
  }
}

/**
 * Fetch the metadata for every registered repo agent from `GET /repo/agents`.
 * The repo-side sibling of `fetchAgents` — same empty-array-on-failure contract.
 */
export async function fetchRepoAgents(): Promise<AgentInfo[]> {
  try {
    const res = await fetch(`${API_BASE}/repo/agents`);
    if (!res.ok) return [];
    return res.json() as Promise<AgentInfo[]>;
  } catch {
    return [];
  }
}

/**
 * Fetch one agent's result slice from a stored scan.
 * Maps to `GET /scans/{scanId}/agents/{agentName}`.
 * Throws if not found — the caller shows a 404 state.
 */
export async function fetchAgentResult(
  scanId: string,
  agentName: string,
): Promise<AgentResult> {
  const res = await fetch(
    `${API_BASE}/scans/${encodeURIComponent(scanId)}/agents/${encodeURIComponent(agentName)}`,
  );
  if (!res.ok) throw new Error(`Agent result not found (${res.status})`);
  return res.json() as Promise<AgentResult>;
}
