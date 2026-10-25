#!/usr/bin/env python3
"""An explicit stack profile named in a wizard brief (campaign brief-driven-run B2b).

``brief_intake.py`` derives the profile from the persistence answer. A brief can also NAME one
(the WebUI Intent Wizard, a user, a project profile). This module finds that name, asks the
stack-profile resolver whether it can be used, and hands ``brief_intake.map_brief`` the answer.

Where the name comes from (first hit wins; an explicit value always beats inference):

1. a STRICT field: ``profile`` (JSON / fenced JSON) or ``stack_profile`` (also the ``Stack profile:`` line of
   a ``key: value`` brief); ``profile`` wins; the first present field decides. A strict name that cannot be
   used is an error (exit 3);
2. a HINT: a bare, unbulleted ``profile: x`` line of a ``key: value`` brief (``profile_hint``). Free text
   uses that word too ("Profile: none", "- profile: avatar"), so a hint counts only when it has the
   profile-name shape AND the resolver finds it; anything else stays prose, is not used, and adds a
   non-blocking ``warnings`` entry (exit 0) that points to ``Stack profile: <name>``;
3. the ``Stack profile: <name>`` item of the ``(Intake ...)`` trailer the WebUI writes today
   (``composeNewBrief`` in the WebUI ``IntentWizard/contract.ts``): the LAST ``(Intake`` in the text, which
   must end it. Two trailers or two ``Stack profile:`` items are ambiguous and refused.

The resolver alone decides what a name means (project > user > bundled, ``profile_resolver.py``):
no profile file is opened here, and nothing a profile file says is trusted or echoed unsanitized.
An unusable name is NEVER replaced by null or by another profile: ``profile`` stays null and the
result carries ``profile_error`` (plus ``warnings``) and the refusal shape of the package route
(``refused``/``code``/``message``/``issues``); the CLI exits 3 on it.

Loaded by file path from ``brief_intake.py`` (ADR-045), and only for a brief that can name a profile.
The resolver is reached the way ``shipwright-project``'s ``profile_check`` reaches it:
``shared/scripts`` appended, then removed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

FIELDS = ("profile", "stack_profile")
AMBIGUOUS = "<more than one Stack profile item>"
_SHARED_SCRIPTS = str(Path(__file__).resolve().parents[1])
_ITEM_RE = re.compile(r"Stack profile:", re.IGNORECASE)
_ITEM_VALUE_RE = re.compile(r"Stack profile:\s*([^;)]+)", re.IGNORECASE)
_NAME_SHAPE = re.compile(r"[a-z0-9][a-z0-9-]*")
# C0 and C1 controls, zero-width / bidi marks, bidi overrides and isolates, BOM: written as escapes on purpose
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]")


def _plain(text: Any) -> str:
    """A resolver message made safe to print: no control characters, bounded length."""
    return _CTRL_RE.sub(" ", str(text))[:300]


def _trailer_item(desc: str) -> tuple[str, Any]:
    """``(kind, value)`` for the WebUI ``(Intake ...)`` trailer: the last one, ending the text."""
    items = len(_ITEM_RE.findall(desc))
    start = desc.rfind("(Intake")
    if start < 0 or not items:
        return "", None
    if desc.count("(Intake") > 1 or items > 1:
        return "ambiguous", AMBIGUOUS
    tail = desc[start:]
    match = _ITEM_VALUE_RE.search(tail)
    if not match or not tail.rstrip().endswith(")"):
        return "", None
    return "strict", match.group(1).strip().removesuffix(".").strip()


def requested(raw: Any) -> tuple[str, Any]:
    """``(kind, value)``: kind is ``""`` (none), ``strict``, ``hint`` or ``ambiguous``. ``value`` may be a non-string."""
    if not isinstance(raw, dict):
        return "", None
    blank = False
    for key in (*FIELDS, "profile_hint"):
        value = raw.get(key)
        if value is None:
            continue  # absent: look at the next field
        if isinstance(value, str) and not value.strip():
            blank = True  # present but blank = no choice made here; the next field may still name one
            continue
        return ("hint" if key == "profile_hint" else "strict"), value.strip() if isinstance(value, str) else value
    desc = raw.get("description")
    if blank or not isinstance(desc, str):
        return "", None  # a blank field means the prose trailer is NOT consulted either
    return _trailer_item(desc)


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


def _error(name: Any, code: str, detail: Any) -> dict:
    msg = f"the brief names stack profile {_plain(name)!r}, which cannot be used ({code}): {_plain(detail)}"
    return {
        "profile": None,
        "reason": f"brief names profile {_plain(name)!r}, which cannot be used -> NOT replaced by another profile",
        "extra": {"profile_requested": _plain(name), "profile_error": {"code": code, "message": msg},
                  "warnings": [msg], "refused": True, "code": "profile_unusable", "message": msg, "issues": []},
    }


def _ignored(value: Any) -> dict:
    """A bare ``profile:`` hint that was NOT used: no override (inference stays), but never silent."""
    msg = (f"the line 'profile: {_plain(value)}' was not used as a stack profile, so the profile is inferred from "
           "the answers; to name a stack write 'Stack profile: <name>'")
    return {"extra": {"warnings": [msg]}}


def select(raw: Any, project_root: Any = ".") -> Optional[dict]:
    """None when the brief names no profile, else ``{profile, reason, extra}`` for ``map_brief``
    (an unused hint: ``{extra}`` only, so inference stays and only a warning is added)."""
    kind, name = requested(raw)
    if not kind:
        return None
    if kind == "ambiguous":
        return _error(name, "invalid", "give exactly one Stack profile item (or a profile field)")
    if kind == "hint" and not (isinstance(name, str) and _NAME_SHAPE.fullmatch(name) and name != "detecting"):
        return _ignored(name)  # free text that happens to start with "profile:" is not a choice
    if not isinstance(name, str):
        return _error(name, "invalid", "a profile must be given as a name (string)")
    if name.lower() == "detecting":  # a placeholder state ("detect later"), not a stack a brief can choose
        return _error(name, "invalid", "'detecting' is a reserved placeholder, not a stack profile")
    try:
        res = _resolver().resolve_profile(name, project_root)
    except ValueError as exc:  # the resolver's error family: not_found / invalid / schema_*
        if kind == "hint" and getattr(exc, "kind", "") == "not_found":
            return _ignored(name)  # a hint the resolver does not know is prose, not a typo to refuse
        return _error(name, getattr(exc, "kind", "error"), exc)  # _error prints it sanitized
    except Exception as exc:  # missing resolver tree or any unexpected failure: loud, never a silent inference
        return _error(name, "resolver_unavailable", exc)
    return {
        "profile": res.name,
        "reason": f"brief names profile {res.name!r} ({res.source}): explicit value wins over inference",
        "extra": {"profile_requested": name, "profile_source": res.source,
                  "warnings": [_plain(w) for w in res.warnings]},
    }
