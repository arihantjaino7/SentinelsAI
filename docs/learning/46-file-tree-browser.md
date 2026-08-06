# 46 — File-tree browser

> **Status:** done, 2026-08-05. R12, the last milestone in `docs/PLAN-v3.md`.
> Verified live: a fresh repo scan of `MahatvaGoell/Sentinels` (138 files)
> produced a `repo_files` row per file, and every finding's `file_path`
> reconciled exactly against the tree's `finding_count` — `backend/agents/repo/patterns.py`
> showed 19 both in the raw findings list and in the tree badge. Clicking it in
> a real browser rendered all 19 with evidence, remediation, and "Fix with
> AI" — the same `FindingRow` every other page already uses, unchanged.
> URL scans confirmed to show no Files tab at all.

## What we built

`GET /scans/{id}/files` on the backend, and `/scan/[scanId]/files` on the
frontend — a collapsible tree of every file a repo scan walked, each folder
and file badged with how many findings live under it. Click a file, see its
findings. The nav bar's Files tab only appears for repo scans.

The interesting part wasn't the tree — it was that `docs/PLAN-v3.md` already
designed a `repo_files` SQL table for this back in R3, and nothing had ever
written to it. R12 turned out to be two jobs: teach the repo scan pipeline to
actually populate that table, *then* build the browser that reads it.

## New concepts

### 1. Recursive components, and why each one gets its own memory

A React component can render itself. `TreeNode` (a folder or a file) renders
a list of `TreeNode`s for its children — the same component, over and over,
one level deeper each time. What makes this actually work is that every
*call* to a component — every place it appears in the tree — gets its own
private `useState`, completely independent of every other call, even though
they're all running the exact same function.

Standalone example — a nested comment thread, nothing to do with files:

```jsx
function Comment({ text, replies }) {
  const [expanded, setExpanded] = React.useState(true);
  return (
    <div style={{ marginLeft: 16 }}>
      <button onClick={() => setExpanded(!expanded)}>{text}</button>
      {expanded && replies.map((r, i) => <Comment key={i} {...r} />)}
    </div>
  );
}
```

Collapse the first comment and every reply underneath it hides — but a
sibling comment three levels away keeps its own `expanded` state exactly as
it was. React tracks each hook call by *where the component sits in the
tree*, not by the function's source code, so a hundred `Comment`s sharing one
function definition still behave like a hundred separate switches. That's
`FileTreeView.tsx`'s `TreeNode`: expanding `backend/` doesn't touch whatever
you did inside `frontend/` a moment ago.

### 2. Turning a flat list of paths into a tree

`GET /scans/{id}/files` returns a flat array — `[{path: "backend/main.py",
...}, {path: "backend/db.py", ...}, ...]`. Nothing about that shape is a
tree. `frontend/lib/fileTree.ts` builds one by walking each path's
`/`-separated segments and reusing whatever node already exists for a shared
prefix, creating a new one only the first time a segment is seen.

Standalone example — the exact same trick, building a shop's category menu
from a list of breadcrumb strings instead of file paths:

```js
function buildMenu(breadcrumbs) {
  const root = { name: "root", children: [] };
  for (const path of breadcrumbs) {
    let node = root;
    for (const part of path.split("/")) {
      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, children: [] };
        node.children.push(child);
      }
      node = child;
    }
  }
  return root;
}

buildMenu(["Electronics/Phones", "Electronics/Laptops", "Garden/Tools"]);
// root -> Electronics -> {Phones, Laptops}, Garden -> Tools
// "Electronics" is built once and reused by both Phones and Laptops,
// even though it appears at the start of two different input strings.
```

`buildFileTree` is that function with one addition: after the walk, a second
pass (`sortAndRollUp`) visits every node once more, bottom-up, summing each
directory's `finding_count` from its children. A folder's badge is never
computed by re-scanning the flat list — it's just "add up what my children
already know," which is also why it can never drift out of sync with them.

### 3. `useMemo` — skip work that didn't need to happen again

Every state change in a React component re-runs the whole function, which
would mean rebuilding the entire file tree from scratch on every click if
nothing stopped it. `useMemo` caches a computed value and only recomputes it
when the values it depends on actually change.

