# 40 — The Code Patterns agent

> **Status:** done. `backend/agents/repo/patterns.py` flags 9 risky-looking
> code constructs across a repo, verified against both a "dirty" and a
> deliberately tricky "clean" fixture.

## What we built

A new repo agent, `PatternsAgent`, that scans every file for constructs that
are *often* a security problem: `eval()`/`exec()`, `subprocess` with
`shell=True`, SQL glued together with string concatenation, React's
`dangerouslySetInnerHTML`, `verify=False`, `DEBUG=True`, a wildcard CORS
origin, and `pickle.loads`. Same regex-over-text approach as R6's Config
agent — no real parser, since the input is untrusted repo content and these
patterns don't need one.

## The one big idea: a hint is not proof

Every finding this agent produces comes back as `Status.WARN`, never `FAIL`
— on purpose, and unlike every earlier agent. `eval()` genuinely is
dangerous when fed user input, but plenty of legitimate code calls it on a
trusted, hardcoded string. The agent can see the shape of the code, not what
data actually reaches it at runtime — so finding one of these patterns means
"worth a human look," not "confirmed vulnerability." That's exactly the gap
between a `FAIL` (something Sentinels directly verified, like a live exposed
`.env`) and the checklist's "inferred" tier this agent's findings are meant
to live in.

## The second idea: deciding by shape, with two conditions at once

The SQL check doesn't understand SQL — it just looks for a keyword
(`SELECT`/`INSERT`/...) sharing a line with either an f-string `{...}` or a
`+` next to a quoted string. Both conditions have to line up:

```python
def is_suspicious(line):
    has_number = any(c.isdigit() for c in line)
    has_dollar_sign = "$" in line
    return has_number and has_dollar_sign

print(is_suspicious("cost is $12"))   # True  -- both conditions met
print(is_suspicious("cost is high"))  # False -- no number, no match
```

`_looks_like_sql_concat` is that same pattern, just with two more specific
conditions:

```python
def _looks_like_sql_concat(line: str) -> bool:
    if not _SQL_KEYWORD_RE.search(line):
        return False
    has_fstring_interpolation = bool(re.search(r'f["\']', line)) and "{" in line
    has_string_concat = "+" in line and bool(re.search(r'["\']', line))
    return has_fstring_interpolation or has_string_concat
```

A parameterized query like `cursor.execute("...WHERE id = %s", (id,))` has
the SQL keyword but neither an f-string brace nor a `+` next to a quote — so
it correctly passes through untouched.

## Try it

```bash
cd backend && .venv/Scripts/python.exe -c "
from agents.repo.patterns import _looks_like_sql_concat
print(_looks_like_sql_concat('q = \"SELECT * FROM users\" + user_id'))   # True
print(_looks_like_sql_concat('cursor.execute(\"SELECT * FROM t WHERE id=%s\", (x,))'))  # False
"
```

- Write a file with `def evaluate(x): return x + 1` — no finding, since
  `\beval\s*\(` requires `eval` to be followed directly by `(`, not `uate(`.
- Add `subprocess.run(cmd, shell=False)` — no finding; only `shell=True`
  matches.
- Add `allow_origins=["https://example.com"]` next to `allow_origins=["*"]`
  — only the second one is flagged.

## Words worth knowing

- **Inferred finding** — a weak passive signal worth flagging, but not
  something Sentinels directly confirmed is exploitable.
- **Heuristic** — a rule that's usually right and cheap to check, as
  opposed to one that's provably always correct.

## Verification

A "dirty" fixture with one deliberate instance of all 9 patterns produced
exactly one `WARN` finding per pattern (SQL concat fired twice — once for
each style). A "clean" fixture deliberately used *near-miss* names —
`evaluate()`, `shell=False`, a parameterized query, `DEBUG = False`,
`json.loads` instead of `pickle.loads` — and produced zero findings,
confirming the checks aren't dumb substring matches.

---

**Next:** R8 — extending the Repo Hygiene agent with lockfile/tests/CI/
`.env.example`/large-binary checks.
