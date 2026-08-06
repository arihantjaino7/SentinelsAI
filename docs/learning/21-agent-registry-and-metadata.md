# 21 — Agent registry and metadata

> **Status:** done. `GET /agents` now returns purpose, checks, and display name for all five scanner agents.

## What we built

Each agent class now declares its own metadata — display name, purpose, a list of what it checks, and its category. A new file, `agents/registry.py`, holds the single list of all agents and a `list_agents()` function. The orchestrator and the new `GET /agents` route both read from that one list. Nothing else changed about how agents run.

## The one big idea: class attributes as declarations

A class in Python can hold two kinds of things: **methods** (functions that do work) and **attributes** (values that describe the class itself). You've seen instance attributes before — `self.name = "headers"` stores something on a specific object. A **class attribute** is declared directly on the class body, with no `self`, and belongs to the class rather than any one instance:

```python
class Dog:
    species = "Canis lupus familiaris"   # class attribute — shared by all dogs
    
    def __init__(self, name):
        self.name = name                 # instance attribute — belongs to this dog
```

Every `Dog` object shares the same `species`, but each one has its own `name`. That's the exact shape used for agent metadata: `HeadersAgent.name` and `HeadersAgent.checks` are true for every instance of `HeadersAgent`, so they live on the class, not on `self`.

The payoff is that you can read them from the *class itself* — no instance needed:

```python
for cls in AGENTS:
    print(cls.display_name)   # works without ever calling cls()
```

## The registry pattern

Agents used to be listed in two places: `orchestrator.py` imported them all by name, and `ScanProgress.tsx` on the frontend hardcoded the same five names. That's the kind of duplication that causes bugs — add a sixth agent, forget to update one place, and things break silently.

The fix is a **registry**: one file owns the list, and every other file that needs it imports from there. `agents/registry.py` is now that file. The orchestrator imports `AGENTS` from it. When M8 builds the per-agent frontend pages, they'll fetch the list from `GET /agents` instead of hardcoding names. Adding a sixth agent means one class plus one line in `registry.py` — nowhere else.

## The actual code

`agents/registry.py` — the whole thing:

```python
from agents.dns_email import DNSAgent
from agents.exposure import ExposureAgent
from agents.headers import HeadersAgent
from agents.recon import ReconAgent
from agents.tls import TLSAgent
from models import AgentInfo

AGENTS = [HeadersAgent, ReconAgent, TLSAgent, ExposureAgent, DNSAgent]

def list_agents() -> list[AgentInfo]:
    return [
        AgentInfo(
            name=cls.name,
            display_name=cls.display_name,
            purpose=cls.purpose,
            checks=cls.checks,
            category=cls.category,
        )
        for cls in AGENTS
    ]
```

Each agent class gets four new lines, e.g. `headers.py`:

```python
class HeadersAgent(BaseAgent):
    name = "headers"
    display_name = "Security Headers"
    purpose = "Checks whether the server sends the four most important security-related HTTP response headers."
    checks = [
        "Content-Security-Policy — restricts what scripts/styles/frames the browser will load",
        "Strict-Transport-Security — prevents downgrade attacks from HTTPS to HTTP",
        "X-Content-Type-Options — stops browsers from guessing a response's content type",
        "X-Frame-Options — blocks the page from being embedded invisibly in another site",
    ]
    category = "Headers"
```

The orchestrator now has one import instead of five:

```python
from agents.registry import AGENTS  # was: from agents.headers import HeadersAgent, ...
```

## Try it

Start the backend:

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload
```

Then:

- `curl localhost:8000/agents` — you get a JSON array of five objects, each with `name`, `display_name`, `purpose`, `checks`, `category`.
- `localhost:8000/docs` — `GET /agents` appears in the docs list automatically.
- Run a real scan — it works exactly as before. Metadata is inert at scan time.

## Words worth knowing

- **Class attribute** — a value on the class itself, not on any instance. Shared by all objects of that class.
- **Registry** — a central list that other code imports, so the list exists in exactly one place.
- **`list_agents()`** — reads class attributes from each class in `AGENTS` and returns plain `AgentInfo` objects the API can serialize.

---

**Next:** M4 — structured evidence. The headers agent starts attaching real request/response data to each finding, proving the evidence shape before touching the other four.
