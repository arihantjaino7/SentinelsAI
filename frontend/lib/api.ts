/* The one place the frontend knows the backend exists.

   These types are a hand-written mirror of backend/models.py. They are not
   checked against it automatically — nothing generates one from the other — so
   if a Pydantic model changes shape, this file has to change with it. That's a
   real cost, accepted deliberately: the alternative (an OpenAPI type generator
   wired into the build) is a whole toolchain for a contract with nine fields. */

// Mirrors backend/models.py `Severity`. A union of exact strings, not `string` —
// so a typo like "Criticl" is a compile error rather than a silent no-match.
export type Severity = "Critical" | "High" | "Medium" | "Low" | "Info";

// Mirrors `Status`. Lowercase here because that's what the enum's values are.
export type Status = "fail" | "warn" | "pass";

// Mirrors `EvidenceKind`. Each kind is a string slug.
export type EvidenceKind =
  | "request"
  | "response_headers"
  | "dns_record"
  | "certificate"
  | "html_snippet"
  | "log"
  | "screenshot"
  | "file_snippet"
  | "dependency";

// Mirrors the new `ScanReport.target_type` / `ScanSummary.target_type` discriminator.
export type TargetType = "url" | "repo";

export interface EvidenceItem {
  kind: EvidenceKind;
  label: string;
  content: string;
  content_type: string;
  collected_at: string;
  agent: string;
}

export interface Finding {
  id: string;
  title: string;
  category: string;
  severity: Severity;
  status: Status;
  owasp: string | null; // Optional[str] in Python arrives as null, not undefined
  evidence: string;
  description: string;
  remediation: string;
  agent: string;                          // which agent produced this finding
  evidence_items: EvidenceItem[];         // structured evidence (may be empty)
  file_path: string | null;               // repo-relative path; null for URL-scan findings
  line: number | null;                    // 1-based line number; null for URL-scan findings
  affected_url: string | null;            // the exact URL/host this is about; null = the scanned site itself
  confidence: number | null;              // 0-1; null = nothing to hedge, the check is certain
}

// Mirrors backend/models.py `SubdomainEntry` — one row of the subdomain
// inventory the `subdomain` agent builds (PLAN-v4 §V6). Same precedent as
// `RepoFileEntry`: a structured, non-Finding list carried on `ScanReport`.
export interface SubdomainEntry {
  host: string;
  record_type: string;                    // "A" | "AAAA" | "CNAME"
  record_value: string;
  source: string;                         // "certificate" | "ct-log" | "common-name"
  http_status: number | null;
  scheme: string | null;                  // "https" | "http" | null
  tls_valid: boolean | null;
  server: string | null;
  redirects_to: string | null;
  issue_count: number;
}

export interface AgentResult {
  agent: string;
  findings: Finding[];
  duration_ms: number;
  error: string | null;
}

export interface AgentInfo {
  name: string;
  display_name: string;
  purpose: string;
  checks: string[];
  category: string;
}

export type ChecklistTier = "auto" | "inferred" | "self_attested";
export type ChecklistState = "pass" | "warn" | "fail" | "unknown";

export interface ChecklistItem {
  item_key: string;
  title: string;
  tier: ChecklistTier;
  state: ChecklistState;
  explanation: string;
  suggested_fix: string;
  agent: string | null;
}

export interface ScanReport {
  id: string;                             // uuid4, set once the scan is persisted
  url: string;                            // a repo scan's "URL" is its GitHub URL -- same field
  target_type: TargetType;
  scanned_at: string;
  duration_ms: number;
  score: number;
  grade: string;
  summary: string; // "" when no GROQ_API_KEY is set — the report is still complete
  counts: Record<string, number>;
  findings: Finding[];
  agents: AgentResult[];
  readiness_score: number | null;         // 0-100, % of auto items passing
  deployment_status: string | null;       // "ready" | "caution" | "blocked"
  checklist: ChecklistItem[];
  subdomains: SubdomainEntry[];           // [] for repo scans and pre-v4 stored scans
}

// Mirrors backend/models.py `RepoFileEntry` — one row of a repo scan's file
// tree (R12). Empty/absent for URL scans, which have no `repo_files` rows.
export interface RepoFileEntry {
  path: string;
  size: number;
  language: string | null;
  finding_count: number;
}

