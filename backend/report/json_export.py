"""JSON exporter — the ScanReport, serialized directly.

No transformation, no hand-built structure: `report.model_dump()` is the same
shape the frontend already receives from `GET /scans/{id}`. Round-trips
cleanly back into a `ScanReport` — the optional `fixes` key added below is
extra data a plain `ScanReport(**data)` silently ignores, since Pydantic
drops unrecognized fields by default rather than rejecting them.
"""
from __future__ import annotations

import json
from typing import Optional

from models import FixSuggestion, ScanReport


class JsonExporter:
    format_id = "json"
    media_type = "application/json"
    extension = "json"

    async def render(
        self, report: ScanReport, fixes: Optional[dict[str, FixSuggestion]] = None
    ) -> bytes:
        payload = report.model_dump(mode="json")
        if fixes:
            payload["fixes"] = {key: fix.model_dump(mode="json") for key, fix in fixes.items()}
        return json.dumps(payload, indent=2).encode("utf-8")
