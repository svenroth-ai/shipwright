#!/usr/bin/env python3
"""An explicit stack profile named in a wizard brief (campaign brief-driven-run B2b).

``brief_intake.py`` derives the profile from the persistence answer. A brief can also NAME one
(the WebUI Intent Wizard, a user, a project profile). This module finds that name, asks the
stack-profile resolver whether it can be used, and hands ``brief_intake.map_brief`` the answer.

Where the name comes from (first hit wins; an explicit value always beats inference):

1. a ``profile`` field (alias ``stack_profile``; ``profile`` wins; the first present field decides) of a JSON object / fenced JSON / ``key: value`` brief;
2. the ``Stack profile: <name>`` item of the one-line ``(Intake - ...)`` trailer the WebUI writes
   today (``composeNewBrief`` in the WebUI ``IntentWizard/contract.ts``).

The resolver alone decides what a name means (project > user > bundled, ``profile_resolver.py``):
no profile file is opened here, and nothing a profile file says is trusted or echoed unsanitized.
An unusable name is NEVER replaced by null or by another profile: ``profile`` stays null and the
result carries ``profile_error`` (plus ``warnings``) and the refusal shape of the package route
(``refused``/``code``/``message``/``issues``); the CLI exits 3 on it.

Loaded by file path from ``brief_intake.py`` (ADR-045). The resolver is reached the way
``shipwright-project``'s ``profile_check`` reaches it: ``shared/scripts`` appended, then removed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

FIELDS = ("profile", "stack_profile")
_SHARED_SCRIPTS = str(Path(__file__).resolve().parents[1])
_TRAILER_RE = re.compile(r"\(Intake\b[^)]*?\bStack profile:\s*([^;)]+)")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f‪-‮⁦-⁩]")  # C0, C1 controls and bidi overrides


def _plain(text: Any) -> str:
    """A resolver message made safe to print: no control characters, bounded length."""
    return _CTRL_RE.sub(" ", str(text))[:300]


def requested_name(raw: Any) -> tuple[bool, Any]:
    """``(present, value)``: the profile the brief names. ``value`` may be a non-string (invalid)."""
    if not isinstance(raw, dict):
        return False, None
    blank = False
    for key in FIELDS:
        value = raw.get(key)
        if value is None:
            continue  # absent: look at the next field
        if isinstance(value, str) and not value.strip():
            blank = True  # present but blank = no choice made here; the next field may still name one
            continue
        return True, value.strip() if isinstance(value, str) else value
    if blank:
        return False, None  # a blank field means the prose trailer is NOT consulted either
    desc = raw.get("description")
    match = _TRAILER_RE.search(desc) if isinstance(desc, str) else None
    if match:
        return True, match.group(1).strip().rstrip(".,")
    return False, None


def _resolver() -> Any:
    if not os.path.isfile(os.path.join(_SHARED_SCRIPTS, "profile_resolver.py")):
        raise ImportError(f"stack-profile resolver not found in {_SHARED_SCRIPTS}")
    added = _SHARED_SCRIPTS not in sys.path
    if added:
        sys.path.append(_SHARED_SCRIPTS)  # APPEND: plugins own a `lib`
    try:
        import profile_resolver
    finally:
        if added and _SHARED_SCRIPTS in sys.path:
            sys.path.remove(_SHARED_SCRIPTS)
    return profile_resolver


def _error(name: Any, code: str, detail: str) -> dict:
    msg = f"the brief names stack profile {_plain(name)!r}, which cannot be used ({code}): {_plain(detail)}"
    return {
        "profile": None,
        "reason": f"brief names profile {_plain(name)!r}, which cannot be used -> NOT replaced by another profile",
        "extra": {"profile_requested": _plain(name), "profile_error": {"code": code, "message": msg},
                  "warnings": [msg], "refused": True, "code": "profile_unusable", "message": msg, "issues": []},
    }


def select(raw: Any, project_root: Any = ".") -> Optional[dict]:
    """None when the brief names no profile, else ``{profile, reason, extra}`` for ``map_brief``."""
    present, name = requested_name(raw)
    if not present:
        return None
    if not isinstance(name, str):
        return _error(name, "invalid", "a profile must be given as a name (string)")
    if name.lower() == "detecting":  # a placeholder state ("detect later"), not a stack a brief can choose
        return _error(name, "invalid", "'detecting' is a reserved placeholder, not a stack profile")
    try:
        res = _resolver().resolve_profile(name, project_root)
    except ImportError as exc:
        return _error(name, "resolver_unavailable", exc)
    except ValueError as exc:  # the resolver's error family: not_found / invalid / schema_*
        return _error(name, getattr(exc, "kind", "error"), exc)  # _error prints it sanitized
    return {
        "profile": res.name,
        "reason": f"brief names profile {res.name!r} ({res.source}): explicit value wins over inference",
        "extra": {"profile_requested": name, "profile_source": res.source,
                  "warnings": [_plain(w) for w in res.warnings]},
    }
