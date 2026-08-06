# 20 — Read endpoints

> **Status:** done. `GET /scans`, `GET /scans/{id}`, and `DELETE /scans/{id}` all work — a finished scan can now be fetched back out of the database.

## What we built

M1 gave every scan a permanent home on disk. M2 opens the door back out:
three new routes let you list what's been saved, fetch any single scan by
its id, and delete one. The interesting part is `GET /scans/{id}` — the
data that went *in* as a nested Python object (a `ScanReport` containing
agents, each agent containing findings) had to come *back out* of three
flat tables and be reassembled.

## The one big idea: flat tables, nested objects

Databases store rows — one row per thing, no nesting. Your Python objects
are nested. The gap between the two is the thing this endpoint has to
bridge.

Here's the mismatch in miniature, with a recipe instead of a scan:

```python
# What you want in Python — nested
recipe = {
    "name": "pasta",
    "steps": [
        {"order": 1, "text": "boil water"},
        {"order": 2, "text": "add pasta"},
    ]
}

# What a database actually stores — flat rows, one per step
# steps table:
# recipe_name | order | text
# "pasta"     | 1     | "boil water"
# "pasta"     | 2     | "add pasta"
```

To go from the flat rows back to the nested dict, you group by `recipe_name`:

```python
steps_by_recipe = {}
for row in rows:
    steps_by_recipe.setdefault(row["recipe_name"], []).append(
        {"order": row["order"], "text": row["text"]}
    )
```

`setdefault(key, [])` either returns the existing list for that key or
creates an empty one — so you never have to check "does this key exist
yet?" before appending.

That's exactly what `get_scan` does in `storage/scans.py`: it reads all
`findings` rows for one scan, groups them into `findings_by_agent`, then
hands each group to its matching `AgentResult`. Three `SELECT` queries,
one grouping loop, one reassembled `ScanReport`.

## The actual code

```python
# storage/scans.py — the read path

def get_scan(scan_id: str) -> ScanReport | None:
    conn = get_connection()
    try:
        scan_row = conn.execute(
            "SELECT * FROM scans WHERE id = ?", (scan_id,)
        ).fetchone()
        if scan_row is None:
            return None                     # signals "not found" to the caller

        agent_rows = conn.execute(
            "SELECT * FROM agent_runs WHERE scan_id = ? ORDER BY id", (scan_id,)
        ).fetchall()

        finding_rows = conn.execute(
            "SELECT * FROM findings WHERE scan_id = ? ORDER BY id", (scan_id,)
        ).fetchall()

        findings_by_agent: dict[str, list[Finding]] = {}
        all_findings: list[Finding] = []
        for row in finding_rows:
            f = Finding(id=row["finding_key"], ...)   # build Pydantic model from row
            all_findings.append(f)
            findings_by_agent.setdefault(row["agent"], []).append(f)

        agents = [
            AgentResult(
                agent=ar["agent"],
                findings=findings_by_agent.get(ar["agent"], []),
                ...
            )
            for ar in agent_rows
        ]
        return ScanReport(counts=counts, findings=all_findings, agents=agents, ...)
    finally:
        conn.close()
```

The route in `main.py` just calls this and converts `None` to a 404:

```python
@app.get("/scans/{scan_id}", response_model=ScanReport)
def scans_get(scan_id: str) -> ScanReport:
    report = get_scan(scan_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
    return report
```

`DELETE /scans/{id}` is simpler: one `DELETE FROM scans WHERE id = ?`. The
`ON DELETE CASCADE` constraint in the schema means SQLite automatically
removes the matching rows in `agent_runs` and `findings` — no manual
cleanup needed.

## Try it

Start the server, then run a scan from `/docs` and copy the `id` from the
response. Then:

- `curl localhost:8000/scans` — lists that scan (and any others saved
  before it).
- `curl localhost:8000/scans/<paste-id-here>` — returns the full report.
  The content should match what `POST /scan` returned exactly.
- `curl -X DELETE localhost:8000/scans/<id>` then
  `curl localhost:8000/scans/<id>` — the second call should return a 404.

## Words worth knowing

- **`fetchone()` / `fetchall()`** — `fetchone()` returns one row or `None`;
  `fetchall()` returns a list of all matching rows (empty list if none).
- **`setdefault(key, default)`** — dict method that returns the value for
  `key` if it exists, or inserts `default` and returns it. Saves you writing
  an `if key not in d:` guard before every append.
- **`ON DELETE CASCADE`** — a database rule: when a parent row is deleted,
  all child rows that reference it are deleted automatically.

---

**Next:** M3 — agent registry. Agents declare their own metadata and a
`GET /agents` route serves it, so the frontend can stop hardcoding the list
of agent names.
