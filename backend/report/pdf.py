"""Turn a finished `ScanReport` into a downloadable PDF.

M17 split this file in two: `html_doc.py` now owns "what does the report
look like" (the HTML string), and this file owns only "how do you turn HTML
into a PDF" — driving a real (headless) browser to print it, the same way a
human would use Ctrl+P on a normal web page. See
`docs/learning/17-pdf-export-and-playwright.md` for why a headless browser
is the tool for "HTML in, PDF out" at all.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Optional

from playwright.async_api import async_playwright

from models import FixSuggestion, ScanReport
from report.html_doc import render_html


async def _render_pdf(html: str) -> bytes:
    """Drive a real headless Chromium — the same engine, and the same `Ctrl+P`
    machinery, a human would use on a normal web page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="load")
            return await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
        finally:
            await browser.close()


def _render_pdf_on_own_loop(html: str) -> bytes:
    """Run `_render_pdf` on a Proactor event loop this function owns.

    Windows has two event loop implementations, and only one of them —
    Proactor — can start a subprocess. Playwright *must* start one: the
    browser it drives is a separate program, not a Python library. Normally
    that's fine, since Proactor is Python's default on Windows.

    `uvicorn --reload` breaks that assumption. In reload mode uvicorn
    deliberately switches the process to `WindowsSelectorEventLoopPolicy`,
    and on a Selector loop `asyncio.create_subprocess_exec` raises a bare
    `NotImplementedError` — so PDF export died with an unexplained 500 for
    anyone running the documented dev command.

    Building the loop directly (rather than via `asyncio.get_event_loop`)
    is the point: the policy is exactly what uvicorn has overridden, so
    asking the policy for a loop would hand back a Selector one again.
    """
    loop = asyncio.ProactorEventLoop()
    try:
        return loop.run_until_complete(_render_pdf(html))
    finally:
        loop.close()


async def generate_pdf(
    report: ScanReport, fixes: Optional[dict[str, FixSuggestion]] = None
) -> bytes:
    """Render `report` to HTML, then print that HTML to PDF."""
    html = render_html(report, fixes)

    if sys.platform != "win32":
        return await _render_pdf(html)

    # A loop can only be run by the thread that owns it, and this thread is
    # already busy running uvicorn's. `to_thread` hands the work to a spare
    # thread — which is free to run a loop of its own — and awaits the result
    # without blocking the server. Same tool the TLS agent (A8) uses to keep
    # a blocking socket handshake off the event loop.
    return await asyncio.to_thread(_render_pdf_on_own_loop, html)


class PdfExporter:
    """Registered in `report/registry.py` under format_id "pdf"."""

    format_id = "pdf"
    media_type = "application/pdf"
    extension = "pdf"

    async def render(
        self, report: ScanReport, fixes: Optional[dict[str, FixSuggestion]] = None
    ) -> bytes:
        return await generate_pdf(report, fixes)
