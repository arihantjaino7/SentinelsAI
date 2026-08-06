"""The shape every export format implements.

A `Protocol` (not an ABC) — Python structural typing: anything with these
three attributes and this method satisfies `Exporter`, with no inheritance
required. `PdfExporter`, `JsonExporter`, and `MarkdownExporter` each just
happen to match this shape.

`render` is async even though only the PDF exporter genuinely needs to await
anything (a headless browser) — JSON and Markdown just return immediately.
One uniform signature keeps `registry.py`'s caller simple: it always awaits,
never branches on which format it's calling.
"""
from __future__ import annotations

from typing import Optional, Protocol

from models import FixSuggestion, ScanReport


class Exporter(Protocol):
    format_id: str    # e.g. "pdf" — used in the URL and the registry key
    media_type: str   # MIME type sent in the HTTP response
    extension: str    # file extension for the download, e.g. "pdf"

    async def render(
        self, report: ScanReport, fixes: Optional[dict[str, FixSuggestion]] = None
    ) -> bytes:
        """Render one report to this format's bytes.

        `fixes` maps finding-slug -> cached AI fix suggestion, when any exist
        for this scan. Optional and defaults to None/empty — a report with no
        cached fixes must still export cleanly (same graceful-degradation
        rule as the rest of the AI layer).
        """
        ...
