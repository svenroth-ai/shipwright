"""Budget + parsing helpers for the always-loaded agent docs.

Single source of truth for the "one-line pointer" rule on the three append
sections — ``## Architecture Updates`` / ``## Convention Updates``
(architecture.md / conventions.md) and ``## Learnings`` (conventions.md).

These docs are always-loaded Layer-1 context: every line costs tokens on every
future iterate, so each entry must be a one-line "what + pointer", not a
paragraph. The rule used to be enforced only by a monorepo pytest with a
date-regex hole (the bold ``- **rule** (iterate-…-slug)`` Learnings form carried
its date only inside the run-id slug, so it parsed as "undated" and was exempt).
This module makes the rule a repo-agnostic, hole-free SSoT consumed by:

- ``plugins/shipwright-iterate/tests/test_agent_doc_entry_rules.py`` — monorepo
  full-corpus, date-cutoff check;
- ``shared/scripts/tools/check_agent_doc_budget.py`` — repo-agnostic CLI
  (forward-only vs a git base, or full-corpus);
- ``verify_iterate_finalization.check_agent_doc_budget`` — the F11 gate, which
  ships to adopted repos via the plugin cache and so enforces in webui too.

All functions are pure (no I/O); the CLI / verifier own the git + file reads.
"""

from __future__ import annotations

import re
from datetime import date

# One-line "what + pointer". 600 chars ≈ a self-contained sentence plus a key
# surface path and an ADR pointer — generous vs. the typical ~100-300 char
# compact entry, tight enough to forbid the multi-hundred-word paragraphs.
ENTRY_MAX_CHARS = 600

# CLAUDE.md net-growth cap per iterate. CLAUDE.md has no stable entry grammar
# to parse (DO-NOT blocks are free-form prose), so whole-file net growth is the
# enforceable proxy: 30 lines admits a legitimate new section (~20-26 lines,
# e.g. the plain-language-questions rule) but blocks the multi-hundred-line
# inline-rationale dumps that bloated adopted repos' CLAUDE.md files.
CLAUDE_MD_MAX_NEW_LINES = 30

# (filename, section header) for the three always-loaded append sections.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("architecture.md", "## Architecture Updates"),
    ("conventions.md", "## Convention Updates"),
    ("conventions.md", "## Learnings"),
)

# A date appearing INSIDE parentheses — either bare ``(2026-06-13)`` or embedded
# in a run-id slug ``(iterate-2026-06-13-foo)`` / ``(2026-06-11, iterate …)``. The
# run-id ALWAYS carries the date, so matching paren-enclosed dates closes the
# hole that exempted the bold-lead Learnings format. A prose date NOT inside
# parens is ignored on purpose, so a content date deep in the rule text can't
# false-trigger enforcement on an otherwise-undated entry.
_PAREN_DATE_RE = re.compile(r"\([^)]*?(\d{4})-(\d{2})-(\d{2})[^)]*?\)")

# Bold anchor (``**run_id**`` / ``**ADR-NNN**``) used to identify an entry across
# a base→current diff so a re-worded-but-same-entry edit is not seen as "new".
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def iter_entries(text: str, section_header: str) -> list[str]:
    """Yield each top-level ``- `` bullet block under ``section_header``.

    An entry is a top-level ``- `` bullet at column 0 plus its continuation
    lines (deeper indentation / blank lines) up to the next top-level bullet or
    the next ``## `` heading. Returns the joined entry text (trailing whitespace
    stripped) for each entry.
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == section_header:
            start = i + 1
            break
    if start is None:
        return []
    entries: list[str] = []
    cur: list[str] | None = None
    for ln in lines[start:]:
        if ln.startswith("## "):
            break
        if ln.startswith("- "):
            if cur is not None:
                entries.append("\n".join(cur).rstrip())
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        entries.append("\n".join(cur).rstrip())
    return entries


def entry_date(entry: str) -> date | None:
    """First paren-enclosed ``YYYY-MM-DD`` in ``entry`` (bare OR run-id slug).

    Returns ``None`` for a genuinely undated entry (no parenthesised date),
    which the budget gate treats as grandfathered legacy.
    """
    for m in _PAREN_DATE_RE.finditer(entry):
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    return None


def entry_anchor(entry: str) -> str:
    """A stable identity for an entry, for a base→current diff.

    Prefers the bold anchor (``**run_id**`` / ``**ADR-NNN**``); for the date-lead
    Learnings form (``- (2026-06-13) phase — …``) falls back to the first 60
    chars of the bullet body.
    """
    m = _BOLD_RE.search(entry)
    if m:
        return m.group(1).strip()
    body = entry[2:].strip() if entry.startswith("- ") else entry.strip()
    return body[:60]


def _fmt(entry: str, max_chars: int) -> str:
    head = entry.splitlines()[0][:80] if entry else ""
    return f"{len(entry)} chars (> {max_chars}): {head}…"


def over_budget(
    entries: list[str],
    max_chars: int = ENTRY_MAX_CHARS,
    enforced_from: date | None = None,
) -> list[str]:
    """Dated entries exceeding ``max_chars`` (and ``>= enforced_from`` if set).

    Undated entries (no parenthesised date) are exempt — their authoring date is
    unknown, so they are treated as grandfathered legacy.
    """
    bad: list[str] = []
    for e in entries:
        d = entry_date(e)
        if d is None:
            continue
        if enforced_from is not None and d < enforced_from:
            continue
        if len(e) > max_chars:
            bad.append(_fmt(e, max_chars))
    return bad


def claude_md_over_growth(
    current_text: str,
    base_text: str,
    max_new_lines: int = CLAUDE_MD_MAX_NEW_LINES,
) -> list[str]:
    """Net CLAUDE.md line growth above ``max_new_lines`` (forward-only).

    Pure text comparison — the caller owns git resolution, existence checks
    (creation/deletion is not accretion → don't call), and any env override.
    ``splitlines()`` on both sides keeps CRLF/LF and trailing-newline-only
    differences from counting as growth. Shrink or equal never flags.
    """
    growth = len(current_text.splitlines()) - len(base_text.splitlines())
    if growth <= max_new_lines:
        return []
    return [
        f"+{growth} lines net growth (> {max_new_lines}) — CLAUDE.md is "
        f"always-loaded orientation; state each invariant as one line + an ADR "
        f"pointer and move the rationale into the ADR it cites"
    ]


def new_over_budget(
    current_text: str,
    base_text: str,
    section_header: str,
    max_chars: int = ENTRY_MAX_CHARS,
) -> list[str]:
    """Forward-only budget check: entries present in ``current_text`` but not in
    ``base_text`` (by anchor) that exceed ``max_chars``.

    Repo-agnostic — no date cutoff, so a legacy over-budget entry the author did
    not touch is never flagged; only a NEW or anchor-changed over-budget entry
    blocks. (Compacting an existing entry keeps its anchor, so a cleanup edit
    that shrinks an entry is not flagged.)
    """
    base_anchors = {entry_anchor(e) for e in iter_entries(base_text, section_header)}
    bad: list[str] = []
    for e in iter_entries(current_text, section_header):
        if entry_anchor(e) in base_anchors:
            continue
        if len(e) > max_chars:
            bad.append(_fmt(e, max_chars))
    return bad
