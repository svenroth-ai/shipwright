"""Markdown checks: hidden padding, safety-suppressing instructions, tool scope.

Rules (all advisory, see ``skill_surface_scan``):

* ``SURFACE_WHITESPACE_PADDING`` — a long run of blank lines, or text pushed far
  to the right of a line of spaces, so a human reviewer never sees what the agent
  still reads.
* ``SURFACE_REFUSAL_SUPPRESSION`` / ``SURFACE_DISCLAIMER_SUPPRESSION`` /
  ``SURFACE_SAFETY_NULLIFICATION`` — instructions that tell the agent to never
  decline, to drop warnings, or to treat its safety rules as void.
* ``SURFACE_SKILL_WILDCARD_TOOLS`` — a ``SKILL.md`` whose ``allowed-tools`` grants
  every tool. A *missing* declaration is deliberately not flagged: measured on this
  repo it fired on 13 of 13 skills (none declare one), i.e. no signal.

Part of the advisory ``skill_surface_scan`` package; see its docstring for the
attribution note (categories inspired by NVIDIA SkillSpector, Apache-2.0; rules
re-implemented, no code or text copied).
"""

from __future__ import annotations

import re

PADDING_BLANK_LINES = 25
PADDING_SPACE_RUN = 120

_FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
_INLINE_CODE = re.compile(r"`[^`]*`")
# Any run of blanks, including NBSP / em space / U+3000. A single-class `+` match is linear;
# a pattern like `[ ]{120,}` followed by a text character backtracks quadratically on a long
# run of spaces with nothing after it.
_SPACE_RUN = re.compile(r"[^\S\r\n]+")

# Each entry: (rule, compiled pattern, human label). Matched case-insensitively on prose
# lines only (fenced code and inline code spans are blanked first).
_PHRASES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("SURFACE_REFUSAL_SUPPRESSION",
     # Aimed at the agent's own requests; "a program must not refuse a rollback" is ordinary prose.
     re.compile(r"\b(?:never|do not|don't|must not)\s+(?:ever\s+)?(?:refuse|decline|say no to)\s+(?:to\s+)?"
                r"(?:anything|any\s+\w+|(?:the\s+)?(?:user'?s?\s+)?(?:requests?|tasks?|instructions?|commands?|prompts?|questions?))\b", re.I),
     "tells the agent never to refuse"),
    ("SURFACE_REFUSAL_SUPPRESSION",
     # Needs an addressee: "the service must always comply with GDPR" is ordinary prose.
     re.compile(r"\b(?:you|assistant|agent)\s+(?:must\s+|should\s+|will\s+)?always\s+(?:comply|obey|do\s+(?:as|what)\s+(?:you(?:'re| are)\s+)?(?:told|asked|instructed))\b", re.I),
     "tells the agent to always comply"),
    ("SURFACE_DISCLAIMER_SUPPRESSION",
     # Aimed at the agent's own answers: "remove the disclaimer banner from the footer" is UI prose.
     re.compile(r"\b(?:(?:omit|skip|drop|remove|suppress|strip)\s+(?:any\s+|all\s+|the\s+)?"
                r"(?:safety\s+warnings?|disclaimers?|caveats?|ethical\s+(?:commentary|considerations))"
                r"(?:\s+(?:and|or)\s+(?:safety\s+warnings?|disclaimers?|caveats?))?"
                r"\s+(?:from|in)\s+(?:your|the|every|each|all)\s+(?:answers?|responses?|outputs?|repl(?:y|ies)|messages?)"
                r"|never\s+(?:add|include|give|show)\s+(?:any\s+|all\s+)?"
                r"(?:safety\s+warnings?|disclaimers?|caveats?|ethical\s+(?:commentary|considerations)))\b", re.I),
     "tells the agent to drop disclaimers or safety warnings"),
    ("SURFACE_SAFETY_NULLIFICATION",
     re.compile(r"\b(?:you|agent|assistant)\s+(?:have|has)\s+no\s+(?:restrictions|limits|limitations|rules|guidelines)\b", re.I),
     "declares the agent has no restrictions"),
    ("SURFACE_SAFETY_NULLIFICATION",
     re.compile(r"\bignore\s+(?:your|all|any)\s+(?:safety|content|usage)\s+(?:policy|policies|guidelines|restrictions|rules)\b", re.I),
     "tells the agent to ignore its safety policy"),
    ("SURFACE_SAFETY_NULLIFICATION",
     re.compile(r"\b(?:bypass|disable|override|turn off)\s+(?:your\s+|the\s+|all\s+)?(?:safety|content)\s+(?:filters?|policy|policies|guardrails?|checks?)\b", re.I),
     "tells the agent to disable its safety filters"),
)

