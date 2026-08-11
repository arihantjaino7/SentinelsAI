"""Identity for Sentinels — who is asking, and may they write to a repo.

Deliberately small. GitHub is the identity provider (`github_oauth.py`), so
there are no passwords in this codebase to hash, leak, reset, or get wrong.
`session.py` owns the cookie; `deps.py` is what routes actually depend on.
"""
