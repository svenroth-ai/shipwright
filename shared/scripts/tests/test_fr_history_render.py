"""The renderer: wrapping, and what each branch actually prints (campaign S7).

Body text is written as ONE logical string and wrapped at runtime, so the source
carries no hand-managed line breaks. ``_wrap`` and ``_para`` share a single
``_fold`` so two wrapping rules cannot drift apart.

``_render_text`` is driven IN-PROCESS here. The CLI suites drive it through a
subprocess, which exercises it thoroughly but reports no coverage for it — and
when the renderer moved from ``tools/`` (unmeasured) to ``lib/`` (measured) that
showed up as 30% and took the diff-coverage gate below its floor, with nothing
about its behaviour having changed. Driving it directly is both the repair and
the better test: every branch is reachable without spawning a process.

The structural rule that no display literal may look like a missing comma lives
in ``test_fr_history_display_lists.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.fr_history_render import _ascii, _fold, _para, _render_text, _wrap  # noqa: E402

# --------------------------------------------------------------------------
# The wrapping the fix relies on
# --------------------------------------------------------------------------

#: Deliberately uneven word lengths. A uniform "tokenN" corpus breaks at the
#: same points for several nearby widths, so an off-by-N in one of the two
#: wrappers passes unnoticed — which is exactly what the first version of the
#: test below did, and a mutation caught it.
_UNEVEN = (
    "a bb ccc dddd eeeee ffffff ggggggg hhhhhhhh i jj kkk llll mmmmm "
    "nnnnnn ooooooo pppppppp q rr sss tttt uuuuu vvvvvv wwwwwww"
)


def test_fold_breaks_on_words_and_never_loses_one():
    text = " ".join(f"word{i}" for i in range(40))
    out = _fold(text, 30)
    assert len(out) > 1, "the text should have wrapped"
    assert " ".join(out).split() == text.split(), "a word was lost or duplicated"
    assert all(len(line) <= 30 or " " not in line for line in out)


@pytest.mark.parametrize("width", [12, 17, 23, 31, 40, 55])
def test_fold_fills_each_line_as_far_as_the_width_allows(width):
    """The width is a limit, not a suggestion — and it must be pinned exactly.

    ``<=`` alone does not do that: flipping ``_fold``'s ``> width`` to
    ``>= width`` breaks one character early on every line, which satisfies every
    "no line exceeds the width" assertion and survived the whole suite. The
    parity sweep could not see it either, since both wrappers call the same
    ``_fold`` and therefore move together.

    Maximality is the property that actually fixes the boundary: for every line
    but the last, the first word of the NEXT line must genuinely not have fit.
    """
    lines = _fold(_UNEVEN, width)
    assert len(lines) > 1, "the corpus should wrap at this width"

    for current, following in zip(lines, lines[1:]):
        next_word = following.split()[0]
        if len(current) + 1 + len(next_word) <= width:
            raise AssertionError(
                f"width={width}: {next_word!r} would have fitted on "
                f"{current!r} ({len(current) + 1 + len(next_word)} <= {width}) "
                f"but was pushed to the next line — the fold is breaking early."
            )
        if len(current.split()) > 1:
            assert len(current) <= width, (
                f"width={width}: {current!r} exceeds the limit"
            )


def test_fold_of_empty_text_is_empty():
    assert _fold("", 30) == []


def test_a_word_longer_than_the_width_is_kept_whole():
    """Truncating an unbreakable token would corrupt a run id or a URL."""
    out = _fold("short " + "x" * 90, 30)
    assert "x" * 90 in out


def test_para_returns_display_lines_not_a_joined_string():
    out = _para("one two three", width=80)
    assert isinstance(out, list)
    assert out == ["one two three"]


def test_wrap_indents_continuation_lines_for_the_entry_layout():
    out = _wrap(" ".join(f"w{i}" for i in range(40)), width=20)
    assert "\n        " in out, "continuations must align under the entry"
    assert out.split("\n        ")[0].startswith("w0")


@pytest.mark.parametrize("width", [12, 17, 20, 23, 29, 31, 37, 40, 41, 55, 60])
def test_wrap_and_para_share_one_wrapping_rule(width):
    """Two wrapping implementations would drift; both delegate to ``_fold``.

    Swept across widths with unevenly-sized words so an off-by-one in either
    wrapper shows up, rather than only a wholesale rewrite.
    """
    assert _wrap(_UNEVEN, width=width).split("\n        ") == _para(
        _UNEVEN, width=width
    )


# --------------------------------------------------------------------------
# The renderer itself, driven in-process
# --------------------------------------------------------------------------
#
# The CLI tests drive this module through a subprocess, which exercises it but
# reports no coverage for it — the renderer moved from `tools/` (unmeasured)
# into `lib/` (measured), and the diff-coverage gate caught the resulting hole
# at 30%. Driving `_render_text` directly is both the fix and better testing:
# each branch is reachable without spawning a process.

def _history(**kw):
    from lib.fr_change_history import (
        STATUS_FOUND,
        CoverageSummary,
        FrChange,
        FrHistory,
    )
    defaults = dict(
        fr_id="FR-01.01",
        status=STATUS_FOUND,
        changes=(),
        existence_verified=True,
        in_catalog=True,
        corrupt_fragments=0,
        coverage=CoverageSummary(work_events=10, fr_linked_events=4),
    )
    defaults.update(kw)
    ctor = FrHistory(
        defaults["fr_id"], defaults["status"], defaults["changes"],
        defaults["existence_verified"],
        in_catalog=defaults["in_catalog"],
        corrupt_fragments=defaults["corrupt_fragments"],
        coverage=defaults["coverage"],
    )
    return ctor, FrChange


def _change(FrChange, **kw):
    defaults = dict(
        event_id="evt-1", run_id="run-a", ts="2026-01-01T00:00:00+00:00",
        relation="affected", summary="did a thing", commit="", spec_impact="",
    )
    defaults.update(kw)
    return FrChange(**defaults)


def test_render_lists_a_change_with_its_details():
    history, FrChange = _history()
    history = history.__class__(
        history.fr_id, history.status,
        (_change(FrChange, spec_impact="modify", commit="abcdef1234567890"),),
        True, in_catalog=True, corrupt_fragments=0, coverage=history.coverage,
    )
    out = _render_text(history, history.coverage)
    assert "1 recorded change(s), oldest first:" in out
    assert "run-a" in out
    assert "did a thing" in out
    assert "impact=modify" in out
    assert "commit=abcdef123456" in out
    assert "+ introduced this requirement" in out


def test_render_marks_an_introduced_change_differently():
    history, FrChange = _history()
    history = history.__class__(
        history.fr_id, history.status,
        (_change(FrChange, relation="introduced"),),
        True, in_catalog=True, corrupt_fragments=0, coverage=history.coverage,
    )
    assert "  1. + " in _render_text(history, history.coverage)


def test_render_falls_back_when_a_change_has_no_timestamp():
    history, FrChange = _history()
    history = history.__class__(
        history.fr_id, history.status, (_change(FrChange, ts=""),),
        True, in_catalog=True, corrupt_fragments=0, coverage=history.coverage,
    )
    assert "(no date)" in _render_text(history, history.coverage)


def test_render_of_an_empty_history_claims_existence_only_when_verified():
    from lib.fr_change_history import STATUS_NO_CHANGES

    verified, _ = _history(status=STATUS_NO_CHANGES, existence_verified=True)
    out = _render_text(verified, verified.coverage)
    assert "No recorded changes." in out
    assert "This requirement exists" in out

    unverified, _ = _history(status=STATUS_NO_CHANGES, existence_verified=False)
    out = _render_text(unverified, unverified.coverage)
    assert "This requirement exists" not in out
    assert "could NOT be checked" in out
    assert "not checked for existence" in out


def test_render_labels_a_retired_requirement():
    history, FrChange = _history(in_catalog=False)
    history = history.__class__(
        history.fr_id, history.status, (_change(FrChange),),
        True, in_catalog=False, corrupt_fragments=0, coverage=history.coverage,
    )
    assert "not a live requirement" in _render_text(history, history.coverage)


def test_render_reports_coverage_and_points_at_the_commit_log():
    history, _ = _history()
    out = _render_text(history, history.coverage)
    assert "4 of 10 recorded changes name any requirement (40%)." in out
    assert "git log --all --grep" in out


def test_render_of_a_fully_linked_log_omits_the_commit_log_pointer():
    from lib.fr_change_history import CoverageSummary

    full = CoverageSummary(work_events=10, fr_linked_events=10)
    history, _ = _history(coverage=full)
    out = _render_text(history, full)
    assert "git log --all --grep" not in out


def test_render_of_an_empty_log_says_so():
    from lib.fr_change_history import CoverageSummary

    empty = CoverageSummary(work_events=0, fr_linked_events=0)
    history, _ = _history(coverage=empty)
    out = _render_text(history, empty)
    assert "No completed changes are recorded in this tree's event log." in out


def test_render_warns_about_unreadable_fragments():
    history, _ = _history(corrupt_fragments=3)
    out = _render_text(history, history.coverage)
    assert "3 unreadable fragment(s)" in out


def test_render_omits_the_fragment_warning_when_there_are_none():
    history, _ = _history(corrupt_fragments=0)
    assert "unreadable fragment" not in _render_text(history, history.coverage)


def test_ascii_escapes_rather_than_drops_non_ascii():
    """Escaped, not dropped - a mistyped id stays recognisable in the rejection."""
    escaped = _ascii("FR-01.01→")
    assert escaped.isascii()
    assert escaped == "FR-01.01" + chr(92) + "u2192"
    assert _ascii("plain") == "plain"
