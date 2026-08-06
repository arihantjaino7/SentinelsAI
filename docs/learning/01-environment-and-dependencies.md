# A1 — Environment up

> **Status:** done. `backend/.venv/` exists with 27 packages installed, all imports verified.

## 1. What we built

We gave the backend its own private Python installation — a *virtual environment* —
and installed the 8 libraries listed in `requirements.txt` into it. Nothing was
installed into your system Python, so this project can't break your other projects and
they can't break it. We also added a `.gitignore` so those installed packages never get
committed to git.

No application code yet. This is the foundation everything else stands on.

---

## 2. New concepts

### Concept: the virtual environment

Python installs packages into one shared folder by default. That's fine until two
projects disagree about a version.

Standalone example of the problem — imagine two folders on your machine:

```
project-a/   needs  requests==2.20   (old, written 2019)
project-b/   needs  requests==2.32   (new, written 2026)
```

With one shared Python, installing `requests` for project-b **overwrites** the version
project-a depends on. Project-a silently breaks. There is no version of "install both"
that works — there's one folder, one `requests`.

A virtual environment is just **a folder containing its own copy of Python and its own
`site-packages`**. Each project gets one. They can't see each other.

```bash
python -m venv .venv          # creates the folder
```

That's genuinely all it is — a directory. Look inside ours:

```
backend/.venv/
  Scripts/python.exe      <- a Python that looks in ITS OWN site-packages
  Lib/site-packages/      <- our 27 packages live here, nowhere else
```

The important consequence: **which `python.exe` you run decides which packages exist.**

```bash
python -c "import fastapi"                    # system Python -> ModuleNotFoundError
./.venv/Scripts/python.exe -c "import fastapi" # venv Python   -> works
```

This is the #1 source of "but I installed it!" confusion. You didn't install it *for
that Python*.

> **Why `.venv` and not `venv`?** The leading dot is convention for "tooling, not
> source code" — editors and file listings sort it out of the way, and VS Code
> auto-detects a folder named `.venv` as the project interpreter.

### Concept: `python -m pip` instead of `pip`

We ran `./.venv/Scripts/python.exe -m pip install ...`, not `pip install ...`.

`-m` means "run this module as a script, using **this specific** Python."

Standalone example of why it matters:

```bash
pip install requests                # WHICH pip? whichever the PATH found first
python -m pip install requests      # unambiguous: THIS python's pip, this python's packages
```

Remember `where python` earlier returned **three** different Pythons on your machine:

```
C:\Users\Ariha\AppData\Local\Programs\Python\Python313\python.exe
Y:\python.exe
C:\Users\Ariha\AppData\Local\Microsoft\WindowsApps\python.exe
```

With three Pythons installed, a bare `pip` is a coin flip. `python -m pip` never is.
Make it a habit.

### Concept: pinning versions with `==`

Our `requirements.txt` uses exact versions:

```
fastapi==0.115.6
```

The three options, and what each means:

```
fastapi              # any version — whatever is newest the day you install
fastapi>=0.115.6     # at least this, but newer is fine
fastapi==0.115.6     # exactly this. nothing else.
```

Standalone example of why unpinned hurts: you build and demo your project in July on
`fastapi 0.115`. In September, FastAPI 0.120 ships with a renamed function. A judge or
teammate clones your repo, runs `pip install -r requirements.txt`, gets 0.120, and the
app crashes on import — **on code you never touched**. You can't reproduce it, because
your machine still has July's version.

Pinning trades "automatic updates" for "it runs the same everywhere, forever." For a
project you'll demo, that trade is obviously correct.

### Concept: transitive dependencies

You listed **8** packages. Pip installed **27**. The other 19 are dependencies *of your
dependencies*.

Standalone example of the shape:

```
you asked for:  fastapi
fastapi needs:  starlette, pydantic
starlette needs: anyio
anyio needs:    sniffio, idna
```

Ask for one thing, get a tree. A few from our install worth recognizing when they show
up in error messages later:

| Package | Arrived because of | What it does |
|---|---|---|
| `starlette` | fastapi | The actual web machinery — FastAPI is a layer on top |
| `pydantic-core` | pydantic | Pydantic's validation engine, written in Rust for speed |
| `anyio` / `sniffio` | fastapi, httpx | Async plumbing shared between libraries |
| `h11` / `httpcore` | httpx | The raw HTTP protocol implementation |
| `certifi` | httpx | The list of trusted certificate authorities — we'll meet this again in the TLS agent (A8) |
| `soupsieve` | beautifulsoup4 | CSS selector support for HTML parsing |

