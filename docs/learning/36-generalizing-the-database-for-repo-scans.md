# 36 — Making room in the database for repo scans (R3)

> **Status:** done. `scans` and `findings` gained new columns, a new
> `repo_files` table was added, and every existing URL scan was proven to
> still round-trip byte-for-byte through `GET /scans/{id}`.

## What we built

Repo scans need a couple of things URL scans never did: a way to say "this
report is about a repo, not a website" (`target_type`), and a way to say
"this finding came from line 47 of `config.py`" (`file_path` / `line`). Both
were added as **new, optional columns** — nothing that already existed had to
change shape.

## The one big idea: adding a column is safe; changing one isn't

`ALTER TABLE ... ADD COLUMN ... DEFAULT 'url'` is a different, much safer
move than editing an existing column. A tiny standalone example — imagine a
spreadsheet of students instead of a database:

```python
students = [{"name": "Priya"}, {"name": "Sam"}]

# Adding a new column with a default: every existing row is still valid,
# nothing reads it differently than before.
for s in students:
    s.setdefault("grade_level", "unknown")

print(students)
# [{'name': 'Priya', 'grade_level': 'unknown'}, {'name': 'Sam', 'grade_level': 'unknown'}]
```

Every row that existed before still has a sensible value for the new column
— nobody has to go back and guess what `grade_level` should have been.
That's exactly what `_V6_SCHEMA` does:

```sql
ALTER TABLE scans ADD COLUMN target_type TEXT NOT NULL DEFAULT 'url';
ALTER TABLE findings ADD COLUMN file_path TEXT;
ALTER TABLE findings ADD COLUMN line INTEGER;
```

Every scan taken *before* this migration reads back with `target_type = 'url'`
automatically — which is simply true, since every one of them really was a
URL scan. `file_path`/`line` have no `DEFAULT`, so old findings just get
`NULL`, which `Finding.file_path: Optional[str] = None` reads back as `None`.

## The second small idea: `Literal` instead of a bare `str`

`target_type` isn't *any* string — it's always `"url"` or `"repo"`, nothing
else. `Literal` says so directly in the type:

```python
from typing import Literal

def set_status(status: Literal["on", "off"]) -> None:
    print(status)

set_status("on")     # fine
set_status("maybe")  # a type checker flags this immediately — "maybe" isn't allowed
```

`ScanReport.target_type: Literal["url", "repo"] = "url"` gets the same
guarantee `Severity` and `Status` already have as enums, just for a field
with only two valid values — a typo like `"repo "` (trailing space) becomes a
caught mistake instead of a silent bug three files later.

## Proving nothing broke: the round-trip test

Adding fields is only *actually* safe if it's true, not just probably true.
So a real scan (`wordpress.org`, 12 findings) was fetched via
`GET /scans/{id}` **twice** — once with the old code (temporarily set aside
with `git stash`), once with the new code — and every field of both
responses was compared. The only differences allowed to survive: `target_type`
appearing (`"url"`), and `file_path` / `line` appearing (`null`) on every
finding. Every score, grade, evidence item, and checklist entry matched
exactly.

## Try it

```bash
cd backend && .venv/Scripts/python.exe -c "
import sqlite3
conn = sqlite3.connect('data/sentinels.db')
print(conn.execute(\"SELECT sql FROM sqlite_master WHERE name='scans'\").fetchone()[0])
"
```

- Look for `target_type TEXT NOT NULL DEFAULT 'url'` in the output.
- `curl localhost:8000/scans/<any old scan id>` — `target_type` shows up as
  `"url"` even for a scan taken before this migration ever existed.
- Try constructing `ScanReport(target_type="repo", ...)` for something that
  was never a repo scan — nothing stops you at runtime (Pydantic checks the
  *shape*, not truthfulness) but a linter/type-checker would flag
  `target_type="website"` as invalid immediately.

## Words worth knowing

- **`ALTER TABLE ... ADD COLUMN`** — extends an existing table without
  touching any row already in it.
- **`Literal`** — a type hint restricting a value to an exact, fixed set of
  options, rather than any string/int.
- **Additive change** — a change only new callers can even notice, because
  every old caller's behavior is unaffected.
- **Round-trip test** — save data, read it back, and diff the two to prove a
  change didn't silently alter anything it wasn't supposed to.
