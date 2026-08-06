# 37 — The Secrets agent

> **Status:** done. `backend/agents/repo/secrets.py` scans a repo's files for
> committed credentials and reports them without ever revealing the real value.

## What we built

A new repo agent, `SecretsAgent`, that reads every file in a scanned repo and
looks for three things: known credential *shapes* (an AWS key always looks
like `AKIA` + 16 characters), a committed `.env` file, and code that looks
like `SECRET_KEY = "some random string"`. Whatever it finds gets reported
with the file and line number — but the actual secret is masked before it
ever leaves the agent.

## The one big idea: matching a shape, not guessing a value

We're not brute-forcing anyone's password. Every provider publishes a fixed
format for its keys — that's the whole trick. An AWS key always starts
`AKIA` or `ASIA` followed by exactly 16 more characters. A regex that matches
*that shape* will catch a real leaked key with no guessing involved:

```python
import re

aws_key = re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")
text = "AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP"
print(aws_key.search(text).group())   # AKIAABCDEFGHIJKLMNOP
```

`secrets.py` has eight of these, one per well-known provider (AWS, GitHub,
Groq, OpenAI, Stripe, Google, Slack, and private-key files) — the same public
signatures tools like gitleaks use.

## The second idea: entropy catches what shapes can't

Most secrets have no fixed shape — a Django `SECRET_KEY` can be any random
string. For those we measure **Shannon entropy**: roughly, "how surprised
would you be by the next character?" A random string is high entropy; a word
or a repeated pattern is low entropy.

```python
import math
from collections import Counter

def entropy(s):
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())

print(entropy("aaaaaaaa"))        # ~0.0  -- totally predictable
print(entropy("xK9pL2vQ8mN4wZ7r"))  # ~3.9  -- looks random
```

High entropy alone isn't enough, though — a commit hash or a UUID is also
high entropy, and flagging every one of those would bury the real findings.
So the check only fires when **both** are true: the variable name contains a
secret-suggestive word (`key`, `secret`, `token`, `password`, ...) *and* the
value's entropy clears a threshold. That's why the fixture test uses two
identical random values — one named `SECRET_KEY` (flagged) and one named
`SESSION_ID` (not flagged): same randomness, different name, different
result. Name-only or entropy-only would either miss `SECRET_KEY` or drown in
noise.

## Never echoing the secret

Every finding runs the matched value through one function before it's ever
stored:

```python
def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"
```

The report says `AKIA...MNOP`, never the real key. Verification doesn't just
eyeball the finding text for this — it dumps the whole `AgentResult` to JSON
and asserts the real secret string is nowhere in it, which would also catch
a mistake in some other field accidentally including it.

## Why finding IDs had to become dynamic

Every earlier agent used a fixed id per check, e.g. `"repo-readme-present"`
— there's only ever one README check per scan. Secrets don't work that way:
the same AWS-key pattern can match in five different files, or five times in
one file. If every match reused one static id like `"secret-aws-key"`, the
second occurrence would silently overwrite the first in anything keyed by
id — including the "Fix with AI" button, which looks up a finding by
`finding.id == finding_key`. Two unrelated leaks would collide, and fixing
the second would actually generate a fix for the first. The id is built from
the match itself instead: `f"secret-{provider}-{file_path}-L{line}"` — unique
per occurrence, and stable if you re-scan the same unchanged repo.

## Try it

```bash
cd backend && .venv/Scripts/python.exe -c "
from agents.repo.secrets import _mask, _shannon_entropy
print(_mask('AKIAABCDEFGHIJKLMNOP'))
print(_shannon_entropy('aaaaaaaa'), _shannon_entropy('xK9pL2vQ8mN4wZ7r'))
"
```

- Create a file with `MY_SECRET_TOKEN = "aaaaaaaaaaaaaaaaaaaa"` (low entropy,
  repeated character) — no finding, even though the name matches.
- Create `.env.example` containing AWS's own published example key
  (`AKIAIOSFODNN7EXAMPLE`) — zero findings, because `.env.example` is
  excluded from scanning entirely, not just the "real .env" rule.
- Run the agent against a real small public repo and confirm it finishes
  with zero findings and no crash.

## Words worth knowing

- **Shannon entropy** — a number measuring how unpredictable a string's
  characters are; random-looking strings score high, repetitive ones score low.
- **Masking** — replacing most of a sensitive value with `*` or `...` before
  it's ever displayed or stored.
- **Provider signature** — the fixed, published format a company's API keys
  always follow (e.g. `sk-` for OpenAI keys).

---

**Next:** R5 — the Dependencies agent, which checks a repo's manifests
against the OSV.dev vulnerability database.
