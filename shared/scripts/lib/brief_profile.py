#!/usr/bin/env python3
"""An explicit stack profile named in a wizard brief (campaign brief-driven-run B2b).

``brief_intake.py`` derives the profile from the persistence answer. A brief can also NAME one
(the WebUI Intent Wizard, a user, a project profile). This module finds that name, asks the
stack-profile resolver whether it can be used, and hands ``brief_intake.map_brief`` the answer.

PRECEDENCE (one rule: strict sources always beat the bare hint; an explicit value always beats inference):

1. a JSON field ``profile`` (alias ``stack_profile``; ``profile`` wins, the first present field decides);
2. the ``Stack profile:`` / ``stack_profile:`` line of a ``key: value`` brief (it lands in the same field);
3. the ``Stack profile: <name>`` item of the ``(Intake ...)`` trailer the WebUI writes today
   (``composeNewBrief`` in the WebUI ``IntentWizard/contract.ts``): the LAST ``(Intake`` in the text, which
   must end it. Two trailers, two items in the trailer or two ``Stack profile:`` lines are ambiguous and refused (only the trailer's
   own items count: an idea that says "(Intake forms)" or "stack profile: x" in prose is ignored);
4. ONLY when none of 1-3 exists: a HINT, a bare, unbulleted ``profile: x`` line of a ``key: value`` brief
   (``profile_hint``). Free text uses that word too ("Profile: none", "Profile: dentist SaaS ..."), so a hint
   counts only with the profile-name shape AND a resolver hit; anything else stays prose, is not used, and
   adds a non-blocking ``warnings`` entry (exit 0) that points to ``Stack profile: <name>``.

A strict source that cannot be used is an error (exit 3). A blank strict field means "no choice made":
neither the trailer nor the hint is consulted. A hint is never even looked at when a strict source exists.

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
_INTAKE_RE = re.compile(r"\(Intake", re.IGNORECASE)
_EARLIER_TRAILER_RE = re.compile(r"\(Intake[^()]*Stack profile:", re.IGNORECASE)
_ITEM_VALUE_RE = re.compile(r"Stack profile:[ \t]*([^;)\r\n]+)", re.IGNORECASE)
_NAME_SHAPE = re.compile(r"[a-z0-9][a-z0-9-]*")
# C0 and C1 controls, zero-width / bidi marks, bidi overrides and isolates, BOM: written as escapes on purpose
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]")


def _plain(text: Any) -> str:
    """A resolver message made safe to print: no control characters, bounded length."""
    return _CTRL_RE.sub(" ", str(text))[:300]


def _trailer_item(desc: str) -> tuple[str, Any]:
    """``(kind, value)`` for the WebUI ``(Intake ...)`` trailer: the last one (any case), ending the text.

    Kinds: ``""`` none; ``strict``; ``ambiguous``; ``misplaced`` (the last ``(Intake`` holds a ``Stack profile:``
    item but does not end the text: not a trailer, never used, but reported). Only the trailer's own items count:
    the idea may say "(Intake forms)" or "stack profile: x" in prose. An EARLIER ``(Intake ... Stack profile: ...)``
    is a second trailer: ambiguous. Every pattern here is linear in the text (no nested unbounded span)."""
    last = None
    for last in _INTAKE_RE.finditer(desc):
        pass
    tail = desc[last.start():] if last else ""
    if not _ITEM_RE.search(tail):
        return "", None
    if not tail.rstrip().endswith(")"):
        return "misplaced", None
    if len(_ITEM_RE.findall(tail)) > 1 or _EARLIER_TRAILER_RE.search(desc, 0, last.start()):
        return "ambiguous", AMBIGUOUS
    match = _ITEM_VALUE_RE.search(tail)
    return ("strict", match.group(1).strip().removesuffix(".").strip()) if match else ("", None)


def requested(raw: Any) -> tuple[str, Any]:
    """``(kind, value)``: kind is ``""`` (none), ``strict``, ``hint`` or ``ambiguous``. ``value`` may be a non-string."""
    if not isinstance(raw, dict):
        return "", None
    if raw.get("_dup"):  # two `Stack profile:` lines in a key: value brief
        return "ambiguous", AMBIGUOUS
    trailer, blank = ("", None), False
    for text in (raw.get("description"), raw.get("_text")):  # (3) the last trailer; `_text` = a one-line brief
        trailer = _trailer_item(text) if isinstance(text, str) else ("", None)
        if trailer[0] in _SOURCES:
            break
    if "_text" in raw and trailer[0] in _SOURCES:
        return trailer  # the WebUI one-liner: a key at the start of the line is the idea, the trailer is the choice
    for key in FIELDS:  # (1) JSON field, (2) text `Stack profile:` key: both land in these dict keys
        value = raw.get(key)
        if value is None:
            continue  # absent: look at the next field
        if isinstance(value, str) and not value.strip():
            blank = True  # present but blank = no choice made here; the next field may still name one
            continue
        value = value.strip() if isinstance(value, str) else value
        if "_dup" in raw and trailer[0] == "strict" and trailer[1] != value:
            return "ambiguous", AMBIGUOUS  # a text key and a trailer disagree: never pick one silently
        return "strict", value
    if not blank and trailer[0] in _SOURCES:
        return trailer
    hint = raw.get("profile_hint")
    if blank or not isinstance(hint, str) or not hint.strip():
        return "", None  # a blank strict field means no choice: neither trailer nor hint is consulted
    return "hint", hint.strip()  # (4) only when no strict source exists, so a hint can never mask one


_SOURCES = ("strict", "ambiguous")


_ALLOWED_KEYS = {"profile", "stack_profile", "profile_hint", "_text", "_dup"}


def _stray_keys(raw: Any) -> list:
    """Top-level keys that look like a profile field but are not one (``stackProfile``): reported, never an alias."""
    if not isinstance(raw, dict):
        return []
    return [_plain(k) for k in raw if isinstance(k, str) and "profile" in k.lower() and k not in _ALLOWED_KEYS]


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
    said = f"resolver said (untrusted): {_plain(detail)}" if isinstance(detail, Exception) else _plain(detail)
    msg = f"the brief names stack profile {_plain(name)!r}, which cannot be used ({code}): {said}"
    return {
        "profile": None,
        "reason": f"brief names profile {_plain(name)!r}, which cannot be used -> NOT replaced by another profile",
        "extra": {"profile_requested": _plain(name), "profile_error": {"code": code, "message": msg},
                  "warnings": [msg], "refused": True, "code": "profile_unusable", "message": msg, "issues": []},
    }


def _ignored(value: Any) -> dict:
    """A bare ``profile:`` hint that was NOT used: no override (inference stays), but never silent."""
    msg = (f"the line 'profile: {_plain(value)}' is not a usable stack profile, so it was ignored and the brief names "
           "none: the profile comes from the other answers (persistence) or stays undecided; to name a stack "
           "write 'Stack profile: <name>'")
    return {"extra": {"warnings": [msg]}}


def _select(raw: Any, project_root: Any) -> Optional[dict]:
    """None when the brief names no profile, else ``{profile, reason, extra}`` for ``map_brief``
    (an unused hint: ``{extra}`` only, so inference stays and only a warning is added)."""
    kind, name = requested(raw)
    if not kind:
        return None
    if kind == "ambiguous":
        return _error(name, "invalid", "the brief names more than one stack profile (several Stack profile lines or "
                                    "items, or two Intake trailers); give exactly one")
    if kind == "hint" and not (isinstance(name, str) and _NAME_SHAPE.fullmatch(name) and name != "detecting"):
        return _ignored(name)  # free text that happens to start with "profile:" is not a choice
    if not isinstance(name, str):
        return _error(name, "invalid", "a profile must be given as a name (string)")
    if name.lower() == "detecting":  # a placeholder state ("detect later"), not a stack a brief can choose
        return _error(name, "invalid", "'detecting' is a reserved placeholder, not a stack profile")
    try:
        res = _resolver().resolve_profile(name, project_root)
    except ValueError as exc:  # the resolver's error family: not_found / invalid / schema_*
        if kind == "hint":
            return _ignored(name)  # whatever the resolver says of a bare hint (unknown, bad name, broken file): prose, warn
        return _error(name, getattr(exc, "kind", "error"), exc)  # _error prints it sanitized
    except Exception as exc:  # missing resolver tree or any unexpected failure: loud, never a silent inference
        if kind == "hint":
            return _ignored(name)  # an OS error on a profile directory must not refuse a mere hint
        return _error(name, "resolver_unavailable", exc)
    return {
        "profile": res.name,
        "reason": f"brief names profile {res.name!r} ({res.source}): explicit value wins over inference",
        "extra": {"profile_requested": name, "profile_source": res.source,
                  "warnings": [_plain(w) for w in res.warnings]},
    }


def _misplaced(raw: Any) -> bool:
    """A ``Stack profile:`` item in an ``(Intake`` part that does not end the text: tolerated (never used), but said."""
    texts = (raw.get("description"), raw.get("_text")) if isinstance(raw, dict) else ()
    return any(isinstance(t, str) and _trailer_item(t)[0] == "misplaced" for t in texts)


def select(raw: Any, project_root: Any = ".") -> Optional[dict]:
    """``_select`` plus non-blocking warnings: a misplaced trailer, a stray profile-looking JSON key (``stackProfile``)."""
    res = _select(raw, project_root)
    notes = []
    if _misplaced(raw):
        notes.append("a 'Stack profile:' item sits in an '(Intake ...' part that does not end the brief, so it is not the "
                     "wizard trailer and was ignored; to name a stack write 'Stack profile: <name>'")
    stray = _stray_keys(raw)
    if stray:
        notes.append(f"the key(s) {', '.join(map(repr, stray))} are not a profile field and were ignored; use `profile`")
    if notes:
        res = res or {"extra": {}}
        res["extra"].setdefault("warnings", []).extend(notes)
    return res
