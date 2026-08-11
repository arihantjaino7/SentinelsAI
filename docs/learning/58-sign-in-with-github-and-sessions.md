# 58 — Sign in with GitHub, and how a session cookie actually works

> **Status:** done. PLAN-v5 Stage 0. Every route except `/`, `/health`,
> `/agents`, `/repo/agents`, and `/auth/*` now requires a signed-in user.
> `pytest backend/tests -q` → 137 passed (36 new). Manually verified end to
> end with a `TestClient`: no cookie → 401, public routes stay open, sign-in
> → protected routes serve, logout revokes the session immediately.

## What we built

Until now, Sentinels had no idea who was asking. Every one of its 21 routes
was reachable by anyone who could reach the port — fine for a read-only
scanner, not fine for a feature that's about to be able to open pull
requests on someone's GitHub repositories (PLAN-v5 Stage B). So before any
of that gets built, Sentinels needs an answer to "who is this?"

The answer is **"sign in with GitHub"** — no password, no new account to
register. The same GitHub App that will later write to your repos also acts
as an identity provider: you approve on github.com, GitHub tells us your
username and numeric id, and we remember you. Nothing about your GitHub
account's actual access is stored — the access token GitHub hands us is used
once, to ask "who is this?", and then thrown away.

Once someone's signed in, the browser needs a way to prove "I'm still that
person" on every later request, without sending GitHub credentials each
time. That's what a **session cookie** does, and it's the part with the most
new ideas in it.

## New concept: a session is a receipt, not a password

When you sign in, the server doesn't remember *you* — it remembers a random
number, and gives your browser a copy of it. Every later request, your
browser hands that number back, and the server checks: "do I have this
number on file, and whose is it?" If yes, you're that person. If the number
is wrong, missing, or one the server has never seen, you're nobody.

Standalone example — a coat check, not a security system, but the same shape:

```python
import secrets

checked_coats = {}  # ticket -> owner's name

def check_coat(name: str) -> str:
    ticket = secrets.token_urlsafe(8)
    checked_coats[ticket] = name
    return ticket  # you get this back, and it's what you present later

def claim_coat(ticket: str) -> str | None:
    return checked_coats.get(ticket)  # None if it's not a real ticket
```

`check_coat("Ariha")` hands you a ticket; you don't need to say your name
again to get your coat back — you show the ticket. Lose the ticket and
someone else can claim your coat; that's why `secrets.token_urlsafe`
(unguessable) matters, not `random` (predictable, meant for simulations).

`backend/auth/session.py`'s `new_token()` is exactly `check_coat`'s ticket.
`storage/users.py`'s `sessions` table is `checked_coats`.

## New concept: signing, so a forged ticket doesn't work

A plain random ticket is enough for a coat check, but not for a web app —
here, *anyone* could type in a random-looking string and try it as a cookie.
So the cookie isn't just the ticket; it's the ticket plus a **signature**
only the server could have produced, using a secret key nobody else has.

```python
import hmac, hashlib

SECRET = "only-the-server-knows-this"

def sign(message: str) -> str:
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

def verify(message: str, signature: str) -> bool:
    # NOT `sign(message) == signature` — see below.
    return hmac.compare_digest(sign(message), signature)
```

Now a cookie is `token.signature`. Verifying it is two checks: does the
signature match what we'd compute for this token (proves *we* issued it),
and does the token's hash exist in our `sessions` table (proves it hasn't
been revoked). A forged cookie fails the first check before the database is
ever touched. A revoked cookie — someone logged out — fails the second, even
though its signature is perfectly valid.

## New concept: why `compare_digest` and not `==`

`verify` above uses `hmac.compare_digest`, not a plain `==`. Here's why that
distinction is not pedantry:

```python
def naive_equals(a: str, b: str) -> bool:
    return a == b   # stops at the FIRST mismatched character
```

Python's `==` on strings compares character by character and returns the
instant it finds a difference. That means comparing `"aXXXXX"` to the real
secret `"abXXXX"` takes measurably less time than comparing `"abcXXX"` to
it — the second one matched one more character before failing. An attacker
who can measure response time precisely (and over a network, with enough
attempts, they often can) can use that timing difference to guess a secret
one character at a time, instead of needing to guess the whole thing at
once. `compare_digest` always takes the same amount of time no matter where
the strings first differ, so there's nothing to measure.

This is the same reason `session.py`'s `token_from_cookie` uses it, and it's
why the file's docstring calls this out explicitly rather than leaving it as
an unremarked implementation detail.

## The actual code, walked through

**The cookie, end to end** (`backend/auth/session.py`):

