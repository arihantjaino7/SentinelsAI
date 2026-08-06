# 19 — SQLite storage and migrations

> **Status:** done. Every finished scan is saved to `backend/data/sentinels.db` and gets a real `id`.

## What we built

Until now, a scan lived only in memory — the moment the response left the
server, it was gone. Refreshing the frontend lost it. Now `POST /scan`
writes the finished report to a real file on disk (`backend/data/sentinels.db`)
before handing it back, and the response includes an `id` that names that
saved row. Nothing changed about how scanning itself works — this is purely
"remember what happened."

## The one big idea: talking to a database with plain Python

Python ships with a database built in — no install, no separate server
process, just a file. Here's the whole pattern in miniature, with a
notebook instead of a security scan:

```python
import sqlite3

conn = sqlite3.connect("notes.db")
conn.execute("CREATE TABLE IF NOT EXISTS notes (text TEXT)")
conn.execute("INSERT INTO notes (text) VALUES (?)", ("buy milk",))
conn.commit()

for row in conn.execute("SELECT text FROM notes"):
    print(row[0])   # "buy milk"
conn.close()
```

`connect()` opens (or creates) the file. `execute()` runs one SQL statement,
with `?` placeholders for values — never string-format your own SQL, that's
how SQL injection happens even in a project that itself refuses to send
attack traffic. `commit()` makes the writes permanent. `close()` releases
the file handle.

Two small choices carried into `backend/db.py`:

- **`conn.row_factory = sqlite3.Row`** — without it, a row comes back as a
  plain tuple (`row[0]`, `row[1]`, ...). With it, you can also do
  `row["url"]`, which is far easier to read than remembering column order.
- **One connection per call, not one shared connection.** `get_connection()`
  opens fresh and every caller closes it when done. SQLite connections
  aren't safe to hand between threads, and a web server can run different
  requests on different threads — so "open, use, close" avoids that trap
  entirely, at the cost of a tiny bit of overhead per call that doesn't
  matter here.

Also worth naming: `save_scan()` is a normal *blocking* function, called
with a plain `save_scan(report)` — no `await` — from inside `_finalize`,
which itself *is* `async def`. That's fine here: the write is small and
fast enough that it briefly pausing the event loop (see note 11 on
`asyncio.gather` for what the event loop is) isn't noticeable. If scans
ever got large enough for this to matter, the fix would be to run it in a
thread pool rather than making everything more complicated up front.

## The second idea: schema_version, so future changes don't need a framework

The database's shape (which tables, which columns) is called its **schema**.
Later milestones will add more tables — evidence, AI fix suggestions, a
chatbot's conversation history. Each of those needs to add columns or
tables to an *existing* database without deleting anyone's data.

The trick, without pulling in a migrations library: keep one tiny table,
`schema_version`, that just holds a single number. `backend/db.py` keeps a
list of `(version, sql)` pairs:

```python
MIGRATIONS = [
    (1, "CREATE TABLE scans (...); CREATE TABLE findings (...);"),
    # (2, "ALTER TABLE findings ADD COLUMN ...")   <- a future milestone adds this
]
```

`init_db()` reads the current number out of `schema_version`, then runs
every migration whose version is higher than that, in order, bumping the
number as it goes. Run it against a brand-new empty file and it plays every
migration from the start. Run it again against a database that's already
up to date and it does nothing. This runs once, automatically, every time
the server starts (`main.py` calls `init_db()` right after `load_dotenv()`).

## The actual code

```python
# backend/orchestrator.py — inside _finalize()
report = ScanReport(
    id=str(uuid.uuid4()),   # a random, effectively-unique string
    url=url,
    ...
)
save_scan(report)
return report
```

```python
# backend/storage/scans.py
def save_scan(report: ScanReport) -> None:
    conn = get_connection()
    try:
        conn.execute("INSERT INTO scans (id, url, score, ...) VALUES (?, ?, ?, ...)", (...))
        save_agent_results(conn, report.id, report.agents)   # writes agent_runs + findings
        conn.commit()
    finally:
        conn.close()
```

`save_agent_results` lives in its own file, `storage/findings.py`, mostly
because that's also where *reading* findings back out will live once the
frontend needs them (a near-future milestone) — keeping writes and reads
for the same tables in one place.

## Try it

- Run the server, then `POST /scan` (e.g. from `/docs`) against any URL —
  the JSON response now has a non-empty `"id"` field.
- Run a second scan, then look at both rows at once:
  ```bash
  cd backend && .venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('data/sentinels.db'); [print(dict(zip([d[0] for d in c.execute('SELECT * FROM scans').description], r))) for r in c.execute('SELECT * FROM scans')]"
  ```
- Delete `backend/data/sentinels.db` entirely and start the server again —
  it gets recreated from scratch, empty, with no errors.

## Words worth knowing

- **Schema** — the shape of a database: which tables exist, which columns
  each one has.
- **Migration** — a small, one-way step that changes the schema (add a
  table, add a column) without destroying existing data.
- **`sqlite3.Row`** — a row object you can index by column name (`row["url"]`)
  instead of just position (`row[0]`).
- **Blocking call** — code that makes the whole program (or, in `async`
  code, the whole event loop) wait for it, as opposed to `await`ing
  something that lets other work happen in the meantime.

---

**Next:** M2 — read endpoints (`GET /scans`, `GET /scans/{id}`), so a saved
scan can be fetched back out, not just written in.
