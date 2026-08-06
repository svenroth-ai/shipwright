"""What each external-review mode reads, and how its prompt renders.

Split out of ``tools/external_review.py`` when the architecture mode pushed that
file 93 lines past its baseline. The two halves are genuinely separable: the CLI
owns *talking to providers and assembling the envelope*, this module owns *which
input a mode takes and what the template becomes*. The dependency runs one way.

Both rules here are load-bearing rather than clerical, and each exists because
the obvious implementation was wrong in a way nothing surfaced:

* **One input flag per mode, and a foreign flag is an error.** Architecture mode
  earns a different answer from the same two models only because it is handed a
  short brief instead of the plan. A silently-dropped ``--plan-file`` would leave
  a successful-looking run whose reviewer read the very document the mode exists
  to withhold, with a byte-identical envelope.
* **Substitution is ONE pass over the template.** Chained ``str.replace`` rescans
  what the previous call produced.
"""

from __future__ import annotations

import re
import sys
from typing import Any

__all__ = [
    "BLANK_CHARS",
    "KNOWN_PLACEHOLDERS",
    "MODE_INPUT",
    "ModeInputError",
    "is_blank",
    "render_user_prompt",
    "select_mode_input",
]

#: Mode → (input flag, dest attribute, human label). One row per mode, so a new
#: mode cannot be added without deciding what it reads.
#:
#: ``plan`` and ``iterate`` deliberately SHARE ``plan_file``: they read the same
#: kind of document (a plan) and differ only in prompt. The foreign-flag check
#: keys on the dest, not the mode, so neither rejects the other's flag.
MODE_INPUT: dict[str, tuple[str, str, str]] = {
    "plan": ("--plan-file", "plan_file", "Plan"),
    "iterate": ("--plan-file", "plan_file", "Plan"),
    "code": ("--diff-file", "diff_file", "Diff"),
    "architecture": ("--brief-file", "brief_file", "Brief"),
}

#: Placeholder → which argument fills it. ``{PLAN}`` / ``{DIFF}`` / ``{BRIEF}``
#: all take the mode's primary input; whichever token the active template uses
#: wins and the others simply never appear in it.
_SUBSTITUTIONS_FOR = {
    "{PLAN}": "primary", "{DIFF}": "primary", "{BRIEF}": "primary",
    "{SPEC}": "spec",
}
KNOWN_PLACEHOLDERS = tuple(_SUBSTITUTIONS_FOR)

_PLACEHOLDER_RE = re.compile(r"\{[A-Z][A-Z_]*\}")

#: Whitespace plus the invisible characters an "empty" file can still carry: a
#: UTF-8 BOM and a zero-width space. Neither is ``str.isspace()``, so a bare
#: ``.strip()`` reads them as content — and PowerShell 5.1's
#: ``Set-Content -Encoding UTF8 ""`` writes exactly BOM+CRLF.
BLANK_CHARS = " \t\r\n\v\f﻿​"


class ModeInputError(ValueError):
    """The mode's input flags are wrong. Carries the operator-facing message."""


def is_blank(text: str) -> bool:
    """True when ``text`` holds nothing a reviewer could read."""
    return not text.strip(BLANK_CHARS)


def select_mode_input(mode: str, args: Any) -> tuple[str, str]:
    """Return ``(value, human_label)`` for ``mode``'s input flag.

    Raises :class:`ModeInputError` when a flag belonging to a DIFFERENT mode was
    passed, or when this mode's own flag is missing — in that order. The order is
    the point: the likeliest real mistake is typing ``--plan-file`` where
    ``--brief-file`` was meant, and diagnosed the other way round the operator is
    told only "--brief-file is required", which is true and says nothing about
    the plan they just handed an architecture review.
    """
    flag, dest, label = MODE_INPUT[mode]
    for other_mode, (other_flag, other_dest, _) in MODE_INPUT.items():
        if other_dest != dest and getattr(args, other_dest, None):
            raise ModeInputError(
                f"{other_flag} belongs to --mode {other_mode}; --mode {mode} "
                f"reads {flag} and nothing else"
            )
    value = getattr(args, dest, None)
    if not value:
        raise ModeInputError(f"{flag} is required for --mode {mode}")
    return value, label


def render_user_prompt(user_prompt: str, primary: str, spec: str) -> str:
    """Substitute placeholders into ``user_prompt`` in ONE pass.

    A chain of ``str.replace`` calls looks equivalent and is not: each call scans
    the string the previous one produced, so a token appearing *inside* the
    injected text is substituted again by a later call. Measured:
    ``('Diff:\\n{DIFF}', 'a{BRIEF}b')`` rendered ``'Diff:\\naa{BRIEF}bb'`` — the
    whole diff duplicated AND a literal placeholder leaking into the prompt. The
    same flaw let primary content bearing ``{SPEC}`` splice the spec into the
    middle of a diff. Both close here.

    An unknown placeholder warns on stderr, so adding a mode without updating
    :data:`_SUBSTITUTIONS_FOR` is noisy. It fires on the TEMPLATE only — injected
    content carrying a literal placeholder is not a false positive, and that
    separation is structural rather than a second loop over the rendered output.
    """
    def _substitute(match: re.Match) -> str:
        token = match.group(0)
        kind = _SUBSTITUTIONS_FOR.get(token)
        if kind is not None:
            return primary if kind == "primary" else spec
        print(
            "warning: external_review prompt template contains unknown "
            f"placeholder {token}",
            file=sys.stderr,
        )
        return token

    return _PLACEHOLDER_RE.sub(_substitute, user_prompt)
