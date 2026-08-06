# A7 — Recon agent

> **Status:** done. `backend/agents/recon.py` — `ReconAgent`, the second real agent,
> now runs alongside `HeadersAgent` in every scan.

## What we built

`ReconAgent` runs two passive checks:

- **Generator meta tag** — parses the homepage's HTML looking for
  `<meta name="generator" content="...">`, a tag many CMSes (WordPress, Drupal, Wix)
  add automatically that announces exactly what software and version built the page.
- **`robots.txt`** — fetches `/robots.txt` and checks its disallowed paths against a
  short list of sensitive-sounding keywords (`admin`, `login`, `config`, `.env`, etc.).

Both are just a single GET to a public path — nothing here guesses or brute-forces
anything. Tested against real sites: `wordpress.org` reveals its generator tag,
`github.com`'s `robots.txt` hints at a sensitive path, `example.com` has neither.

## The one big idea: parsing HTML with BeautifulSoup

A web page's HTML is just text. You *could* search it with plain string matching, but
that breaks the moment whitespace or attribute order is slightly different.
**BeautifulSoup** parses the text into a tree of tags you can query properly, the same
way a browser understands the page's structure.

```python
from bs4 import BeautifulSoup

html = '<html><body><meta name="author" content="Sam"></body></html>'
soup = BeautifulSoup(html, "html.parser")

tag = soup.find("meta", attrs={"name": "author"})
print(tag.get("content"))   # 'Sam'
```

- `"html.parser"` tells BeautifulSoup which engine to use — it's the one built into
  Python, so no extra install is needed.
- `.find(...)` returns the first match (or `None`); `.find_all(...)` returns every
  match as a list. Our generator check uses `.find` since a page only ever has one.

Our actual check:

```python
soup = BeautifulSoup(response.text, "html.parser")
tag = soup.find("meta", attrs={"name": "generator"})
content = tag.get("content") if tag else None
```

Using `.get("content")` instead of `tag["content"]` matters: if the tag exists but is
missing that attribute, `.get(...)` quietly returns `None` instead of crashing.

## robots.txt, briefly

`robots.txt` is a plain-text file telling web crawlers which paths they're asked not
to index — a polite request, not a lock. The reason a security auditor checks it: a
human wrote that file, and humans tend to list the paths they consider most sensitive,
which is a free hint about where something interesting probably lives.

```
User-agent: *
Disallow: /admin
Disallow:
```

A bare `Disallow:` with nothing after it means "nothing else is disallowed" — our
code filters those empty entries out. One real wrinkle found while testing against
`github.com`: its `robots.txt` repeats the same path under several different
`User-agent:` blocks, so the check printed it four times over until a one-line fix —
`list(dict.fromkeys(disallowed))` — deduped it while keeping the original order.

## The actual code

```python
async def scan(self, context: ScanContext) -> list[Finding]:
    return [
        await self._check_generator(context),
        await self._check_robots_txt(context),
    ]
```

Two independent checks against two different URLs — the homepage, and
`/robots.txt`. To always hit the real root of the domain (even if the scanned URL was
some deep page), we build the robots.txt URL with `urljoin`:

```python
from urllib.parse import urljoin
robots_url = urljoin(context.url, "/robots.txt")
# urljoin("https://example.com/blog/post", "/robots.txt")
#   -> "https://example.com/robots.txt"   (leading "/" means "from the root")
```

Plain string concatenation would have produced a broken URL like
`https://example.com/blog/post/robots.txt` instead.

A missing `robots.txt` (usually a 404) is reported as `PASS`, not a problem — plenty
of well-run sites just don't have one.

## Try it

```bash
cd backend
./.venv/Scripts/python.exe -c "
import asyncio, httpx
from agents.base import ScanContext
from agents.recon import ReconAgent

async def main():
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in ['https://example.com', 'https://github.com', 'https://wordpress.org']:
            ctx = ScanContext(url=url, client=client)
            result = await ReconAgent().run(ctx)
            print(url, [(f.status.value, f.title) for f in result.findings])

asyncio.run(main())
"
```

- Notice only `wordpress.org` trips the generator-tag check.
- Look at a real `robots.txt` yourself first: `curl -s https://github.com/robots.txt | grep -i disallow`.
- With the server running, POST to `/scan` with `wordpress.org` and check the response
  now has two agents (`headers` and `recon`) combined into one report.

## A couple of words worth knowing

- **BeautifulSoup** — parses HTML text into a queryable tree instead of raw strings.
- **`.find()` vs `.find_all()`** — first match only, vs. every match as a list.
- **`robots.txt`** — a request to crawlers, not an enforcement mechanism; visible to anyone.
- **`urljoin`** — resolves a path against a base URL the way a browser does.
- **`dict.fromkeys(items)`** — dedupes a list while keeping the original order.

---

**Next:** A8 — TLS agent. Reading a real certificate's expiry date using raw sockets
and Python's `ssl` module.
