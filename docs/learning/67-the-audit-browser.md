# 67 — The audit browser

> **Status:** done. `/audit` shows every plan, pull request, and verification Sentinels
> has ever recorded — the first time any of that history has been read back by anything
> other than a raw SQL query.

## What we built

Since Stage B, every time Sentinels opened a pull request, merged one, or verified a
fix, it quietly wrote one row into a database table called `audit_log`. Nothing ever
read those rows back — the only way to see them was to open the database by hand. This
step adds two backend endpoints and one frontend page that finally show that history:
`GET /audit` (everything this account has ever done, newest first) and
`GET /scans/{id}/audit` (just one scan's own trail), both landing on a single `/audit`
page.

## The one big idea: LEFT JOIN

The account-wide view needs to show, for each audit row, which scan it belonged to —
its URL, so the list is actually readable instead of a wall of ids. That data lives in
a different table (`scans`), so we need to combine two tables in one query. That's what
`JOIN` does in SQL.

A plain `JOIN` only keeps rows that match on *both* sides. But a scan can be deleted,
and when that happens the audit row's `scan_id` gets set to `NULL` (a database rule
already in place: `ON DELETE SET NULL`) rather than deleting the audit row too — the
history should survive even if its subject doesn't. A plain `JOIN` would silently drop
that now-orphaned row from the results, because `NULL` never matches anything.
`LEFT JOIN` keeps every row from the left-hand table regardless, filling in `NULL` for
any columns that had no match:

```sql
-- Two tiny tables: books, and reviews that point at a book
-- reviews.book_id can be NULL ("this book was removed")

SELECT reviews.text, books.title
FROM reviews
LEFT JOIN books ON books.id = reviews.book_id;
-- every review shows up, even the one with no book —
-- its "title" column just comes back NULL
```

Our real query does the same thing, with `audit_log` as the left-hand table:

```python
conn.execute(
    """
    SELECT audit_log.*, scans.url AS scan_url, scans.target_type AS scan_target_type
    FROM audit_log
    LEFT JOIN scans ON scans.id = audit_log.scan_id
    WHERE audit_log.user_id = ?
    ORDER BY audit_log.id DESC
    LIMIT ?
    """,
    (user_id, limit),
)
```

## The other new idea: a page driven by the URL

`/audit` and `/scan/abc123`'s new "Audit" link both point at the same page, but the
per-scan one adds `?scan=abc123` to the end. That's a **query parameter** — extra
information tacked onto a URL after a `?`, that the page can read to change what it
shows without needing a whole separate page for "audit, but for one scan."

React's `useSearchParams()` hook reads it:

```tsx
const params = useSearchParams();
const scanId = params.get("scan"); // "abc123", or null if there's no ?scan=...
```

If `scanId` is set, the page calls `fetchScanAudit(scanId)` instead of the account-wide
`fetchAudit()`. Next.js requires any component that calls `useSearchParams()` to sit
inside a `<Suspense>` boundary — a wrapper that says "this part might not be ready
immediately, show a fallback until it is" — which is why `AuditPage` below is just a
thin shell around the real component.

## The actual code

Two backend routes, in `backend/main.py`:

```python
@app.get("/audit", response_model=list[AuditLogEntry])
def audit_list(limit: int = 100, user: User = Depends(current_user)) -> list[AuditLogEntry]:
    return [AuditLogEntry(**row) for row in list_audit_for_user(user.id, limit=limit)]


@app.get("/scans/{scan_id}/audit", response_model=list[AuditLogEntry])
def scan_audit(scan_id: str, user: User = Depends(current_user)) -> list[AuditLogEntry]:
    ...
    owner = scan_owner(scan_id)
    if owner is not None and owner != user.id:
        raise HTTPException(status_code=403, detail="This scan belongs to another user.")
    return [AuditLogEntry(**row) for row in list_audit(scan_id)]
```

The second one is stricter than most routes in this project: reading a scan's fix
history is refused outright if it isn't yours, even for old scans nobody owns. Who-did-
what is exactly the kind of thing that shouldn't leak between accounts.

The frontend page picks its data source based on the URL, and the nav bar on both
`/settings` and every per-scan page now links to `/audit`, so there are two ways in.

## Try it

- Sign in, open `/audit` — you'll see every fix Sentinels has ever planned, opened, or
  verified for your account, newest first.
- Open any scan that's had a fix applied, click "Audit" in its nav bar — same page,
  now scoped to just that scan (look at the URL: `?scan=...` got added).
- From the scoped view, click "view all activity" — same page again, this time with
  the `?scan=` removed, back to the account-wide list.

## Words worth knowing

- **LEFT JOIN** — combine two tables, keeping every row from the left one even when
  nothing matches on the right (unlike a plain `JOIN`, which drops unmatched rows).
- **Query parameter** — extra data appended to a URL after `?`, e.g. `?scan=abc123`,
  readable by the page without needing a separate route.
- **`useSearchParams()`** — the React hook that reads those query parameters.
- **`<Suspense>`** — a wrapper telling React "this might not be ready yet, show a
  fallback until it is," required around anything using `useSearchParams()`.

---

**Next:** nothing queued yet — Stage E was the last stage PLAN-v5 had scoped. The
deferred items (a dependency-version fixer, a secret-removal fixer, more header-fixer
stacks) each need their own scoping pass before they become a stage.