// NEXT_PUBLIC_ is required for a variable to reach browser code at all; without
// that prefix Next.js keeps it server-side. The fallback is the dev default, so
// the app runs with no .env file present.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/* PLAN-v5 Stage 0: every protected route now requires a session cookie. Two
   small, shared pieces make that true everywhere without hand-editing every
   fetch call below:

   `withAuth(init)` merges in `credentials: "include"` — without it, the
   browser never attaches the cookie to a cross-port request (localhost:3000
   talking to localhost:8011 counts as cross-origin), and every call would
   look like it's coming from a signed-out visitor no matter who's signed in.

   `checkAuth(res)` is called right after every fetch below, before each
   function's own status handling. A 401 means the session is missing or
   expired — the one response every caller should react to the same way,
   so it's handled once here instead of once per function. */

function withAuth(init: RequestInit = {}): RequestInit {
  return { ...init, credentials: "include" };
}

function checkAuth(res: Response): void {
  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

export interface SessionUser {
  id: number;
  github_id: number;
  github_login: string;
  avatar_url: string | null;
}

/** Who the current session cookie belongs to, or null if signed out. */
export async function fetchMe(): Promise<SessionUser | null> {
  const res = await fetch(`${API_BASE}/auth/me`, withAuth());
  if (!res.ok) return null;
  return res.json() as Promise<SessionUser>;
}

/** Revoke the current session and clear its cookie. */
export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, withAuth({ method: "POST" }));
}

/** The URL to send the browser to for "Sign in with GitHub". */
export function githubLoginUrl(): string {
  return `${API_BASE}/auth/github/login`;
}

export interface ScanStreamHandlers {
  /** Called once per agent, the instant it finishes — real completion order. */
  onAgent: (result: AgentResult) => void;
  /** Called exactly once, when the full report is ready. */
  onDone: (report: ScanReport) => void;
  /** Called on either a rejected URL or a lost connection. Terminal either way. */
  onError: (message: string) => void;
}

/**
 * Open a live connection to `GET /scan/stream` and report each agent as it
 * finishes, then the completed report. Returns a function that closes the
 * connection — callers aren't required to use it (see the note on `onDone`
 * below for why this component doesn't need to), but it's returned so a
 * caller with a reason to cancel early always has one.
 */
export function streamScan(url: string, handlers: ScanStreamHandlers): () => void {
  // encodeURIComponent, not raw interpolation — url is user-typed text ending
  // up in a query string; without escaping, a stray "&" or "#" in it would
  // split the URL into extra query params instead of reaching the backend.
  //
  // { withCredentials: true } is EventSource's own equivalent of fetch's
  // credentials: "include" — without it the session cookie never reaches
  // this cross-port request either, and the stream 401s before the first event.
  const source = new EventSource(
    `${API_BASE}/scan/stream?url=${encodeURIComponent(url)}`,
    { withCredentials: true },
  );

  source.addEventListener("agent", (event) => {
    handlers.onAgent(JSON.parse((event as MessageEvent).data) as AgentResult);
  });

  source.addEventListener("done", (event) => {
    handlers.onDone(JSON.parse((event as MessageEvent).data) as ScanReport);
    // EventSource auto-reconnects on ANY closed connection, including a
    // normal end-of-stream — without this, the browser would reopen the
    // connection a few seconds later and silently re-run the whole scan.
    source.close();
  });

  // Our own application-level failure (a rejected URL) — named "failed", not
  // "error". EventSource reserves the plain "error" event for connection-level
  // problems; reusing that name for our own message would make the two
  // impossible to tell apart in the handler below.
  source.addEventListener("failed", (event) => {
    const body = JSON.parse((event as MessageEvent).data) as { detail?: string };
    handlers.onError(body.detail ?? "The scan could not be run.");
    source.close();
  });

  source.onerror = () => {
    // A genuine connection-level failure — the backend is unreachable, or
    // the connection dropped before a "done" ever arrived. Per spec this
    // should never fire for our own source.close() calls above (close() is
    // not a connection error); verified for real in the learning note by
    // killing the backend mid-scan and confirming this path, not silence,
    // is what actually runs.
    handlers.onError("Lost connection to the scanner.");
    source.close();
  };

  return () => source.close();
}

/**
 * Open a live connection to `GET /repo/stream` and report each agent as it
 * finishes, then the completed report. The repo-side sibling of
 * `streamScan` — same SSE event names (`agent`, `done`, `failed`), same
 * error/close handling; only the endpoint and the query param's meaning
 * (a GitHub URL, not a website URL) differ.
 */
