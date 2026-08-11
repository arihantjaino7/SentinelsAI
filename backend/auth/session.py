"""Session cookies: how a browser proves it is the same person who signed in.

The cookie carries two things joined by a dot: a random token, and an HMAC
signature of that token. Verifying a request is therefore two independent
checks, and they catch different attacks:

  1. The signature proves the token came from this server. A garbage or
     hand-crafted cookie is rejected here, before any database work happens.
  2. The token's SHA-256 hash is looked up in `sessions`. This is what makes
     logout real — the row is deleted, so the still-perfectly-signed cookie
     in the attacker's hands stops working immediately.

Only the *hash* is ever stored (`storage/users.py`). A stolen copy of
`sentinels.db` therefore contains nothing anyone can present as a valid
cookie, for the same reason a password table stores hashes rather than
passwords.

Both comparisons use `hmac.compare_digest`, never `==`. A normal string
comparison returns as soon as two characters differ, so how *long* it takes
leaks how much of the value was correct — enough, over many attempts, to
guess a secret one character at a time. `compare_digest` always takes the
same time regardless of where the difference is.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

# The cookie's name. Not a secret — it shows up in devtools — but it needs to
# be stable, because renaming it silently signs everyone out.
COOKIE_NAME = "sentinels_session"

# How long a session lasts before the browser has to sign in again. Fourteen
# days is a local developer tool's tradeoff: long enough that you aren't
# re-authenticating every morning, short enough that an abandoned laptop
# session doesn't stay valid for a year.
SESSION_TTL = timedelta(days=14)

# `secrets.token_urlsafe` emits A-Z a-z 0-9 - _ and never a dot, so a dot is
# an unambiguous separator between the token and its signature.
_SEPARATOR = "."


def get_session_secret() -> str | None:
    """Return the signing secret, or None if the operator never set one.

    Mirrors `ai.client.get_api_key` exactly — including the `or None`, which
    turns the empty string in the committed `.env.example` into a clean
    "absent" rather than a secret that is technically present and useless.

    Unlike the Groq key, though, a missing value here is not something to
    degrade gracefully around: without it there is no way to tell a real
    session from a forged one, so `deps.current_user` refuses to serve
    protected routes at all rather than quietly letting everyone in.
    """
    return os.environ.get("SENTINELS_SESSION_SECRET") or None


def new_token() -> str:
    """A fresh, unguessable session token.

    `secrets`, not `random`: `random` is a pseudo-random generator seeded from
    predictable state and is designed for simulations, not for values an
    attacker must not be able to predict. 32 bytes is well past brute force.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The value stored in `sessions.token_hash`.

    Plain SHA-256 with no salt is right here, unlike for passwords: the input
    is already 32 bytes of full-entropy randomness, so there is no dictionary
    to attack and nothing for a salt to defend against.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _sign(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def cookie_value(token: str, secret: str) -> str:
    """Build the string that actually goes into the Set-Cookie header."""
    return f"{token}{_SEPARATOR}{_sign(token, secret)}"


def token_from_cookie(raw: str, secret: str) -> str | None:
    """Verify a cookie's signature and return the bare token, or None.

    None means "do not trust this cookie" for every possible reason — no
    separator, empty half, wrong signature. Callers get one answer to check
    rather than a set of failure modes to enumerate and accidentally miss one.
    """
    token, separator, signature = raw.partition(_SEPARATOR)
    if not separator or not token or not signature:
        return None
    if not hmac.compare_digest(signature, _sign(token, secret)):
        return None
    return token


def session_expiry(now: datetime | None = None) -> str:
    """When a session minted right now should stop being accepted (ISO 8601 UTC)."""
    moment = now or datetime.now(timezone.utc)
    return (moment + SESSION_TTL).isoformat()


def is_expired(expires_at: str, now: datetime | None = None) -> bool:
    """True if an `expires_at` timestamp has passed.

    Expiry is enforced here, in Python, rather than by a `WHERE expires_at > ?`
    clause in SQL, so that string-vs-datetime comparison rules never become
    the thing standing between a stale session and a protected route.
    """
    moment = now or datetime.now(timezone.utc)
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        # An unparseable timestamp is corrupt data. Treat it as expired —
        # failing closed is the only safe direction for an auth check.
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= moment