You never import these directly. But when a traceback mentions `h11`, now you know it
came from httpx, not from nowhere.

### Concept: why `.venv/` must never be committed

Our `.gitignore` includes `.venv/`. Two reasons:

1. **Size** — those 27 packages are tens of thousands of files. Git would crawl.
2. **They aren't portable** — `.venv` contains compiled binaries built for *your*
   Windows machine and *your* Python 3.13. On someone's Mac, they're useless.

`requirements.txt` is the portable thing. It's a *recipe*, not the meal:

```
requirements.txt   9 lines, works everywhere   -> COMMIT THIS
.venv/             ~30,000 files, Windows-only -> IGNORE THIS
```

Anyone can rebuild `.venv` from the recipe in 60 seconds. That's the whole point.

While we're here — the same file also ignores `.env` but **not** `.env.example`:

```
.env           real secrets (your actual API key)  -> IGNORED, never committed
.env.example   the template (ANTHROPIC_API_KEY=)   -> committed, shows what's needed
```

Committing a real `.env` is one of the most common ways API keys leak publicly. The
`.gitignore` line is what prevents it.

---

## 3. The actual commands, walked through

```bash
cd backend
python -m venv .venv
```
Creates `backend/.venv/`. Uses your system Python once — the last time we'll do that.

```bash
./.venv/Scripts/python.exe -m pip install --upgrade pip --quiet
```
Upgrades pip *inside* the venv first. The bundled pip is often outdated, and an old pip
sometimes can't read newer package formats. Cheap insurance.

> **Windows note:** it's `.venv/Scripts/` here. On Mac/Linux it's `.venv/bin/`. If you
> ever follow a tutorial that says `bin` and it doesn't exist, that's why.

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```
`-r` = "read the list from this file." Pip resolves the whole dependency tree, then
downloads and installs all 27.

Then the verification — the part that actually proves A1 is done:

```python
import fastapi, httpx, dns.resolver, bs4, anthropic, pydantic

from models import Finding, Severity, Status
f = Finding(id='missing-hsts', title='HSTS header not set', category='Headers',
            severity=Severity.HIGH, status=Status.FAIL)
```

Two things checked at once. The imports prove the packages are installed *and reachable
from this Python*. Building a real `Finding` proves `models.py` — written before you and
I started — actually works against the installed Pydantic version.

Note `import dns.resolver`, not `import dnspython`. **The install name and the import
name are different.** This is common and catches everyone:

```
pip install dnspython        ->  import dns
pip install beautifulsoup4   ->  import bs4
pip install python-dotenv    ->  import dotenv
```

The output confirmed the scoring constant wired up correctly too:

```
models.py works -> HSTS header not set | High | penalty 15
```

That `15` came from `SEVERITY_PENALTY[Severity.HIGH]` in `models.py` — the same
deduction table you'll see in the score in A6.

---

## 4. Try this

**See the isolation for yourself.** Run both and compare:

```bash
python -c "import fastapi; print('found it')"
```

That should **fail** with `ModuleNotFoundError` — your system Python has no fastapi.
Then:

```bash
cd backend && ./.venv/Scripts/python.exe -c "import fastapi; print('found it')"
```

That works. Same machine, same command, different Python. That contrast *is* the concept.

**Count what actually got installed:**

```bash
cd backend && ./.venv/Scripts/python.exe -m pip list
```

27 entries from 8 requested. Find `starlette` in the list — you never asked for it;
FastAPI did.

**See the dependency tree for one package:**

```bash
cd backend && ./.venv/Scripts/python.exe -m pip show fastapi
```

The `Requires:` line names its direct dependencies. The `Required-by:` line is empty —
nothing depends on fastapi, because fastapi is what *we* wanted.

---

## 5. Words you now know

- **Virtual environment (venv)** — a folder holding a project's own Python and its own
  packages, isolated from the system and from other projects.
- **`site-packages`** — the directory inside a Python installation where third-party
  packages actually live.
- **Pinning** — specifying an exact dependency version with `==`, so installs are
  reproducible.
- **Transitive dependency** — a package you didn't ask for, installed because something
  you did ask for needs it.
- **`-m` flag** — "run this module using *this* Python," removing ambiguity about which
  Python or which pip you meant.
- **`.gitignore`** — a list of paths git should never track; here it protects us from
  committing both bulk (`.venv/`) and secrets (`.env`).

---

**Next:** [A2 — Server breathes](02-fastapi-and-the-server.md). We write the first real
code: a FastAPI app with a `/health` endpoint you can open in a browser.
