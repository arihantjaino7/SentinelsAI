"""Hard caps on remediation writes -- readable constants at the top, the
same style `agents/probe.py`'s `Budget` established for HTTP probing,
extended here to plan size and (from Stage B on) PR creation.

Stage A only enforces `MAX_FILES_PER_PR` (see `remediation/patch.py`'s
`validate_plan`). The other two exist now because they're part of this
stage's design and belong next to the constant they'll gate, not because
anything reads them yet -- Stage B is what opens a PR.
"""
from __future__ import annotations

MAX_FILES_PER_PR = 10
MAX_PRS_PER_SCAN = 3
MAX_PRS_PER_HOUR = 10
