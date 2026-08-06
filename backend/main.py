"""Sentinels API — the FastAPI application object.

This module owns `app`. Uvicorn imports it by the string "main:app" and drives
it; nothing here opens a socket or listens on a port itself.

Run locally:
    .venv/Scripts/python.exe -m uvicorn main:app --reload
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

# Loads backend/.env into the process's environment (GROQ_API_KEY, if
# present) once, at startup — so ai/analyst.py's os.environ.get() call later,
# at request time, sees it without every module that wants an env var
# needing to load .env itself.
load_dotenv()

from agents.registry import list_agents  # noqa: E402
from agents.repo_registry import list_repo_agents  # noqa: E402
from ai.chat import answer as chat_answer  # noqa: E402
from ai.client import get_api_key  # noqa: E402
from ai.fixes import get_or_generate_fix  # noqa: E402
from ai.prompts import PROMPT_VERSION  # noqa: E402
from db import init_db  # noqa: E402
from models import AgentInfo, AgentResult, ChatMessage, ChecklistItem, FixSuggestion, RepoFileEntry, ScanReport, ScanRequest, ScanSummary  # noqa: E402
from orchestrator import run_scan, run_scan_stream  # noqa: E402
from repo_orchestrator import run_repo_scan, run_repo_scan_stream  # noqa: E402
from report.pdf import generate_pdf  # noqa: E402
from report.registry import get_exporter, list_formats  # noqa: E402
from storage.chat import load_messages  # noqa: E402
from storage.fixes import load_fixes_for_scan  # noqa: E402
from storage.repo_files import get_repo_files  # noqa: E402
from storage.scans import delete_scan, get_scan, list_scans, update_checklist_item  # noqa: E402

# Creates backend/data/sentinels.db and brings its schema up to date if it
# isn't already — safe to call on every startup (see db.init_db's docstring).
init_db()

VERSION = "0.1.0"

app = FastAPI(
    title="Sentinels",
    description="Passive website security auditor. Read-only checks only.",
    version=VERSION,
)

# The browser treats http://localhost:3000 (the Next.js frontend) and
# http://localhost:8000 (this API) as different origins — same host, different
# port is enough — and by default refuses to let JavaScript on one read a
# response from the other. This middleware sends the headers that grant that
# permission explicitly.
#
# Listing the two dev origins rather than allow_origins=["*"] is deliberate:
# a wildcard would let a page on *any* site drive this API using the visitor's
# machine as the source of the scan traffic. For a tool that makes outbound
# requests to third-party sites, that's a genuinely bad default to ship.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root() -> dict:
    """Signpost for anyone who opens the bare host, so it isn't a blank 404."""
    return {"service": "Sentinels", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict:
    """Liveness check.

    Deliberately does no work — no network calls, no disk, no agents. Its only
    job is to answer "is this process up and routing?". If it ever gets slow,
    a monitor watching it can no longer tell "server down" from "server busy".
    """
    return {
        "status": "ok",
        "service": "Sentinels",
        "version": VERSION,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/scan", response_model=ScanReport)
async def scan(request: ScanRequest) -> ScanReport:
    """Run a full scan against `request.url` and return the report.

    `async def` here (unlike `/health`'s plain `def`) because this endpoint
    genuinely awaits something — `run_scan` awaits real HTTP requests inside
    the agents it calls.
    """
    try:
        return await run_scan(request.url)
    except ValueError as exc:
        # normalize_url's complaints (empty string, bad scheme, no host) are
        # the client's fault, not the server's — 400, not a 500 crash.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/repo/scan", response_model=ScanReport)
async def repo_scan(request: ScanRequest) -> ScanReport:
    """Run a full scan against a public GitHub repo (`request.url`) and
    return the report. The repo-side sibling of `POST /scan` -- same
    request/response shape, same 400-on-ValueError contract, a different
    orchestrator underneath (`repo_orchestrator.run_repo_scan`).

    The live streaming variant (`GET /repo/stream`, mirroring
    `GET /scan/stream`) and the frontend launcher that calls it are R11's
    job (PLAN-v3, Phase R-D); this endpoint exists now so a repo scan is
    independently reachable and verifiable over real HTTP, the same way
    every other milestone in this codebase has been.
    """
    try:
        return await run_repo_scan(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sse(event: str, data: str) -> str:
    """Format one Server-Sent Events message. `\\n\\n` is the wire format's
    own message terminator — the browser's EventSource won't deliver a
    message until it sees the blank line after it."""
    return f"event: {event}\ndata: {data}\n\n"


@app.get("/scan/stream")
async def scan_stream(url: str) -> StreamingResponse:
    """Same scan as `POST /scan`, reported as it happens instead of all at
    once. Server-Sent Events, not JSON — a one-way, GET-only, plain-text
    streaming protocol the browser understands natively via `EventSource`,
    which is why this takes `url` as a query parameter instead of a JSON
    body the way `POST /scan` does: `EventSource` can only issue GET.

    Emits one `event: agent` per finished agent (real completion order, not
    `AGENTS`' declared order), then one `event: done` carrying the complete
    `ScanReport`. A bad URL can't become a `400` the way it does for
    `POST /scan` — once the first byte of a streaming response has gone out,
    the status code (200) is already committed — so it's reported as
    `event: failed` instead, a message *inside* the otherwise-successful
    stream.
    """

    async def events():
        try:
            async for event_name, payload in run_scan_stream(url):
                yield _sse(event_name, payload.model_dump_json())
        except ValueError as exc:
            yield _sse("failed", json.dumps({"detail": str(exc)}))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/repo/stream")
async def repo_scan_stream(url: str) -> StreamingResponse:
    """Same repo scan as `POST /repo/scan`, reported as it happens instead of
    all at once. The repo-side sibling of `GET /scan/stream` -- same SSE
    shape (`event: agent` per finished agent, one `event: done` at the end,
    a bad URL reported in-band as `event: failed` since the 200 is already
    committed by the time it's known), a different generator underneath
    (`repo_orchestrator.run_repo_scan_stream`).
    """

    async def events():
        try:
            async for event_name, payload in run_repo_scan_stream(url):
                yield _sse(event_name, payload.model_dump_json())
        except ValueError as exc:
            yield _sse("failed", json.dumps({"detail": str(exc)}))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/agents", response_model=list[AgentInfo])
def agents_list() -> list[AgentInfo]:
    """Return metadata for every registered scanner agent."""
    return list_agents()


@app.get("/repo/agents", response_model=list[AgentInfo])
def repo_agents_list() -> list[AgentInfo]:
    """Return metadata for every registered repo-scanner agent."""
    return list_repo_agents()


@app.get("/scans", response_model=list[ScanSummary])
def scans_list(limit: int = 20, offset: int = 0) -> list[ScanSummary]:
    """List stored scans, newest first. Paginate with `limit` and `offset`."""
    limit = min(max(limit, 1), 100)
    return list_scans(limit=limit, offset=offset)


@app.get("/scans/{scan_id}", response_model=ScanReport)
def scans_get(scan_id: str) -> ScanReport:
    """Return the full stored ScanReport for `scan_id`."""
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    return report


@app.get("/scans/{scan_id}/agents/{agent_name}", response_model=AgentResult)
def scans_agent_get(scan_id: str, agent_name: str) -> AgentResult:
    """Return one agent's result slice from a stored scan.

    Used by the per-agent detail page so it only fetches what it needs instead
    of the full report. Returns 404 if either the scan or the agent is missing.
    """
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    for result in report.agents:
        if result.agent == agent_name:
            return result
    raise HTTPException(
        status_code=404,
        detail=f"Agent {agent_name!r} not found in scan {scan_id!r}",
    )


@app.get("/scans/{scan_id}/files", response_model=list[RepoFileEntry])
def scans_files_get(scan_id: str) -> list[RepoFileEntry]:
    """Return the file tree (path, size, language, finding count) for a repo
    scan. Empty for a URL scan — `target_type` is what the frontend checks
    before ever calling this, but an empty list is also a perfectly valid
    answer on its own, not an error.
    """
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    return get_repo_files(scan_id)


@app.delete("/scans/{scan_id}")
def scans_delete(scan_id: str) -> Response:
    """Delete a scan and all its findings. Returns 204 on success, 404 if not found."""
    if not delete_scan(scan_id):
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    return Response(status_code=204)


@app.get("/scans/{scan_id}/checklist", response_model=list[ChecklistItem])
def checklist_get(scan_id: str) -> list[ChecklistItem]:
    """Return the deployment checklist for a stored scan."""
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    return report.checklist


class ChecklistAnswer(BaseModel):
    state: str          # "pass" | "fail"
    explanation: str = ""


@app.post("/scans/{scan_id}/checklist/{item_key}", response_model=ChecklistItem)
def checklist_answer(scan_id: str, item_key: str, body: ChecklistAnswer) -> ChecklistItem:
    """Update a self-attested checklist item's state.

    Only self_attested items are writable — auto and inferred items are computed
    from findings and cannot be overridden here.
    """
    if body.state not in ("pass", "fail"):
        raise HTTPException(status_code=422, detail="state must be 'pass' or 'fail'")

    explanation = body.explanation or (
        "Confirmed as done." if body.state == "pass" else "Marked as not done."
    )
    updated = update_checklist_item(scan_id, item_key, body.state, explanation)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Self-attested item {item_key!r} not found in scan {scan_id!r}",
        )

    # Return the updated item from the DB
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    for item in report.checklist:
        if item.item_key == item_key:
            return item
    raise HTTPException(status_code=404, detail=f"Item {item_key!r} not found")


@app.post("/scans/{scan_id}/findings/{finding_key}/fix", response_model=FixSuggestion)
async def finding_fix(
    scan_id: str, finding_key: str, regenerate: bool = False
) -> FixSuggestion:
    """Return an AI-generated fix suggestion for one finding (cached).

    First call is a live LLM request (~3-8 s). Subsequent calls return the
    cached result instantly. `?regenerate=true` forces a fresh LLM call.
    With no GROQ_API_KEY: returns 503 with a clear message, never a 500.
    """
    if not get_api_key():
        raise HTTPException(status_code=503, detail="AI fix suggestions require GROQ_API_KEY.")

    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")

    finding = next((f for f in report.findings if f.id == finding_key), None)
    if finding is None:
        raise HTTPException(
            status_code=404,
            detail=f"Finding {finding_key!r} not found in scan {scan_id!r}",
        )

    suggestion = await get_or_generate_fix(scan_id, finding_key, finding, regenerate=regenerate)
    if suggestion is None:
        raise HTTPException(status_code=503, detail="Fix suggestion generation failed. Try again.")
    return suggestion


class ChatQuestion(BaseModel):
    question: str


@app.post("/scans/{scan_id}/chat", response_model=ChatMessage)
async def chat_post(scan_id: str, body: ChatQuestion) -> ChatMessage:
    """Ask one question about a completed scan.

    Persists both the user question and the assistant answer to the DB so the
    conversation survives refresh. With no GROQ_API_KEY: returns 503, not 500.
    """
    if not get_api_key():
        raise HTTPException(status_code=503, detail="Chat requires GROQ_API_KEY.")

    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")

    msg = await chat_answer(scan_id, report, report.checklist, question)
    if msg is None:
        raise HTTPException(status_code=503, detail="Chat answer generation failed. Try again.")
    return msg


@app.get("/scans/{scan_id}/chat", response_model=list[ChatMessage])
def chat_history(scan_id: str) -> list[ChatMessage]:
    """Return the full conversation history for a scan, oldest first."""
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    return load_messages(scan_id)


@app.get("/export/formats")
def export_formats() -> list[dict[str, str]]:
    """List every registered export format — id, MIME type, file extension."""
    return list_formats()


@app.get("/scans/{scan_id}/export/{format_id}")
async def scan_export(scan_id: str, format_id: str) -> Response:
    """Export a stored scan in the given format (pdf | json | markdown).

    Looks up any cached AI fix suggestions for the scan and passes them to
    the exporter — a scan with none still exports cleanly (M19's graceful
    degradation, same rule as the rest of the AI layer).
    """
    exporter = get_exporter(format_id)
    if exporter is None:
        raise HTTPException(status_code=404, detail=f"Unknown export format {format_id!r}")

    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")

    fixes = load_fixes_for_scan(scan_id, PROMPT_VERSION)
    content = await exporter.render(report, fixes)

    host = urlparse(report.url).netloc or "report"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "report"

    return Response(
        content=content,
        media_type=exporter.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="sentinels-{slug}.{exporter.extension}"'
        },
    )


@app.post("/scan/pdf")
async def scan_pdf(report: ScanReport) -> Response:
    """Deprecated alias — kept through M17 per PLAN-v2.md, then removed.

    Prints a *finished* report to PDF, taking the whole `ScanReport` as the
    request body instead of a `url` — the frontend already has one sitting
    in state the moment the "Download PDF" button is visible. Re-scanning
    from just the URL was rejected: a live site can change between the two
    requests, so the PDF could show different findings than the report the
    user is actually looking at. This way, what downloads is guaranteed to
    match what's on screen.

    Prefer `GET /scans/{id}/export/pdf` — it also includes cached AI fixes,
    which this alias (no scan_id, just a bare report) has no way to look up.
    """
    pdf_bytes = await generate_pdf(report)

    host = urlparse(report.url).netloc or "report"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "report"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="sentinels-{slug}.pdf"'},
    )
