"""Envelope grammar for Codex first-prompt activation (R2 — M7).

One shared module for both directions of the first-prompt-embedded closed
grammar an armed Codex activation record is minted from — ``compose()`` (the
terminal helper's own call site, producer) and ``parse()`` (the
``UserPromptSubmit`` hook, consumer of untrusted first-prompt text). Kept in
one module on purpose so the two sides cannot drift.

``parse()`` never raises: its input is the raw text of a live Codex
session's first prompt, which is attacker-influenceable (a pasted log or
README could contain stray text resembling the marker) — any malformed or
ambiguous shape degrades to ``None``, never an exception. Two-or-more
matches in the same text is treated as ambiguous, not resolved by taking the
first. See the iterate spec's Design Notes (R2, M3 campaign) for the full
contract this module implements verbatim."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass

_SKILL_ID_CHARS = r"[A-Za-z0-9_.:/-]+"
_ARGS_B64_CHARS = r"[A-Za-z0-9_-]*"
_SKILL_ID_RE = re.compile(rf"^{_SKILL_ID_CHARS}\Z")
_MARKER_RE = re.compile(
    rf"\[SHIPWRIGHT-CODEX-ACTIVATE-v1\|skill_id=({_SKILL_ID_CHARS})\|args_b64=({_ARGS_B64_CHARS})\]"
)


@dataclass(frozen=True)
class Envelope:
    skill_id: str
    args: dict


def _b64_encode_args(args: dict) -> str:
    if not args:
        return ""
    payload = json.dumps(args, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64_decode_args(args_b64: str) -> dict | None:
    if not args_b64:
        return {}
    padded = args_b64 + "=" * (-len(args_b64) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded)
        decoded = json.loads(payload.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def compose(skill_id: str, args: dict) -> str:
    """Render the literal wire form for ``skill_id``/``args``. Raises
    ``ValueError`` on an invalid ``skill_id`` — this side is
    programmer-controlled (the terminal helper's own call site), so failing
    loudly here is correct; only ``parse()``'s input is untrusted."""
    if not _SKILL_ID_RE.match(skill_id):
        raise ValueError(f"invalid skill_id: {skill_id!r}")
    return f"[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id={skill_id}|args_b64={_b64_encode_args(args)}]"


def parse(prompt_text: str) -> Envelope | None:
    """Recognize the envelope inside a live Codex session's first-prompt
    text (the marker may sit inside a larger prompt). Never raises: any
    malformed, ambiguous, or absent shape returns ``None``."""
    try:
        matches = list(_MARKER_RE.finditer(prompt_text))
    except TypeError:
        return None

    if len(matches) != 1:
        return None

    skill_id, args_b64 = matches[0].group(1), matches[0].group(2)
    args = _b64_decode_args(args_b64)
    if args is None:
        return None

    return Envelope(skill_id=skill_id, args=args)
