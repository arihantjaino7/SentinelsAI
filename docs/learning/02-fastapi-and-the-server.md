# A2 — Server breathes

> **Status:** done. `backend/main.py` serves `/health` and `/` on port 8000.

## What we built

A file, `backend/main.py`, that answers when you visit `localhost:8000/health` in
a browser. That's it. No scanning yet — just a server that responds.

## The one big idea

When your browser asks for `/health`, the request passes through **three
things**, in order:

```
Browser  →  Uvicorn  →  FastAPI  →  your function
```

- **Browser** — sends plain text over the network: "give me /health".
- **Uvicorn** — a program that owns the actual network connection. It reads
  that text and hands it to FastAPI.
- **FastAPI** — doesn't touch the network at all. It just keeps a list of
  "when this URL is asked for, call this function" and looks yours up.
- **Your function** (`health()`) — plain Python. It has no idea a browser or
  the internet exists. It just returns a dict.

That's the whole architecture. Everything else in this note is detail on top
of that one picture.

## How you tell FastAPI "call this function for this URL"

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

That `@app.get("/health")` line is called a **decorator**. All it does is add
one entry to FastAPI's lookup list: *"when someone asks for GET /health, call
this function."* It doesn't change your function at all — `health()` still
works exactly like a normal function if you call it directly yourself.

Think of it like writing a name on a sign-up sheet. Writing your name down
doesn't change who you are — it just means someone with the sheet in hand
knows to call you when needed.

## The actual file

```python
from fastapi import FastAPI

app = FastAPI(title="Sentinels")

@app.get("/")
def root():
    return {"service": "Sentinels", "health": "/health"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "Sentinels"}
```

- `app = FastAPI(...)` creates that lookup list.
- `/` is just a friendly landing message, so visiting the bare address doesn't
  look broken.
- `/health` is the one that actually answers "is the server alive?" It
  deliberately does nothing fancy — no database check, no network call —
  because a health check that can fail for unrelated reasons is a bad health
  check.

## Try it

Start the server:

```bash
cd backend && ./.venv/Scripts/python.exe -m uvicorn main:app --reload
```

Then:

- Open `localhost:8000/health` — you should see `{"status": "ok", ...}`.
- Open `localhost:8000/docs` — a free, auto-generated page listing every
  route, built by FastAPI just from reading your code.
- Try a URL that doesn't exist, e.g. `localhost:8000/nope` — you get a `404`.
  That's the lookup list being asked for something it doesn't have.

## A couple of words worth knowing

- **Uvicorn** — the program that actually owns the network connection.
  FastAPI never touches a socket directly.
- **Decorator** (`@something`) — a way of registering a function without
  changing it.
- **`--reload`** — restarts the server automatically whenever you save a
  file, so you don't have to stop and start it by hand while developing.
- **`main:app`** — tells uvicorn "open `main.py`, and use the variable called
  `app` inside it."

---

**Next:** A3 — The contract. We write the shared shape every scanning agent
will follow.