```python
def cookie_value(token: str, secret: str) -> str:
    return f"{token}{_SEPARATOR}{_sign(token, secret)}"

def token_from_cookie(raw: str, secret: str) -> str | None:
    token, separator, signature = raw.partition(_SEPARATOR)
    if not separator or not token or not signature:
        return None
    if not hmac.compare_digest(signature, _sign(token, secret)):
        return None
    return token
```

`token_from_cookie` returns `None` for *every* kind of bad cookie — empty,
malformed, wrong signature — rather than raising different exceptions for
each. That's deliberate: the caller (`auth/deps.py`) reacts to "not valid"
exactly one way (401), so there's no reason to make it sort failures it will
treat identically. Distinguishing them in the response would also hand an
attacker a free hint about which part of their forged cookie was closest.

**Only the hash is stored, never the token** (`storage/users.py`):

```python
def user_for_token_hash(token_hash: str) -> User | None:
    row = conn.execute(
        "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ?", (token_hash,)
    ).fetchone()
    ...
```

This mirrors why a password table stores a hash, not the password: if
someone copies `sentinels.db`, they get nothing they can present as a valid
cookie — a hash can't be turned back into the token that produced it. The
real token only ever exists in the signed cookie itself and in the moment it
was generated.

**The dependency every protected route hangs off** (`backend/auth/deps.py`):

```python
def current_user(request: Request) -> User:
    user = _resolve(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user
```

FastAPI's `Depends(current_user)` runs this *before* a route's own code, and
if it raises, the route body never executes at all:

```python
@app.get("/scans", response_model=list[ScanSummary])
def scans_list(limit: int = 20, offset: int = 0, user: User = Depends(current_user)):
    ...
```

There's no `if not signed_in: return 401` to forget inside `scans_list` — the
check happens outside the function that needs protecting, which is the whole
point: a protected route has no way to accidentally skip its own protection.

**Rejected alternative: storing state instead of trusting a signed cookie.**
An earlier shape considered was a plain random cookie with *no* signature,
checked only against the database. That's simpler code, but it means a
malformed or garbage cookie value still costs a database round-trip to
reject. Signing the cookie moves that rejection to pure computation — no
database involved — which matters once this same dependency runs on every
single request to every protected route.

**Rejected alternative: JWT instead of a database-backed session.** A JWT
(a signed token that carries its own claims, like "user #42, expires at
...") needs no database lookup to verify at all — the signature alone proves
it's valid. That's attractive, but it comes with a real cost: a JWT can't be
revoked before it expires. There's no row to delete. Logging out could only
mean "the browser promises to forget it" — the token is still perfectly
valid if someone captured it first. Given autofix is about to be able to
open pull requests, "logout must actually work" was worth the one extra
database lookup per request.

## New concept: OAuth's "state" parameter

Before sending the browser to GitHub, `GET /auth/github/login` generates a
random `state` value, remembers it in a short-lived cookie, and sends it to
GitHub too. GitHub sends it back unchanged on the callback. If they don't
match, the callback refuses to continue.

Why this matters: without it, an attacker could start their *own* sign-in
flow, get a valid `code` back from GitHub for *their* account, and then trick
your browser into visiting the callback URL with their code — logging you
into their account under an identity you didn't choose. Checking that the
`state` we get back matches the one we generated proves the callback we're
handling belongs to the login attempt we started, not one an attacker
started elsewhere and handed to us.

## Try this

- Sign in, then open devtools → Application → Cookies, and look at
  `sentinels_session`. Copy the value, sign out, paste it back in as the
  cookie — confirm `GET /auth/me` now returns 401. The signature is still
  perfectly valid; only the database row is gone.
- In `backend/tests/test_auth.py`, `test_tampered_token_is_rejected` flips
  one character in a real cookie. Try flipping a character in the
  *signature* half instead (`test_tampered_signature_is_rejected` already
  does this) and confirm both fail the same way.
- Unset `SENTINELS_SESSION_SECRET` and hit any protected route — you get a
  503, not a 401. That's `deps.py` failing loudly ("this server isn't set up
  right") instead of quietly ("nobody's allowed in"), which is a much easier
  bug to notice during setup.

## Words you now know

- **Session** — a server-side record ("this random number belongs to user
  #42") that a cookie references, so the browser never has to resend real
  credentials.
- **HMAC** — a way to sign a message with a secret key so that only someone
  holding the key could have produced a valid signature for it.
- **Constant-time comparison** — comparing two values in a way that takes the
  same time regardless of where they differ, closing off a timing-based
  guessing attack.
- **OAuth `state` parameter** — a value round-tripped through the identity
  provider to prove a callback belongs to the login attempt that started it.
- **Fail closed** — when something is ambiguous or broken (an unparseable
  timestamp, a missing secret), treat it as *not allowed* rather than
  *allowed*.
