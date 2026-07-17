"""Canonical-shape gate for the always-loaded agent-doc changelog sections.

Companion to ``agent_doc_budget`` (which governs LENGTH) — this module governs
SHAPE. The two ``…Updates`` changelog sections carry one bullet per change; the
user-visible inconsistency was that the SAME change flip-flopped between a run_id
anchor (hand-written at iterate F2) and a duplicate ``ADR-NNN`` anchor
(blind-appended by the release aggregator), plus stray ``Campaign …`` /
``sub_iterate-…`` / free-text anchors. The aggregator no longer dups (see
``aggregate_decisions.run_id_documented_for_impact`` guard); this gate keeps every
NEW dated bullet well-formed so the drift cannot creep back:

    - **<anchor>** (YYYY-MM-DD): <Impact> — <sentence>. → <pointer>

where ``<anchor>`` is a run_id (``iterate-YYYY-MM-DD-slug``, the F2 form) OR an
``ADR-NNN`` (the direct build/plan/… ``write_decision_log`` path — a single,
non-dup entry, now emitted in this same canonical form). Anchors that are neither
(Campaign, sub_iterate, a free-text title) are rejected.

Scope: only the TWO ``…Updates`` sections are shape-governed. ``## Learnings``
(conventions.md) uses a different date-first grammar
(``- (YYYY-MM-DD) <phase> — <rule>. → …``) and is deliberately excluded — its
length is still covered by ``agent_doc_budget``.

All functions are pure (no I/O); the CLI / F11 verifier own the git + file reads.
Reuses ``agent_doc_budget.iter_entries`` / ``entry_date`` / ``entry_anchor`` so
entry parsing, the date cutoff, and the forward-only anchor-diff match the budget
gate exactly.
"""

from __future__ import annotations

import re
from datetime import date

from .agent_doc_budget import entry_anchor, entry_date, iter_entries

# The date the run_id canonical form stabilized. Dated entries on/after this are
# shape-enforced; earlier + undated entries are grandfathered legacy (the deep
# ``→ archive`` residue and the pre-cutoff bare ``ADR-NNN`` / ``Campaign`` lines).
ENFORCED_FROM = date(2026, 6, 28)

# The two changelog sections whose bullets carry the canonical anchor grammar.
# ``## Learnings`` (conventions.md) is intentionally NOT here (date-first grammar).
SHAPE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("architecture.md", "## Architecture Updates"),
    ("conventions.md", "## Convention Updates"),
)

# Canonical head: a run_id (iterate-YYYY-MM-DD-slug) or ADR-NNN anchor, a bare
# parenthesised date, then ": ". Campaign / sub_iterate / free-text anchors fail.
_CANON_HEAD = re.compile(
    r"^- \*\*(?:iterate-\d{4}-\d{2}-\d{2}-[a-z0-9-]+|ADR-\d{3,4})\*\* "
    r"\(\d{4}-\d{2}-\d{2}\): "
)
_IMPACT_SEP = " — "  # "<Impact> — <sentence>" (em-dash, U+2014)
# The pointer must resolve to a real target — a bare arrow ("→ anything") is not
# enough (external-review OpenAI #1). Accepts "→ decision_log (…)" / "→ archive".
_POINTER_RE = re.compile(r"→\s*(?:decision_log|archive)")


def is_canonical(entry: str) -> bool:
    """True iff ``entry``'s bullet matches the canonical changelog grammar.

    Checks the first line's ``anchor (date):`` head, an ``<Impact> — `` separator
    in the body, and a ``→`` pointer somewhere in the entry. Shape only — it does
    NOT judge whether the sentence is a good summary.
    """
    first = entry.splitlines()[0] if entry else ""
    if not _CANON_HEAD.match(first):
        return False
    body = first.split("): ", 1)[1] if "): " in first else ""
    if _IMPACT_SEP not in body:
        return False
    return _POINTER_RE.search(entry) is not None


# ``architecture_impact`` → the display word in "<Impact> — …".
_IMPACT_WORD = {"component": "Component", "data-flow": "Data-flow", "convention": "Convention"}


def render_canonical_bullet(
    anchor: str, entry_date: str, impact: str, summary: str, pointer: str
) -> str:
    """Render a canonical changelog bullet — the form ``is_canonical`` accepts.

    SSoT for producing (not just validating) the grammar, so the direct
    ``write_decision_log`` path emits exactly what the gate enforces. Collapses ALL
    whitespace (incl. embedded newlines) to single spaces so a multi-line summary
    can't inject a second Markdown bullet, and strips a trailing period so we never
    emit "…thing.." before the arrow (external-review OpenAI #5). ``impact`` outside
    the three canonical values renders verbatim.
    """
    impact_word = _IMPACT_WORD.get(impact, impact)
    sentence = " ".join(summary.split()).rstrip(".").strip()
    return f"- **{anchor}** ({entry_date}): {impact_word} — {sentence}. → {pointer}"


def _fmt(entry: str) -> str:
    return entry.splitlines()[0][:100] if entry else "(empty)"


def non_canonical(
    entries: list[str], enforced_from: date | None = ENFORCED_FROM
) -> list[str]:
    """Dated entries on/after ``enforced_from`` that are not canonical.

    Undated + pre-cutoff entries are grandfathered (skipped). Full-corpus variant
    — used by the monorepo pytest to keep the whole doc clean after the one-time
    normalization.
    """
    bad: list[str] = []
    for e in entries:
        d = entry_date(e)
        if d is None:
            continue
        if enforced_from is not None and d < enforced_from:
            continue
        if not is_canonical(e):
            bad.append(_fmt(e))
    return bad


def new_non_canonical(
    current_text: str,
    base_text: str,
    section_header: str,
    enforced_from: date | None = ENFORCED_FROM,
) -> list[str]:
    """Forward-only: entries new-by-anchor vs ``base_text`` that are not canonical.

    Repo-agnostic — a legacy non-canonical entry the author did not touch is never
    flagged; only a NEW or anchor-changed dated bullet on/after ``enforced_from``
    must be canonical. Mirrors ``agent_doc_budget.new_over_budget``, so a
    compacting edit that keeps the anchor is not seen as new.
    """
    base_anchors = {entry_anchor(e) for e in iter_entries(base_text, section_header)}
    bad: list[str] = []
    for e in iter_entries(current_text, section_header):
        if entry_anchor(e) in base_anchors:
            continue
        d = entry_date(e)
        if d is None:
            continue
        if enforced_from is not None and d < enforced_from:
            continue
        if not is_canonical(e):
            bad.append(_fmt(e))
    return bad
