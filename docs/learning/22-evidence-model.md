# 22 — Evidence model + Headers agent

> **Status:** done. Every Headers finding now carries a structured `evidence_items` list, stored in a new `evidence_items` table, alongside the existing plain-text `evidence` string.

## What we built

Up to now, a `Finding` had one flat string called `evidence` — e.g. `"content-security-policy: default-src 'self'"`. That's fine for reading, but useless for building a UI that wants to know "is this a request, a DNS record, or a certificate?" so it can render each one differently. This step adds a second, richer field, `evidence_items`, that tags each piece of proof with a *kind*. We proved the whole shape on the Headers agent only — the other four agents still return an empty list — before touching everything at once.

## The one big idea: tagging data with an enum instead of guessing from its shape

An `EvidenceItem` looks like this:

```python
class EvidenceItem(BaseModel):
    kind: EvidenceKind        # e.g. "response_headers", "dns_record", "certificate"
    label: str                # short caption, e.g. "Response headers"
    content: str              # the actual evidence text
    content_type: str = "text/plain"
    collected_at: str         # when this was captured
    agent: str                # which agent produced it
```

`EvidenceKind` is a `str, Enum` — the same pattern already used for `Severity` and `Status` elsewhere in this project. The reason to tag data explicitly like this, rather than have a reader *guess* what kind of thing a string is (does it look like a DNS record? a header line?), is a classic problem. Say you were building a notes app and wanted to render sticky notes differently from to-do items:

```python
from enum import Enum

class NoteKind(str, Enum):
    STICKY = "sticky"
    TODO = "todo"

def render(note_kind: NoteKind, text: str) -> str:
    if note_kind == NoteKind.TODO:
        return f"[ ] {text}"
    return f"* {text}"
```

Without `note_kind`, `render` would have to inspect `text` itself and guess — fragile, and wrong the moment two kinds of note happen to look similar. Tagging the kind up front means the rendering code never has to guess; it just branches on the tag. That's exactly what `EvidenceItem.kind` buys the future evidence panel: a certificate and a DNS record can both be `text/plain` strings, but the UI will know to show one with a "cert" icon and the other with a "DNS" icon just from `kind`.

## Building one without repeating yourself: `BaseAgent.evidence()`

Every `EvidenceItem` needs the same two boring fields filled in — `collected_at` (right now, in UTC) and `agent` (this agent's own name). Rather than have every agent write that out by hand, `BaseAgent` gained one helper:

```python
def evidence(self, kind, label, content, content_type="text/plain") -> EvidenceItem:
    return EvidenceItem(
        kind=kind, label=label, content=content, content_type=content_type,
        collected_at=datetime.now(timezone.utc).isoformat(),
        agent=self.name,
    )
```

This only works as an *instance* method — it needs `self.name` to know which agent is calling it. `headers.py`'s `_check` helper used to be a `@staticmethod` (no `self` at all, callable straight off the class). To let it call `self.evidence(...)`, it became a normal instance method instead — one word removed (`@staticmethod`), one word added (`self` as the first parameter). Small change, but it's *why* that decorator had to go.

`BaseAgent.run()` also now stamps `finding.agent = self.name` on every finding right after `scan()` returns, in one place — so individual agents don't each need to remember to set it themselves, the same "give agents the guarantee for free" pattern `run()` already used for crash-proofing.

## Storing it: one more table

`evidence_items` is a new table (schema version 2, added the same way version 1 was — see note 19), one row per `EvidenceItem`, pointing back at the `findings` row it belongs to:

```sql
CREATE TABLE evidence_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id   INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    label        TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/plain',
    collected_at TEXT NOT NULL,
    agent        TEXT NOT NULL
);
```

`ON DELETE CASCADE` means deleting a scan deletes its findings, which deletes their evidence — no orphaned rows to clean up by hand.

## Try it

- Run a scan and check one finding: `report.findings[0].evidence_items` is a non-empty list for Headers findings, `[]` for the other four agents' findings — exactly what "proved on one agent first" means.
- `sqlite3 backend/data/sentinels.db ".schema evidence_items"` — see the new table.
- Fetch the same scan back with `GET /scans/{id}` and check the Headers findings still have their `evidence_items` — the round trip through the database, not just the in-memory object.
- Generate a PDF from a report with evidence attached — it looks identical to before, because `pdf.py` never reads `evidence_items`.

## Words worth knowing

- **`EvidenceKind`** — an enum tagging what *kind* of proof one evidence item is, so a reader doesn't have to guess from its content.
- **Additive field** — a new field with a default (`= Field(default_factory=list)`), so every existing caller that never mentions it keeps working unchanged.
- **`ON DELETE CASCADE`** — a foreign key option that auto-deletes child rows when their parent row is deleted.

---

**Next:** M5 — give the other four agents (Recon, TLS, Exposure, DNS) the same evidence treatment now that the shape is proven.