export function streamRepoScan(repoUrl: string, handlers: ScanStreamHandlers): () => void {
  const source = new EventSource(
    `${API_BASE}/repo/stream?url=${encodeURIComponent(repoUrl)}`,
    { withCredentials: true },
  );

  source.addEventListener("agent", (event) => {
    handlers.onAgent(JSON.parse((event as MessageEvent).data) as AgentResult);
  });

  source.addEventListener("done", (event) => {
    handlers.onDone(JSON.parse((event as MessageEvent).data) as ScanReport);
    source.close();
  });

  source.addEventListener("failed", (event) => {
    const body = JSON.parse((event as MessageEvent).data) as { detail?: string };
    handlers.onError(body.detail ?? "The scan could not be run.");
    source.close();
  });

  source.onerror = () => {
    handlers.onError("Lost connection to the scanner.");
    source.close();
  };

  return () => source.close();
}

/**
 * Fetch a stored scan report by its UUID from `GET /scans/{scanId}`.
 * Throws if the scan is not found or the request fails.
 */
export async function fetchScan(scanId: string): Promise<ScanReport> {
  const res = await fetch(
    `${API_BASE}/scans/${encodeURIComponent(scanId)}`,
    withAuth(),
  );
  checkAuth(res);
  if (!res.ok) throw new Error(`Scan not found (${res.status})`);
  return res.json() as Promise<ScanReport>;
}

/**
 * Fetch the deployment checklist for a stored scan.
 * Returns an empty array on failure rather than throwing.
 */
export async function fetchChecklist(scanId: string): Promise<ChecklistItem[]> {
  try {
    const res = await fetch(
      `${API_BASE}/scans/${encodeURIComponent(scanId)}/checklist`,
      withAuth(),
    );
    checkAuth(res);
    if (!res.ok) return [];
    return res.json() as Promise<ChecklistItem[]>;
  } catch {
    return [];
  }
}

/**
 * Fetch the file tree for a repo scan from `GET /scans/{scanId}/files`.
 * Returns an empty array on failure, and also legitimately for URL scans
 * (which have no files) — callers gate on `target_type` before showing the
 * Files tab at all, so an empty array here is never itself an error state.
 */
export async function fetchScanFiles(scanId: string): Promise<RepoFileEntry[]> {
  try {
    const res = await fetch(
      `${API_BASE}/scans/${encodeURIComponent(scanId)}/files`,
      withAuth(),
    );
    checkAuth(res);
    if (!res.ok) return [];
    return res.json() as Promise<RepoFileEntry[]>;
  } catch {
    return [];
  }
}

/**
 * Answer a self-attested checklist item.
 * Returns the updated item on success, or throws on failure.
 */
export async function answerChecklistItem(
  scanId: string,
  itemKey: string,
  state: "pass" | "fail",
  explanation?: string,
): Promise<ChecklistItem> {
  const res = await fetch(
    `${API_BASE}/scans/${encodeURIComponent(scanId)}/checklist/${encodeURIComponent(itemKey)}`,
    withAuth({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state, explanation: explanation ?? "" }),
    }),
  );
  checkAuth(res);
  if (!res.ok) throw new Error(`Failed to update checklist item (${res.status})`);
  return res.json() as Promise<ChecklistItem>;
}