```jsx
function ExpensiveList({ items, filter }) {
  // Without useMemo, sorting 10,000 items would rerun on every keystroke
  // anywhere else on the page, even changes that have nothing to do with
  // `items` or `filter`.
  const sorted = React.useMemo(
    () => [...items].sort().filter((i) => i.includes(filter)),
    [items, filter],
  );
  return sorted.join(", ");
}
```

`files/page.tsx` wraps `buildFileTree(files)` in `useMemo([files])` — clicking
a file to select it changes `selectedPath`, not `files`, so the tree isn't
rebuilt just to show a different finding list next to it.

## The actual code

**Backend — the table finally gets written to.** `repo_orchestrator.py`'s
`_finalize` already had every finding by the time R12 touched it; the only
new work is counting them per file and handing that to `save_scan`:

```python
counts_by_path: dict[str, int] = {}
for finding in findings:
    if finding.file_path:
        counts_by_path[finding.file_path] = counts_by_path.get(finding.file_path, 0) + 1

file_entries = [
    RepoFileEntry(
        path=rf.path,
        size=rf.size,
        language=_guess_language(rf.path),
        finding_count=counts_by_path.get(rf.path, 0),
    )
    for rf in repo_files
]
save_scan(report, repo_files=file_entries)
```

Counting from the *same* `findings` list that built the report — not a
separate database query afterward — is what guarantees the tree's badges and
the agent pages' issue counts can never disagree: they're two views onto one
list, counted once.

`save_scan(report, repo_files=None)` — the new parameter defaults to `None`
and only `repo_orchestrator.py` ever passes something else, so `orchestrator.py`
(the URL side) calls `save_scan(report)` exactly as it always has. Same shape
as R3's `target_type` column: additive, invisible to the caller that doesn't
know it exists.

**Backend — the read side.** `storage/repo_files.py` is deliberately its own
module rather than folded into `storage/scans.py`'s `get_scan` — the whole
point of R3's separate `repo_files` table was that the tree shouldn't need to
load a full `ScanReport` just to answer "what files were there." `GET
/scans/{scan_id}/files` in `main.py` still 404s through `get_scan` first (so
a nonexistent scan behaves identically to every other endpoint), then reads
`repo_files` directly.

**Frontend — the nav bar's gap.** `layout.tsx` had never fetched anything
before this — it only read the URL. Showing the Files tab *only* for repo
scans meant it needed to know `target_type`, which lives on the full
`ScanReport`, so it now calls `fetchScan(scanId)` once for that one field —
the same fetch every child page already makes independently for its own
reasons. One extra request per page load, consistent with how this codebase
already works everywhere else rather than introducing the first shared cache.

## Try it

- Scan a real GitHub repo at `/repo`, then open its `/files` tab — folders
  start expanded; click one to collapse it, click a badged file to see its
  findings appear on the right.
- Scan a plain website at `/url` afterward and confirm no Files tab appears
  in the nav at all — `target_type !== "repo"` is the only thing gating it.
- In `components/files/FileTreeView.tsx`, change `useState(true)` to
  `useState(false)` in `TreeNode` and reload — every folder now starts
  collapsed, proving that one line controls the tree's default, not some
  hidden per-node config.

## Words worth knowing

- **Recursive component** — a component that renders another instance of
  itself, directly or through its children; what makes an arbitrarily deep
  tree renderable with one component definition instead of one per level.
- **Hook identity by position** — React keeps each `useState` call's memory
  tied to where that component sits in the render tree, not to the function
  body — which is why a hundred identical `TreeNode`s don't share state.
- **Bottom-up aggregation** — computing a parent's value by summing its
  children's already-known values, rather than recomputing from the original
  raw data every time.
- **Memoization** — caching a computed result and only recomputing it when
  its actual inputs change (`useMemo`'s dependency array).

---

**This closes `docs/PLAN-v3.md`.** All twelve milestones (R1–R12) are done.
The plan's own end-to-end checklist (its final section) is the remaining
acceptance pass across the whole v3 feature, not a new milestone.