_WILDCARD = re.compile(r"""(?:^|[\s,\[\-"'])(?:\*|all|bash\(\*\)|bash\(\*:\*\))(?:$|[\s,\]"'])""", re.I)


def _blank_code(lines: list[str]) -> list[str]:
    """Copy of ``lines`` with fenced blocks emptied and inline code spans blanked."""
    out: list[str] = []
    in_fence = False
    for raw in lines:
        if _FENCE.match(raw):
            in_fence = not in_fence
            out.append("")
        elif in_fence:
            out.append("")
        else:
            out.append(_INLINE_CODE.sub("", raw))
    return out


def _scan_padding(lines: list[str], emit) -> None:
    run_start = 0
    run_len = 0
    code = _blank_code(lines)  # ASCII art / aligned comments inside a fence are not hidden text
    for line_no, raw in enumerate(lines, 1):
        if not raw.strip():
            if run_len == 0:
                run_start = line_no
            run_len += 1
            continue
        if run_len >= PADDING_BLANK_LINES:
            _emit_padding(emit, run_start, f"{run_len} consecutive blank lines")
        run_len = 0
        if _has_padded_text(code[line_no - 1]):
            _emit_padding(emit, line_no, f"text after a run of {PADDING_SPACE_RUN}+ spaces")


def _has_padded_text(raw: str) -> bool:
    """True when real text follows a run of PADDING_SPACE_RUN+ blanks on one line.

    Linear in the line length (see ``_SPACE_RUN``). An aligned Markdown table row (starts and
    ends with ``|``) is column padding, not hidden content.
    """
    stripped = raw.strip()
    # A table row is checked cell by cell: alignment padding trails a cell, hidden text follows a run.
    cells = raw.split("|") if stripped.startswith("|") and stripped.endswith("|") else [raw]
    return any(
        len(run.group()) >= PADDING_SPACE_RUN and run.end() < len(cell.rstrip())
        for cell in cells
        for run in _SPACE_RUN.finditer(cell)
    )


def _emit_padding(emit, line_no: int, what: str) -> None:
    emit(
        "medium",
        "SURFACE_WHITESPACE_PADDING",
        f"Whitespace padding ({what}) can push content out of a reviewer's view while "
        f"the agent still reads it.",
        line_no,
        "Remove the padding and read what follows it.",
    )


def _scan_phrases(lines: list[str], emit) -> None:
    for line_no, raw in enumerate(_blank_code(lines), 1):
        if not raw.strip():
            continue
        for rule, pattern, label in _PHRASES:
            if pattern.search(raw):
                emit(
                    "medium",
                    rule,
                    f"Instruction {label}. Safety-suppressing wording in a skill or agent "
                    f"file is how a skill removes the agent's ability to say no.",
                    line_no,
                    "Remove the wording. (The in-file allow marker does not apply to agent configuration files.)",
                )
                break


def _frontmatter(lines: list[str]) -> list[str] | None:
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index]
    return None


def _scan_skill_tools(lines: list[str], emit) -> None:
    parsed = _frontmatter(lines)
    if parsed is None:
        return
    for offset, raw in enumerate(parsed):
        if re.match(r"^(?:allowed[-_]tools|tools)\s*:", raw, re.I):
            value = raw.split(":", 1)[1]
            # YAML block list: gather the indented "- item" lines that follow.
            for follow in parsed[offset + 1:]:
                if not re.match(r"^(?:\s+\S|-)", follow):
                    break
                value += " " + follow
            if _WILDCARD.search(value):
                emit(
                    "medium",
                    "SURFACE_SKILL_WILDCARD_TOOLS",
                    "The tool grant ('allowed-tools' / 'tools') covers every tool (wildcard), so the "
                    "scope is unbounded.",
                    offset + 2,
                    "List only the tools the skill needs.",
                )
            break


def scan_prose(text: str, emit, agent_surface: bool) -> None:
    """Markdown checks. Padding runs on every Markdown file; the safety-wording and
    tool-scope rules run only on agent surfaces (SKILL.md, agents/, commands/, ...), because
    ordinary product prose ("the service must always comply with GDPR") is full of look-alikes.

    Known blind spots: instructions inside a fenced code block or inline code span are not
    matched (blanked to keep documentation of the patterns quiet), and phrases are matched per
    line, so a sentence hard-wrapped across two lines is missed.
    """
    lines = text.splitlines()
    _scan_padding(lines, emit)
    if agent_surface:
        _scan_phrases(lines, emit)
        _scan_skill_tools(lines, emit)
