# 23 — Evidence for the remaining four agents

> **Status:** done. Recon, TLS, Exposure, and DNS all attach `evidence_items` now — every finding from every agent has structured evidence, not just Headers.

## What we built

M4 proved the evidence shape on one agent. This step is almost entirely repetition of that same pattern across the other four: Recon tags its findings `html_snippet` or `request`, TLS tags them `certificate` or `log`, Exposure tags them `request`, and DNS tags them `dns_record`. No new concepts, no schema changes — just `self.evidence(kind, label, content)` called at each of the ~18 remaining places a `Finding` gets built.

## The one thing actually worth explaining: picking the right `kind`

The only real judgment call here was: for a given finding, what *kind* of evidence is it? The rule that fell out of doing all four agents is simple — **ask what you actually did to get the data**, not what the finding is about:

- TLS's certificate expiry and protocol checks both come from the same real TLS handshake, but expiry is fundamentally about the *certificate* (`EvidenceKind.CERTIFICATE`), while the negotiated protocol version is more like a fact you *observed* about the connection (`EvidenceKind.LOG`) — there's no certificate field for "which protocol was negotiated."
- Exposure's `.env` and `.git/HEAD` checks are both plain GET requests, so both get `EvidenceKind.REQUEST` — even the finding that *fails* (file is exposed) only stores the request line and status code, never the response body. That's the same no-echo rule from the original Exposure agent (the whole reason it never puts secrets in the plain `evidence` string) — it applies to the new structured evidence just as strictly, since a UI reading `evidence_items` would leak the secret exactly as badly as one reading `evidence`.
- DNS's SPF and DMARC records are genuine DNS lookups, so `EvidenceKind.DNS_RECORD` for all of them, pass or fail.
- Recon's generator meta tag is a snippet of HTML (`EvidenceKind.HTML_SNIPPET`), but its robots.txt check is really just a plain GET whose *response* happens to list some paths — closer to `EvidenceKind.REQUEST` territory once no `Disallow` lines were found, but kept as `HTML_SNIPPET` for the listed-paths case since the evidence content *is* a fragment of the file's text either way.

None of this changes what a `Finding` looks like or how it's scored — it's purely about giving the right label to material that already existed.

## A repeated shape, once you've seen it

Every one of the ~18 call sites follows the exact same before/after shape M4 introduced. Exposure's `.env` check, for example:

```python
request_text = f"GET {env_url} -> {response.status_code}"
return Finding(
    id="env-file-exposed",
    ...
    evidence=request_text,                                    # unchanged, flat string
    evidence_items=[
        self.evidence(EvidenceKind.REQUEST, ".env request", request_text)
    ],
)
```

The pattern: pull the string that was already being built for `evidence=` out into a local variable first, then hand that same string to `self.evidence(...)` for the structured version too. Nothing is computed twice, and nothing new is exposed that the flat string didn't already show.

## Try it

- Scan a real site and print `[(f.agent, f.id, [e.kind for e in f.evidence_items]) for f in report.findings]` — you'll see all five agents represented, each with the kind that matches what it actually checked.
- Point the Exposure agent at a site with a real `.env` exposed (or a local test fixture) and confirm `evidence_items[0].content` still only shows the request line and status — never file contents.
- Fetch a stored scan back with `GET /scans/{id}` — every finding, from every agent, now has a non-empty `evidence_items` list, closing out what M4 left as `[]`.

## Words worth knowing

- No new terms this time — this step is the same `EvidenceKind` / `self.evidence()` machinery from note 22, applied everywhere it wasn't yet.

---

**Next:** M6 — scan routes with shareable URLs. A finished scan gets its own `/scan/<uuid>` page on the frontend that survives a page refresh.
