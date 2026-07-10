"""Unit tests for ``shared/scripts/lib/agent_doc_budget.py``.

The SSoT parsing + budget helpers for the always-loaded agent-doc append
sections. These prove the gate (a) splits multi-line entries correctly, (b)
extracts the authoring date from BOTH a bare ``(YYYY-MM-DD)`` and a run-id slug
(closing the hole that exempted the bold Learnings format), and (c) discriminates
over-budget from compliant entries in both the date-cutoff and forward-only
diff modes.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.agent_doc_budget import (  # noqa: E402
    CLAUDE_MD_MAX_NEW_LINES,
    ENTRY_MAX_CHARS,
    claude_md_over_growth,
    entry_anchor,
    entry_date,
    iter_entries,
    new_over_budget,
    over_budget,
)


# --- iter_entries -----------------------------------------------------------


def test_iter_entries_splits_top_level_bullets_and_continuations():
    text = (
        "## Architecture Updates\n\n"
        "- **a** (2026-06-13): one\n  continued line\n"
        "- **b** (2026-06-13): two\n\n"
        "## Next\n- **c**: ignored\n"
    )
    entries = iter_entries(text, "## Architecture Updates")
    assert len(entries) == 2
    assert entries[0].startswith("- **a**") and "continued line" in entries[0]
    assert entries[1].startswith("- **b**")


def test_iter_entries_absent_section_returns_empty():
    assert iter_entries("# doc\n\nno section here\n", "## Learnings") == []


# --- entry_date: the hole-closing core --------------------------------------


def test_entry_date_bare_paren():
    assert entry_date("- **x** (2026-06-13): foo") == date(2026, 6, 13)


def test_entry_date_run_id_slug_now_parsed():
    # The format the gate used to EXEMPT — date lives only in the slug.
    assert entry_date("- **a rule** (iterate-2026-06-13-foo-bar)") == date(2026, 6, 13)


def test_entry_date_comma_form_parsed():
    assert entry_date("- **x** (2026-06-11, iterate foo, ADR pending): y") == date(
        2026, 6, 11
    )


def test_entry_date_undated_returns_none():
    assert entry_date("- **x** (ADR-100 file): a rule with no date") is None


def test_entry_date_prose_date_not_in_parens_is_ignored():
    # A date in the rule TEXT (not parenthesised) must not count as authoring date.
    assert entry_date("- a lesson about the 2026-05-29 main-redirect change") is None


def test_entry_date_invalid_date_skipped():
    assert entry_date("- **x** (2026-13-99): bad") is None


# --- entry_anchor -----------------------------------------------------------


def test_entry_anchor_prefers_bold():
    assert entry_anchor("- **iterate-2026-06-13-foo** (2026-06-13): x") == (
        "iterate-2026-06-13-foo"
    )


def test_entry_anchor_falls_back_to_body_head_for_date_lead():
    a = entry_anchor("- (2026-06-13) iterate — some rule about things")
    assert a.startswith("(2026-06-13) iterate")


# --- over_budget (date-cutoff mode) -----------------------------------------


def test_over_budget_flags_dated_oversize():
    big = "- **x** (2026-06-13): " + ("y" * (ENTRY_MAX_CHARS + 50))
    assert over_budget([big])


def test_over_budget_exempts_undated():
    big = "- **x**: " + ("y" * (ENTRY_MAX_CHARS + 50))
    assert over_budget([big]) == []


def test_over_budget_respects_enforced_from():
    big = "- **x** (2026-04-01): " + ("y" * (ENTRY_MAX_CHARS + 50))
    assert over_budget([big], enforced_from=date(2026, 5, 1)) == []
    assert over_budget([big], enforced_from=date(2026, 1, 1))


def test_over_budget_slug_dated_oversize_now_caught():
    # Regression: the bold-lead slug-dated form must now be enforced.
    big = "- **" + ("y" * (ENTRY_MAX_CHARS + 50)) + "** (iterate-2026-06-13-foo)"
    assert over_budget([big])


# --- new_over_budget (forward-only diff mode) -------------------------------


def test_new_over_budget_flags_new_oversize_only():
    header = "## Learnings"
    base = f"{header}\n- **old** (2026-06-01): short\n"
    big = "y" * (ENTRY_MAX_CHARS + 50)
    current = f"{header}\n- **old** (2026-06-01): short\n- **new** (2026-06-13): {big}\n"
    bad = new_over_budget(current, base, header)
    assert len(bad) == 1


def test_new_over_budget_ignores_unchanged_base_oversize():
    header = "## Learnings"
    big = "y" * (ENTRY_MAX_CHARS + 50)
    base = f"{header}\n- **legacy** (2026-01-01): {big}\n"
    current = base  # same oversize entry, untouched
    assert new_over_budget(current, base, header) == []


def test_new_over_budget_ignores_new_but_compliant():
    header = "## Learnings"
    base = f"{header}\n- **old** (2026-06-01): short\n"
    current = base + "- **new** (2026-06-13): a tidy one-line pointer\n"
    assert new_over_budget(current, base, header) == []


# --- claude_md_over_growth (CLAUDE.md net-growth rule) -----------------------


def _lines(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(n))


def test_claude_md_growth_over_cap_flags():
    base = _lines(10)
    current = _lines(10 + CLAUDE_MD_MAX_NEW_LINES + 1)
    bad = claude_md_over_growth(current, base)
    assert len(bad) == 1
    assert f"+{CLAUDE_MD_MAX_NEW_LINES + 1}" in bad[0]


def test_claude_md_growth_exactly_at_cap_clean():
    base = _lines(10)
    current = _lines(10 + CLAUDE_MD_MAX_NEW_LINES)
    assert claude_md_over_growth(current, base) == []


def test_claude_md_growth_shrink_and_equal_clean():
    assert claude_md_over_growth(_lines(5), _lines(50)) == []
    assert claude_md_over_growth(_lines(50), _lines(50)) == []


def test_claude_md_growth_crlf_parity():
    # Same logical content with CRLF endings must not count as growth.
    base = _lines(40)
    current = base.replace("\n", "\r\n")
    assert claude_md_over_growth(current, base) == []


def test_claude_md_growth_trailing_newline_only_clean():
    base = _lines(40).rstrip("\n")
    current = base + "\n"
    assert claude_md_over_growth(current, base) == []


def test_claude_md_growth_custom_cap():
    assert claude_md_over_growth(_lines(6), _lines(1), max_new_lines=4)
    assert claude_md_over_growth(_lines(5), _lines(1), max_new_lines=4) == []
