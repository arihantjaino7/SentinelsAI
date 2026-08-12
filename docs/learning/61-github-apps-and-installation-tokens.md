# 61 — GitHub Apps and installation tokens

> **Status:** done. `backend/remediation/tokens.py`,
> `backend/storage/installations.py`, and four new routes
> (`/auth/github/install`, its callback, `GET /installations`,
> `POST /installations/{id}/revoke`).

## What we built

The permission half of Stage B: the machinery that lets Sentinels prove it
is allowed to write to your repository, for about an hour at a time, without
ever holding a credential that could do so permanently.

## The one big idea: the key that opens the safe never opens a door

Back in Stage 0, signing in with GitHub got an access token, used it once to
read your username, and **threw it away**. That was deliberate: knowing who
you are doesn't require standing permission to act as you.

But Stage B does need to act — it opens a pull request. So how do we get
permission without going back on that?

The answer is a chain where each link is weaker than the one before it:

1. The App has an **RSA private key** — a file on disk, outside the repo.
   It is a *signing* key, not a password. It cannot read or write anything.
2. We sign a **JWT** with it. That's just three chunks of base64 joined by
   dots: a header, some claims, and a signature. The signature is the part
   that matters — nobody without the private key can produce one that
   verifies. Our claims are only "which app" and "valid for nine minutes".
3. That JWT proves *"I am the Sentinels App."* It still cannot touch a single
   file. All it can do is be traded, at one specific endpoint, for…
4. …an **installation token**: a real credential, good only for the
   repositories one installation covers, expiring in about an hour.

The whole shape exists for step 3. The thing that lasts forever can't touch
your code, and the thing that can touch your code doesn't last.

A tiny standalone version, nothing to do with GitHub:

```python
def day_pass(master_key, room):
    return f"{room}-pass-expires-in-1h"

# The master key opens the machine that prints passes.
# It does not open any door.
```

## Nine minutes, and why it's backdated

```python
_JWT_TTL_SECONDS = 9 * 60
_JWT_BACKDATE_SECONDS = 60

payload = {
    "iat": issued - _JWT_BACKDATE_SECONDS,   # issued at
    "exp": issued + _JWT_TTL_SECONDS,        # expires at
    "iss": app_id,                           # issuer
}
return jwt.encode(payload, private_key, algorithm="RS256")
```

GitHub rejects any App JWT claiming more than ten minutes of life, so nine
leaves a minute of headroom. The backdated `iat` handles the opposite
problem: if our clock runs a few seconds slow, a token we just minted looks
to GitHub like it was issued *in the future*, which it also rejects. Both
numbers are guarding against the same thing — two computers disagreeing
about what time it is.

`RS256` is the asymmetric one: we sign with the private key, GitHub verifies
with the public key it already has. That's the reason `cryptography` had to
be added alongside `PyJWT` — PyJWT on its own can only do the symmetric kind
(HMAC), where both sides share one secret.

## Signing in and installing are two different things

This is the distinction that made a whole extra flow necessary. GitHub has
two separate journeys, and the plan had quietly assumed the second one
already existed (it's written up as conflict #10 in `PLAN-v5.md`):

| | Sign in | Install |
|---|---|---|
| Asks | "who are you?" | "may we write to your repos?" |
| Result | a session cookie | a row in `github_installations` |
| Route | `/auth/github/login` | `/auth/github/install` |

Someone can do the first and never the second — and Sentinels has to work
for them, just without autofix. So the install callback is its own route,
and every write later checks for its own thing:

```python
installation = active_installation_for(user.id, owner)
```

Both halves matter. `user.id` because someone else's grant is not yours to
use, and the query's `revoked_at IS NULL` because withdrawing a grant has to
take effect immediately, not at the next restart.

## The one thing that couldn't be checked and didn't need to be

The install callback receives an `installation_id` in a query string. There
is no code-for-token exchange to "verify" it — and that's fine, because of
two facts stacked together:

- GitHub only redirects here after the person signed in *on github.com*
  completed the install screen themselves.
- The `state` value we set as a cookie before sending them there comes back
  unchanged, which ties that redirect to *this* browser session.

What the callback does still have to do is ask GitHub *which account* the
installation covers — the redirect carries only a number, and the account
name is what every later permission check compares against.

## Two switches for the developer token

`DevTokenProvider` reads a personal access token from the environment, so the
Git half could be built before the App was registered. It needs **two**
separate environment variables set — the token itself, and
`SENTINELS_ALLOW_DEV_TOKEN=1`.

One variable would have meant a token left over from a debugging session
stays live forever. With two, forgetting to delete the token isn't enough to
keep using it. `default_provider()` only picks the dev path when both are on.

## Try it

- Run `pytest tests/test_remediation_tokens.py -q`. The RSA key is generated
  inside the test file; nothing touches the network.
- In `test_app_jwt_carries_the_expected_claims`, change `_JWT_TTL_SECONDS` in
  `tokens.py` to `11 * 60` and watch the assertion catch it — that test is
  guarding GitHub's ten-minute rule.
- Try `test_app_jwt_is_signed_with_the_configured_key`: it decodes a real
  token with the *wrong* public key and expects the signature check to fail.
  That's the entire security property of a JWT in one assertion.

## Words worth knowing

- **JWT** — a small signed blob of claims. Not encrypted; anyone can read it,
  nobody can forge it without the key.
- **Claims** — the facts inside it (`iss` issuer, `iat` issued-at,
  `exp` expiry).
- **RS256** — signing with a private key, verifying with a public one.
- **Installation** — one grant of an App onto one GitHub account.
- **Installation token** — the short-lived credential that grant can mint.
- **Clock skew** — two machines disagreeing about the time, and the reason
  `iat` is backdated.

---

**Next:** [62 — Committing without a clone](62-committing-without-a-clone.md),
where that token finally gets used.