export interface FixSuggestion {
  why_it_exists: string;
  security_impact: string;
  exploitation: string;
  recommended_fix: string;
  best_practices: string[];
  framework_examples: Record<string, string>;
  generated_at: string;
  model: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

// Mirrors backend/models.py `FilePatch` (PLAN-v5 Stage A).
export interface FilePatch {
  path: string;
  action: "create" | "modify" | "delete";
  original_sha: string | null;
  original_content: string | null;
  new_content: string | null;
  diff: string;
}

// Mirrors backend/models.py `FixPlan` -- a deterministic, machine-actionable
// fix. Unlike `FixSuggestion` (AI prose above), no model ever produces this;
// plain Python decided every byte of every patch in it.
export interface FixPlan {
  finding_key: string;
  fixer_slug: string;
  tier: 1 | 2;
  summary: string;
  patches: FilePatch[];
  created_at: string;
}

/**
 * Preview a deterministic fix for one finding — computed live, never
 * persisted. `null` means there's no deterministic fixer for this finding
 * (only tier 1/2 findings ever have one); that's a normal answer, not an
 * error, and the caller should fall back to `FixSuggestionPanel`'s AI advice.
 */
export async function fetchFixPlan(
  scanId: string,
  findingKey: string,
): Promise<FixPlan | null> {
  const res = await fetch(
    `${API_BASE}/scans/${encodeURIComponent(scanId)}/findings/${encodeURIComponent(findingKey)}/fix/plan`,
    withAuth(),
  );
  checkAuth(res);
  if (res.status === 404) return null;
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Fix plan unavailable (${res.status})`);
  }
  return res.json() as Promise<FixPlan | null>;
}

/**
 * Plan and persist a deterministic fix for one finding, so it survives a
 * page refresh and is included in `GET /scans/{id}/fix/bundle.zip`.
 * Throws only on a genuine failure (not a repo scan, bad request) — an
 * unfixable finding comes back as a normal `{ fixable: false, plan: null }`
 * result, not a thrown error.
 */
export async function saveFixPlan(scanId: string, findingKey: string): Promise<FixPlan | null> {
  const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(scanId)}/fix/plan`, withAuth({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ finding_keys: [findingKey] }),
  }));
  checkAuth(res);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Fix plan unavailable (${res.status})`);
  }
  const results = (await res.json()) as { finding_key: string; plan: FixPlan | null; fixable: boolean }[];
  return results[0]?.plan ?? null;
}

/**
 * Download every fix plan already saved for a scan (via `saveFixPlan`) as
 * one zip of unified diffs. Throws if nothing has been planned yet.
 */
export async function downloadFixBundle(scanId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(scanId)}/fix/bundle.zip`, withAuth());
  checkAuth(res);
  if (!res.ok) {
    throw new Error(`No fix plans have been generated for this scan yet (${res.status})`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `sentinels-fixes-${scanId.slice(0, 8)}.zip`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

/**
 * Fetch (or generate) an AI fix suggestion for one finding.
 * `regenerate=true` bypasses the cache and forces a new LLM call.
 * Throws if unavailable (no API key → 503, finding not found → 404).
 */
export async function fetchFix(
  scanId: string,
  findingKey: string,
  regenerate = false,
): Promise<FixSuggestion> {
  const url = `${API_BASE}/scans/${encodeURIComponent(scanId)}/findings/${encodeURIComponent(findingKey)}/fix${regenerate ? "?regenerate=true" : ""}`;
  const res = await fetch(url, withAuth({ method: "POST" }));
  checkAuth(res);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Fix unavailable (${res.status})`);
  }
  return res.json() as Promise<FixSuggestion>;
}

/**
 * Send one question to the chatbot for a scan.
 * Throws if the chat endpoint is unavailable.
 */
export async function postChatMessage(
  scanId: string,
  question: string,
): Promise<ChatMessage> {
  const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(scanId)}/chat`, withAuth({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  }));
  checkAuth(res);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Chat unavailable (${res.status})`);
  }
  return res.json() as Promise<ChatMessage>;
}

/**
 * Load the full conversation history for a scan.
 * Returns an empty array on failure.
 */
export async function fetchChatHistory(scanId: string): Promise<ChatMessage[]> {
  try {
    const res = await fetch(`${API_BASE}/scans/${encodeURIComponent(scanId)}/chat`, withAuth());
    checkAuth(res);
    if (!res.ok) return [];
    return res.json() as Promise<ChatMessage[]>;
  } catch {
    return [];
  }
}

/**
 * POST the report already sitting in this page's state to `POST /scan/pdf`
 * and save the PDF it comes back with. No re-scan involved — the backend
 * prints exactly the report handed to it, so the file always matches what's
 * on screen (see the endpoint's docstring in `backend/main.py`).
 */
export async function downloadReportPdf(report: ScanReport): Promise<void> {
  const response = await fetch(`${API_BASE}/scan/pdf`, withAuth({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  }));
  checkAuth(response);

  if (!response.ok) {
    throw new Error(`PDF export failed (${response.status})`);
  }

  // A Blob is the browser's handle to binary data it hasn't decoded as text
  // or JSON — the right shape for a PDF's raw bytes. objectURL turns that
  // Blob into a temporary blob: URL an <a download> can point at, since
  // <a> has no way to "download this Blob" directly.
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);

  const host = (() => {
    try {
      return new URL(report.url).hostname;
    } catch {
      return "report";
    }
  })();

  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `sentinels-${host}.pdf`;
  // Never actually attached to the visible page — click() fires the
  // browser's save behaviour without it needing to render anywhere.
  link.click();

  // Revoking frees the blob: URL's memory. Deferred one tick (not called
  // immediately) because Firefox has been known to cancel the download if
  // the URL is revoked before it's finished starting.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}
