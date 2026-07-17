"""Unit tests for the canonical-shape gate (``lib.agent_doc_shape``).

Shape only: a dated changelog bullet on/after the cutoff must be
``- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — <sentence>. → <pointer>``.
Campaign / sub_iterate / free-text anchors and missing Impact/arrow are rejected;
undated + pre-cutoff entries are grandfathered; ``## Learnings`` is out of scope.
"""

from __future__ import annotations

from datetime import date

from lib.agent_doc_shape import (
    ENFORCED_FROM,
    SHAPE_SECTIONS,
    is_canonical,
    new_non_canonical,
    non_canonical,
)

_RUNID = (
    "- **iterate-2026-07-15-foo-bar** (2026-07-16): "
    "Component — did a thing to a module. → decision_log (Run-ID)"
)
_ADR = (
    "- **ADR-042** (2026-07-01): "
    "Convention — direct-path bullet. → decision_log (ADR-042)"
)


def test_canonical_run_id_and_adr_pass():
    assert is_canonical(_RUNID)
    assert is_canonical(_ADR)  # direct build/plan/… path anchor is allowed


def test_campaign_anchor_rejected():
    assert not is_canonical(
        "- **Campaign B1 — modular** (2026-07-01): Component — x. → decision_log (Run-ID)"
    )


def test_sub_iterate_anchor_rejected():
    assert not is_canonical(
        "- **sub_iterate-20260525-211635-B8** (2026-07-01): Component — x. "
        "→ decision_log (Run-ID)"
    )


def test_free_text_anchor_rejected():
    assert not is_canonical(
        "- **Some hand-written title** (2026-07-01): Component — x. → decision_log (Run-ID)"
    )


def test_missing_arrow_pointer_rejected():
    assert not is_canonical(
        "- **iterate-2026-07-01-x** (2026-07-01): Component — no pointer here."
    )


def test_missing_impact_separator_rejected():
    assert not is_canonical(
        "- **iterate-2026-07-01-x** (2026-07-01): no impact word here → decision_log (Run-ID)"
    )


def test_arrow_to_nondecisionlog_pointer_rejected():
    # A bare arrow to something other than decision_log/archive is not a pointer.
    assert not is_canonical(
        "- **iterate-2026-07-01-x** (2026-07-01): Component — thing. → somewhere else"
    )


def test_archive_pointer_accepted():
    assert is_canonical(
        "- **iterate-2026-07-01-x** (2026-07-01): Component — old thing. → archive"
    )


def test_undated_and_precutoff_are_grandfathered():
    undated = "- **Campaign X** modular refactor, no parenthesised date"
    precut = "- **Campaign B1 — x** (2026-05-26): Component — legacy. → decision_log (Run-ID)"
    # Both are non-canonical in shape but exempt by the date filter.
    assert non_canonical([undated, precut], enforced_from=ENFORCED_FROM) == []


def test_dated_ge_cutoff_noncanonical_is_flagged():
    bad = "- **Campaign X** (2026-07-01): did a thing. → decision_log (Run-ID)"
    good = _RUNID
    flagged = non_canonical([bad, good], enforced_from=ENFORCED_FROM)
    assert len(flagged) == 1
    assert "Campaign X" in flagged[0]


def test_new_non_canonical_is_forward_only():
    header = "## Architecture Updates"
    legacy_bad = "- **iterate-2026-07-01-old** (2026-07-01): bad old format no arrow"
    base = f"# a\n\n{header}\n{legacy_bad}\n"
    new_bad = "- **Campaign New** (2026-07-02): still bad. → decision_log (Run-ID)"
    current = f"# a\n\n{header}\n{legacy_bad}\n{new_bad}\n"
    flagged = new_non_canonical(current, base, header)
    # The untouched legacy non-canonical entry is NOT flagged; only the new one.
    assert len(flagged) == 1
    assert "Campaign New" in flagged[0]


def test_learnings_section_is_out_of_shape_scope():
    assert ("conventions.md", "## Learnings") not in SHAPE_SECTIONS
    assert ("architecture.md", "## Architecture Updates") in SHAPE_SECTIONS
    assert ("conventions.md", "## Convention Updates") in SHAPE_SECTIONS
    assert ENFORCED_FROM == date(2026, 6, 28)
