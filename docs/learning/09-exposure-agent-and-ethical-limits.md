# A9 — Exposure agent

> **Status:** done. `backend/agents/exposure.py` — `ExposureAgent` checks whether
> `/.env` or `/.git/HEAD` are publicly reachable.

## What we built

`ExposureAgent` checks two specific paths that should never be reachable on a
properly configured server:

- **`/.env`** — where frameworks keep local secrets (passwords, API keys). If it's
  sitting in the folder the web server serves from, anyone can just request it.
- **`/.git/HEAD`** — the front door of an exposed `.git` folder. If reachable, tools
  exist that rebuild a project's entire history from it.

Each is a single GET request. No guessing, no trying variations — just these two
well-known paths.

## The one big idea: a 200 doesn't always mean "found it"

A lot of real sites return `200 OK` for *every* URL, even ones that don't exist —
single-page apps and custom "not found" pages do this constantly. If the check were
just "did `/.env` return 200? Then it's exposed!", it would wrongly flag tons of
perfectly safe sites.

So the agent also checks whether the response actually *looks like* the thing it's
supposed to be:

```python
looks_real = (
    response.status_code == 200
    and "html" not in content_type
    and _ENV_LINE_RE.search(response.text)   # KEY=VALUE lines
)
```

A real `.env` file is plain-text `KEY=VALUE` lines, not an HTML page. A real
`.git/HEAD` file's content always starts with `ref:`. A fake "200 for everything"
page matches neither shape, so it correctly gets marked safe. Status code narrows
things down; content shape is what actually confirms it.

## Where the ethical line sits

CLAUDE.md says this project only does passive checks — reading things, never
attacking. For this agent that means: exactly two fixed, well-known paths, one GET
request each, and nothing that tries variations (`.env.bak`, `.env.local`, a
wordlist of 500 filenames). One GET to a standard path is what any browser does.
Hundreds of GETs guessing at hidden files is fuzzing — which this project has ruled
out entirely.

There's also a smaller rule buried in the code: if a `.env` really is exposed, the
finding never prints its actual content. It just says how many `KEY=VALUE` lines
were found. Otherwise our own report would become a second copy of the leaked
secret.

## The actual code

```python
async def _check_env_file(self, context: ScanContext) -> Finding:
    env_url = urljoin(context.url, "/.env")
    # follow_redirects=False: if the server redirects this path away,
    # that's the server telling us "not here" just as clearly as a 404.
    response = await context.client.get(env_url, follow_redirects=False)

    looks_real = (
        response.status_code == 200
        and "html" not in content_type
        and _ENV_LINE_RE.search(response.text)
    )
```

`_ENV_LINE_RE` is `re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", re.MULTILINE)`. The
`re.MULTILINE` flag matters: without it, `^` only matches the very start of the
whole string. With it, `^` matches the start of *every line*, which is needed since
a real `.env` has many `KEY=VALUE` lines and any of them should count.

The `/.git/HEAD` check works the same way, just checking `response.text.strip().startswith("ref:")` instead of the regex.

## Try it

Run a tiny server that returns 200 for literally everything (a fake "soft-404"
site):

```python
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html>nothing here</html>")

HTTPServer(("127.0.0.1", 8899), Handler).serve_forever()
```

- Run `ExposureAgent` against `http://127.0.0.1:8899/` and confirm it reports
  `PASS` for both checks, even though every request came back 200.
- Run it against a real clean site (`github.com`) and confirm the same.
- Check the full scan: `curl -X POST localhost:8000/scan -d "{\"url\": \"github.com\"}"` — four agents now in `"agents"`: `headers`, `recon`, `tls`, `exposure`.

## Words worth knowing

- **Soft-404** — a server that answers `200` for made-up paths too, the reason
  status code alone can't be trusted.
- **Content-shape check** — confirming a response actually looks like what you're
  checking for, not just trusting its status code.
- **`re.MULTILINE`** — makes `^`/`$` match every line in a string, not just the
  very start/end.

---

**Next:** A10 — DNS agent. Whether a domain's email can be spoofed — SPF and DMARC
records.
