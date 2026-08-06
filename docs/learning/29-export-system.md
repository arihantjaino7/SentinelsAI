# 29 — The export system: registry, JSON, and Markdown

> **Status:** done. A scan can now be downloaded as PDF, JSON, or Markdown from `GET /scans/{id}/export/{format}`, and adding a fourth format is one new file plus one line in a registry.

## What we built

The PDF exporter used to be one big file that built HTML and printed it in the same breath. We split that in two — `report/html_doc.py` now owns "what does the report look like," `report/pdf.py` owns only "turn that HTML into a PDF" — and added two more exporters, `report/json_export.py` and `report/markdown.py`, that skip the HTML step entirely. All three are registered in `report/registry.py` under a short id (`pdf`, `json`, `markdown`), and one new endpoint, `GET /scans/{id}/export/{format}`, looks up whichever one you ask for. Exports now also include the deployment checklist, evidence, and any cached AI fix suggestions — gracefully absent if a scan doesn't have them yet.

## The one big idea: a Protocol instead of a base class

`report/base.py` defines what every exporter must look like — three attributes and one method — as a `Protocol`, not an abstract base class:

```python
class Exporter(Protocol):
    format_id: str
    media_type: str
    extension: str
    async def render(self, report, fixes=None) -> bytes: ...
```

The difference from a normal base class: `PdfExporter`, `JsonExporter`, and `MarkdownExporter` don't write `class PdfExporter(Exporter):` anywhere. They just happen to have those three attributes and that method, and that's enough — Python calls this **structural typing**, informally "duck typing with a type-checker watching." If it walks like a duck and quacks like a duck, it's a duck; nobody has to fill out paperwork declaring it a duck first.

A standalone example, nothing to do with exporting:

```python
from typing import Protocol

class Honks(Protocol):
    def honk(self) -> str: ...

class Car:
    def honk(self) -> str:
        return "beep!"

class Goose:
    def honk(self) -> str:
        return "HONK"

def make_it_honk(thing: Honks) -> str:
    return thing.honk()

make_it_honk(Car())     # "beep!"  — Car never mentioned Honks
make_it_honk(Goose())   # "HONK"   — neither did Goose
```

Neither `Car` nor `Goose` inherits from `Honks`. The type checker (and `make_it_honk`) only cares that the shape matches. That's exactly the relationship between `Exporter` and the three exporter classes — `registry.py` can hold all three in one `dict[str, Exporter]` without any of them knowing `Exporter` exists.

## Verifying "zero behaviour change" for a refactor

M17's rule was that splitting `pdf.py` in two must not change what a PDF looks like. The naive way to check that is "generate a PDF before, generate one after, diff the files" — but two PDFs from *identical* HTML aren't always byte-identical; Chromium can embed things like creation timestamps that differ run to run even when nothing visible changed.

So the actual check skipped PDF bytes and compared the HTML string instead — that's the part that actually moved. I loaded the pre-refactor `pdf.py` from git history, called its old `render_html()` and the new `html_doc.render_html()` on the same stripped-down report (no checklist, no evidence — the shape a report had before those features existed), and diffed the two strings. The only differences were a few blank lines where an empty `{checklist_html}` placeholder now sits in the template — invisible once a browser renders it, since HTML collapses whitespace between block elements. Everything that actually draws — the score ring, the findings list, the agent log — was character-for-character identical.

## The actual code

`report/json_export.py` is the simplest exporter — no rendering at all, just the model's own serialization:

```python
async def render(self, report, fixes=None):
    payload = report.model_dump(mode="json")
    if fixes:
        payload["fixes"] = {k: f.model_dump(mode="json") for k, f in fixes.items()}
    return json.dumps(payload, indent=2).encode("utf-8")
```

Adding a top-level `"fixes"` key doesn't break round-tripping: `ScanReport(**data)` on that same JSON still works, because Pydantic silently drops keys it doesn't recognize rather than rejecting them.

`report/markdown.py` reuses `html_doc.group_by_category()` — the same worst-category-first ordering the PDF and the frontend use — so all three formats agree on what comes first without three separate copies of that logic.

The new endpoint in `main.py` ties it together:

```python
@app.get("/scans/{scan_id}/export/{format_id}")
async def scan_export(scan_id, format_id):
    exporter = get_exporter(format_id)          # None -> 404
    report = get_scan(scan_id)                  # None -> 404
    fixes = load_fixes_for_scan(scan_id, PROMPT_VERSION)
    content = await exporter.render(report, fixes)
    return Response(content=content, media_type=exporter.media_type, ...)
```

`load_fixes_for_scan` (new, in `storage/fixes.py`) joins `fix_suggestions` against `findings` to build a `{finding_key: FixSuggestion}` dict — empty if nothing's been generated for that scan yet.

## Try it

- `curl localhost:8000/export/formats` — lists all three registered formats.
- `curl localhost:8000/scans/{id}/export/json | python -m json.tool` — readable JSON, including a `"fixes"` key if you've generated any.
- `curl localhost:8000/scans/{id}/export/markdown` — paste the output straight into a GitHub issue and watch it render.
- Pick an old scan from before the checklist existed and export it in all three formats — none of them should error or show a broken "Deployment checklist" section; they just skip it.

## Words worth knowing

- **Protocol** — a way to say "anything with this shape counts," with no inheritance required. Contrast with an abstract base class, which requires `class X(Base):`.
- **Structural typing** — matching by shape (attributes/methods present) instead of by declared ancestry.
- **Round-trip** — serializing data out and parsing it back in; a good test that nothing was lost or corrupted in between.

---

**Next:** Phase F was the last phase in `docs/PLAN-v2.md` — all 19 milestones are now shipped. Future work would start a new plan.
