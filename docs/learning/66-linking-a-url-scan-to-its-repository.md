# 66 — Linking a URL scan to its repository

> **Status:** done. A URL scan's missing-header findings can now get a real,
> deterministic fix — once you tell Sentinels which repository serves the site.

## What we built

Before this, a URL scan (just a website, no repo) could never get an automatic
fix for anything — including its four most common findings: missing
`Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`,
and `X-Frame-Options` headers. There was simply no file to write a patch to.

Now, on the Headers agent page, clicking "Check for automatic fix" on one of
those findings offers a small form: pick a GitHub account you've already
installed the Sentinels App on, type a repo name, click "Link repository."
Sentinels then reads that repo, figures out whether it's a Vercel or Next.js
project, and — if it is — writes the missing header straight into
`vercel.json` or `next.config.ts`, the same diff-preview-then-PR flow every
other fix already goes through.

## The one big idea: a finding with nowhere to point

Every earlier fixer worked off one simple rule: a `Finding` names a
`file_path`, and its `Fixer` is only ever allowed to touch that exact path.
That rule is a safety net — it stops a bug in one fixer from silently editing
some unrelated file.

A header finding breaks that assumption on purpose: it came from watching a
live HTTP response, not from reading a file, so `file_path` is `None`. There's
nothing to "match" against.

The fix was to give this one fixer its own small, named list of paths it's
allowed to touch — instead of loosening the rule for everyone:

```python
LINK_REPO_FIXER_PATHS: dict[str, frozenset[str]] = {
    "security-headers": frozenset(
        {"next.config.js", "next.config.ts", "next.config.mjs", "vercel.json"}
    ),
}
```

Think of it like a building with one general rule — "you may only enter the
room your keycard was issued for" — and one exception: the janitor's keycard
opens a specific, fixed set of utility closets instead. That's not a hole in
the security policy, it's a second, narrower policy that only applies to one
named badge. A random new fixer gets no such exception; only `"security-headers"`
is in the table, and only for those four exact filenames.

The alternative — a global "allow this fixer to modify things" boolean — would
have been much easier to write and much easier to get wrong later: flip it for
one fixer, and every future fixer that reuses the same flag inherits an
exception it never asked for. A small, explicit, per-slug table can't leak like
that.

## The actual code

Deciding *which* file to write to — `remediation/stack.py`:

```python
async def detect_stack(files: FileSource) -> StackResult | None:
    vercel = await files.get("vercel.json")
    if vercel is not None:
        return StackResult(kind=StackKind.VERCEL, path="vercel.json", existing=vercel)

    for candidate in NEXT_CONFIG_CANDIDATES:  # next.config.ts, .js, .mjs
        found = await files.get(candidate)
        if found is not None:
            return StackResult(kind=StackKind.NEXTJS, path=candidate, existing=found)

    return None  # unrecognized stack — decline, never guess
```

Vercel is checked first on purpose: if a site has both a `vercel.json` and a
`next.config.ts`, it's Vercel's edge network that actually controls the
response headers, regardless of framework.

Writing the fix — `remediation/headers_fix.py`'s `SecurityHeaderFixer` — is
honest about what it *won't* touch: for Next.js, if the config file already
defines its own `headers()` function, the fixer returns `None` instead of
trying to merge into code it can't safely parse:

```python
if "headers(" in content:
    return None  # already has its own headers() -- too risky to merge into
```

That's the same rule the whole project follows for uncertain findings: a
guess never gets dressed up as a fix.

## Try it

- Run a URL scan against any real site (`https://example.com` works — it has
  none of these headers). Open the Headers agent page and click "Check for
  automatic fix" on the CSP finding.
- Link it to a plain repo with no `vercel.json`/`next.config.*` (any repo you
  control works) — you should see "No automatic fix for this finding," not an
  error. That's `detect_stack` correctly saying "I don't recognize this."
- Click "Check for automatic fix" on a *different* header finding in the same
  scan — it reuses the link instead of asking again.
- Read `docs/PLAN-v5.md`'s "conflict #12" note for the full reasoning behind
  the allowlist table, written down before any of this code existed.

## Words worth knowing

- **Allowlist** — a small, explicit list of things that are permitted; anything
  not on it is refused by default. The opposite of a blocklist (list what's
  forbidden, allow everything else).
- **`frozenset`** — an immutable set. Used here because this table is meant to
  be read, never mutated at runtime.
- **Stack detection** — figuring out what framework/platform serves a site by
  looking for the files it leaves behind (`vercel.json`, `next.config.ts`),
  rather than being told directly.

---

**Next:** nothing queued yet — Stage D covers Vercel and Next.js only;
`netlify.toml` and `nginx.conf` are deferred to a later stage if it's picked up.
