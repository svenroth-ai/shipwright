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
    "render_user_prompt_as_stdin_refs",
    "select_mode_input",
    "strip_prior_review_sections",
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


#: Headings the architecture pass must never see (Stage-3 doubt review, high).
#: On the plan side the anchoring defense holds by construction — the internal
#: passes write to `plan.md`, never `spec.md`. On the iterate side there is no
#: second document: these same headings land in the ONE spec file this mode is
#: handed as `--spec-file`, each carrying exactly the rejection rationale the
#: brief was built to withhold.
_PRIOR_REVIEW_SECTION_RE = re.compile(
    r"^## (?:Internal Plan Review|Internal Architecture Review|Self-Review|"
    r"Architecture Review)\b.*?(?=\n## |\Z)",
    re.MULTILINE | re.DOTALL,
)

#: A fenced code block (``` or ~~~, either length) start-to-end. Matched only
#: to MASK its interior before the section regex runs — a spec that quotes a
#: template or a skill excerpt containing a line like "## Internal Plan
#: Review" must not have that quoted line mistaken for a real section
#: boundary (external review, medium — both `glm` and `openai` legs raised
#: this independently against this exact regex).
#:
#: Deliberately NOT a backreference (`^\1\s*$`) on the closer: CommonMark
#: allows a closing fence at least as long as the opener (` ``` ` opened,
#: `` ```` `` closed is valid), and a backreference demands an exact-length
#: match — the opener's own capture, followed by a stray extra backtick that
#: `\s*$` then rejects — so a longer closer is never recognized as a close at
#: all and the whole block goes unmasked (external review round 2, medium,
#: both legs converged on the same regex again). Any 3+-backtick-or-tilde
#: line closes any 3+-backtick-or-tilde opener: type/length-exact matching
#: is CommonMark's job, not this masker's — treating a not-quite-matching
#: pair as fenced errs toward over-masking, never toward leaving a real
#: section boundary hidden inside unmasked "quoted" text.
_FENCE_RE = re.compile(
    r"^(?:`{3,}|~{3,}).*?^(?:`{3,}|~{3,})[ \t]*$", re.MULTILINE | re.DOTALL
)


def _mask_fenced_blocks(text: str) -> str:
    """Replace every character inside a fenced code block with a space,
    preserving newlines and overall length so match offsets computed on the
    masked text still index correctly into the original."""
    return _FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def strip_prior_review_sections(spec_text: str) -> str:
    """Remove sections that would leak a prior reviewer's verdict/rationale
    into the architecture pass's `{SPEC}` input — a code-level backstop for
    the anchoring defense prose already asks the iterate skill to honor.

    Section boundaries are located against a fence-masked copy of the text
    (see `_mask_fenced_blocks`) so a fenced quote of a heading-shaped line
    can never be read as a real section start or end; the located spans are
    then removed from the original, unmasked text."""
    masked = _mask_fenced_blocks(spec_text)
    kept: list[str] = []
    cursor = 0
    for match in _PRIOR_REVIEW_SECTION_RE.finditer(masked):
        kept.append(spec_text[cursor:match.start()])
        cursor = match.end()
    kept.append(spec_text[cursor:])
    return "".join(kept)


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


def render_user_prompt_as_stdin_refs(user_prompt: str) -> str:
    """Like :func:`render_user_prompt`, but every recognized placeholder
    becomes a fixed reference to a stdin block instead of the real
    primary/spec text — for a transport (the Claude CLI leg) that must keep
    untrusted content out of argv entirely. Reuses the same placeholder set
    and unknown-placeholder warning, so a template using ``{DIFF}``/
    ``{PLAN}``/``{BRIEF}``/``{SPEC}`` renders correctly regardless of mode —
    unlike a transport-local, ad-hoc placeholder name that no shipped
    template actually uses.
    """
    def _substitute(match: re.Match) -> str:
        token = match.group(0)
        kind = _SUBSTITUTIONS_FOR.get(token)
        if kind is not None:
            return (
                "(see the <content> block on stdin)" if kind == "primary"
                else "(see the <context> block on stdin)"
            )
        print(
            "warning: external_review prompt template contains unknown "
            f"placeholder {token}",
            file=sys.stderr,
        )
        return token

    return _PLACEHOLDER_RE.sub(_substitute, user_prompt)
