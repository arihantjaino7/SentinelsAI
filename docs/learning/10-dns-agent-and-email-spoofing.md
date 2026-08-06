# A10 — DNS agent

> **Status:** done. `backend/agents/dns_email.py` — `DNSAgent` checks whether a
> domain's email can be spoofed, by reading its SPF and DMARC DNS records.

## What we built

`DNSAgent` reads two public DNS records and asks one question: **if someone forges
an email claiming to be from this domain, would a receiving mail server have any
way to tell?**

- **SPF** — a text record listing which mail servers are allowed to send email as
  this domain.
- **DMARC** — a text record saying what a receiving server should *do* when a
  message fails that check (reject it, send it to spam, or do nothing).

Both are ordinary public DNS lookups — the same reads any real mail server does
before deciding whether to accept a message.

## The one big idea: TXT records, and reading them correctly

DNS's best-known job is turning a hostname into an IP address. A **TXT record** is
different — it's a free-text field attached to a domain, and the internet has
adopted it as a general place to publish small facts about a domain. SPF and DMARC
are both just TXT records with an agreed-upon format.

A real domain often has many unrelated TXT records at once (Google, Stripe, and
other services all ask you to "prove you own this domain" by publishing a specific
string there). So the code doesn't assume the first TXT record is the right one —
it searches for the one that actually starts with `v=spf1`:

```python
def _find_record(records: list[str], prefix: str) -> str | None:
    for record in records:
        if record.strip().lower().startswith(prefix.lower()):
            return record.strip()
    return None
```

An SPF record ends with an `all` rule that says what to do about senders it didn't
list — `-all` (reject them), `~all` (flag them as suspicious), `?all` (no opinion,
same as nothing), or `+all` (allow literally everyone, which is worse than having
no SPF at all). A DMARC record has a `p=` policy — `reject`, `quarantine` (spam
folder), or `none` (just watch and report, don't block anything).

Two real discoveries while testing this: `gmail.com`'s SPF record uses
`redirect=_spf.google.com` instead of ending in `all` — a valid mechanism meaning
"go check that other domain's record instead," which the code checks for
explicitly so it isn't wrongly flagged as having no policy. And both `gmail.com`
and `python.org` have DMARC set to `p=none` — even big, well-run domains often
leave DMARC in "monitor only" mode rather than fully enforcing it.

## The actual code

```python
def _query_txt(name: str) -> list[str]:
    try:
        answer = dns.resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    ...
```

`dnspython`'s resolver is blocking (not async), so it's called through
`asyncio.to_thread(...)` from `scan()` — the same trick used for TLS lookups in
A8, so this one slow lookup doesn't freeze the whole event loop. Two exceptions
both just mean "nothing here": `NXDOMAIN` (the name doesn't exist at all) and
`NoAnswer` (the name exists but has no TXT record) — both happen for real,
so both need catching.

```python
all_token = next((t for t in tokens if t.lower().lstrip("+-~?") == "all"), None)
qualifier = all_token[0] if all_token[0] in "+-~?" else "+"
```

`.lstrip("+-~?")` strips any of those symbols off the front of the token. A bare
`all` (no symbol) has nothing to strip, so it's treated as `+all` — the permissive
default, per the SPF spec.

## Try it

Look up any domain's own records, no project code involved:

```bash
cd backend
./.venv/Scripts/python.exe -c "
import dns.resolver
for name in ['example.com', '_dmarc.example.com']:
    for rdata in dns.resolver.resolve(name, 'TXT'):
        print(name, '->', b''.join(rdata.strings))
"
```

- Run `DNSAgent` against `example.com` (should be clean), `gmail.com` (SPF passes
  via `redirect=`, DMARC warns on `p=none`), and `badssl.com` (fails both — no
  records at all).
- Check the full scan: `curl -X POST localhost:8000/scan -d "{\"url\": \"github.com\"}"` — five agents now in `"agents"`.

## Words worth knowing

- **TXT record** — a free-text DNS record, used to publish small facts about a
  domain (SPF, DMARC, and site-ownership strings all live here).
- **SPF** — lists which mail servers are allowed to send email as a domain.
- **DMARC** — says what to do with mail that fails SPF, and where to report it.
- **`p=none`** — DMARC in "watch only" mode; common even on major domains.

---

**Next:** A11 — Parallel. All five agents run at once via `asyncio.gather`, instead
of one after another.
