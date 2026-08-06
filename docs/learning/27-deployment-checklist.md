# 27 — Deployment checklist

> **Status:** done. Every scan now produces a 16-item deployment checklist, a readiness score (0–100), and a deployment status (ready / caution / blocked). Self-attested items can be answered in the UI and persist across refreshes.

## What we built

After a scan finishes, the system evaluates its findings against 16 deployment-readiness checks and saves the results to the database. A new `/scan/{id}/checklist` page shows all three tiers — auto-verified, passively inferred, and self-attested — with expandable rows. The dashboard now shows a clickable deployment badge linking there.

## The one big idea: a pure function

The checklist evaluator (`backend/checklist/evaluator.py`) is called a **pure function** — same inputs always give the same output, with no side effects.

Think of it like a calculator. You press 3 + 4 on a calculator and always get 7 — it doesn't check the internet, it doesn't remember your last answer, it doesn't change anything around it. Same here: hand the evaluator the same list of findings, you get the same checklist every time.

The practical upside: it's easy to test (no server needed), impossible to behave differently across environments, and deterministic in the same way `scoring.py` already is.

```python
# small standalone example — pure function
def double_all(numbers):
    return [n * 2 for n in numbers]

# same input → same output, always
print(double_all([1, 2, 3]))   # [2, 4, 6]
print(double_all([1, 2, 3]))   # [2, 4, 6] — always
```

The checklist version is a bit bigger, but the same idea:

```python
def evaluate(findings: list[Finding]) -> list[ChecklistItem]:
    items = []
    for rule in RULES:
        state, explanation, fix = rule.evaluate(findings)
        items.append(ChecklistItem(item_key=rule.key, state=state, ...))
    return items
```

`rule.evaluate(findings)` is itself pure — each rule is just a function that reads the findings list and returns a string triple.

## The second idea: three tiers, one honest constraint

Sentinels is passive-only — it can only read, never probe. That limits what it can actually confirm:

| Tier | What it means | Example |
|---|---|---|
| **auto** | Sentinels saw this directly | HSTS header was missing |
| **inferred** | Weak signal, not conclusive | robots.txt lists admin paths |
| **self_attested** | We can't test this; you answer | Rate limiting configured? |

Self-attested items start as `unknown` and can be flipped to `pass` or `fail` by the developer. The answer is stored in the DB so it survives refresh. The `POST /scans/{id}/checklist/{key}` endpoint only allows writing to `self_attested` rows — the WHERE clause rejects any attempt to overwrite an auto-verified result:

```python
UPDATE checklist_items
SET state = ?, explanation = ?
WHERE scan_id = ? AND item_key = ? AND tier = 'self_attested'
```

## The actual code

**Declaring a rule** (`backend/checklist/rules.py`):

```python
ChecklistRule(
    key="https_enforced",
    title="HTTPS enforced",
    tier="auto",
    agent="tls",
    blocking=True,   # a "fail" here forces deployment_status = "blocked"
    evaluate=_eval_https,
)
```

Each rule carries its own `evaluate` function. `blocking=True` means a failure on this item overrides the readiness score regardless of how well everything else looks.

**Computing the score** (`backend/checklist/evaluator.py`):

```python
def compute_readiness(checklist):
    auto_items = [c for c in checklist if c.tier == "auto"]
    passing = sum(1 for c in auto_items if c.state == "pass")
    readiness_score = round(passing / len(auto_items) * 100)
    # blocking fail? → "blocked", regardless of score
    for item in auto_items:
        rule = rule_by_key[item.item_key]
        if rule.blocking and item.state == "fail":
            return readiness_score, "blocked"
    ...
```

Self-attested items are excluded from the score — they're the developer's declaration, not an observed fact.

## Try it

```bash
# Run a scan and see the checklist fields
curl -s -X POST localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d['readiness_score'], d['deployment_status'])"

# Fetch just the checklist
curl -s localhost:8000/scans/{id}/checklist | python3 -m json.tool

# Answer a self-attested item
curl -s -X POST localhost:8000/scans/{id}/checklist/rate_limiting \
  -H "Content-Type: application/json" -d '{"state":"pass"}'
```

Then open `/scan/{id}/checklist` in the browser and confirm the answered item shows "Pass" after a hard-refresh.

## Words worth knowing

- **Pure function** — a function where the output depends only on the inputs, with no side effects and no hidden state.
- **Blocking item** — a checklist rule where a "fail" forces `deployment_status = "blocked"`, overriding the readiness score.
- **Self-attested** — a check Sentinels cannot run passively; the developer answers it manually.
- **Readiness score** — percentage of auto-verified checklist items in "pass" state (0–100).

---

**Next:** M12 — Extract the LLM client. One clean place that talks to Groq, before fix suggestions and the chatbot both need it.
