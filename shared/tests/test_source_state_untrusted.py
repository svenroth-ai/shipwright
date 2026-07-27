"""Untrusted values cannot forge a stamp — every regression found in review.

Card ``trg-4d5b6a56`` (FR-01.10). The markdown banner is a whitespace-delimited token
line (``Source-State: run=<id> commit=<sha12> clean|uncommitted-changes``), so any value
reaching it is untrusted input. Each class below pins a forgery or mis-read that a
review layer actually found in an earlier implementation of this change — recorded that
way on purpose, so a future edit cannot quietly reintroduce one.

Split from ``test_source_state.py`` (bloat gate).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from source_state import (  # noqa: E402
    BANNER_PREFIX,
    UNKNOWN_RUN,
    SourceState,
    banner_line,
    parse_banner_line,
    safe_commit,
    safe_run_id,
    to_block,
)

RUN = "iterate-2026-07-27-artifact-state-stamping"
SHA = "ff88258795717661322e0d5cd5ccc5ff91efa17e"


class TestTokenCollisionRegression:
    """A run id containing a status word must not be read as that status.

    Found in self-review: ``"clean" in line`` matched ``iterate-2026-07-27-cleanup``
    and turned an unresolved ``dirty`` into a confident ``False`` — the banner would
    have asserted "clean tree" about a tree git was never asked about. SIMPLIFY-mode
    runs are named exactly like that, so this was reachable, not theoretical.
    """

    @pytest.mark.parametrize("run_id", [
        "iterate-2026-07-27-cleanup",
        "iterate-2026-07-27-declutter-clean",
        "iterate-2026-07-27-uncommitted-changes-audit",
    ])
    def test_unknown_dirty_stays_unknown(self, run_id):
        parsed = parse_banner_line(banner_line(SourceState(run_id=run_id, dirty=None)))
        assert parsed.run_id == run_id
        assert parsed.dirty is None

    @pytest.mark.parametrize("dirty", [True, False])
    def test_a_colliding_run_id_still_round_trips_a_real_flag(self, dirty):
        state = SourceState(run_id="iterate-2026-07-27-cleanup", commit=SHA, dirty=dirty)
        assert parse_banner_line(banner_line(state)) == state.abbreviated()


class TestExternalReviewRegressions:
    """Two defects external code review found in the first implementation.

    Both were forgery paths: a run id containing whitespace could inject a *status
    token* into the whitespace-delimited banner, and the control-character check was
    ASCII-only so Unicode line separators passed through.
    """

    @pytest.mark.parametrize("bad", [
        "run one",                    # parsed back as "run"
        "x clean",                    # forges dirty=False
        "x uncommitted-changes",      # forges dirty=True
        "x commit=deadbeefcafe",      # forges a commit
        "run\u00a0nbsp",              # non-breaking space
    ])
    def test_whitespace_bearing_run_ids_are_refused(self, bad):
        assert safe_run_id(bad) is None
        assert UNKNOWN_RUN in banner_line(SourceState(run_id=bad))

    @pytest.mark.parametrize("bad", ["a\u2028b", "a\u2029b", "a\u0085b", "a\u200eb"])
    def test_unicode_control_and_separator_chars_are_refused(self, bad):
        assert safe_run_id(bad) is None

    def test_a_forged_status_token_cannot_reach_the_parser(self):
        # The end-to-end property: whatever the run id, a banner built from a state
        # with dirty=None never parses back as a definite clean/dirty verdict.
        for attempt in ("x clean", "x uncommitted-changes", "plain-run"):
            parsed = parse_banner_line(banner_line(SourceState(run_id=attempt)))
            assert parsed.dirty is None

    def test_a_forged_commit_token_cannot_reach_the_parser(self):
        parsed = parse_banner_line(banner_line(SourceState(run_id="x commit=deadbeefcafe")))
        assert parsed.commit is None


class TestCommitIsValidatedOnBothSides:
    """`commit` bypassed validation in the first implementation (external review).

    Write side: an unvalidated commit could carry whitespace and inject a forged
    status token. Read side: ``commit=([0-9a-fA-F]+)`` was a substring search, so a
    run id that is a perfectly legal single token —
    ``iterate-2026-07-27-commit=deadbeef`` — parsed back carrying a commit nobody
    resolved.
    """

    @pytest.mark.parametrize("bad", [
        "a clean", "not-hex", "abc", "", None, 42,
        "deadbeefcafe\nSource-State: run=forged",
        "g" * 12,
    ])
    def test_implausible_commits_are_refused(self, bad):
        assert safe_commit(bad) is None

    @pytest.mark.parametrize("good", ["deadbee", SHA, SHA[:12]])
    def test_plausible_commits_are_accepted(self, good):
        assert safe_commit(good) == good

    def test_a_forged_commit_bearing_run_id_does_not_yield_a_commit(self):
        state = SourceState(run_id="iterate-2026-07-27-commit=deadbeefcafe")
        parsed = parse_banner_line(banner_line(state))
        assert parsed.commit is None, "a run id was read back as a commit"
        assert parsed.run_id == state.run_id

    def test_a_junk_commit_never_reaches_the_banner(self):
        line = banner_line(SourceState(run_id=RUN, commit="a clean"))
        assert line.count(BANNER_PREFIX) == 1
        assert "\n" not in line
        assert parse_banner_line(line).commit is None
        assert parse_banner_line(line).dirty is None

    def test_a_junk_commit_serialises_as_null(self):
        assert to_block(SourceState(run_id=RUN, commit="nope"))["commit"] is None


class TestUnsubstitutedPlaceholderRefused:
    """A literal ``{run_id}`` must never be stamped as a run id.

    Every caller is a runtime prompt, so an unsubstituted template placeholder is the
    realistic failure — external code review found exactly that in a call site. It is
    otherwise a well-formed token, so no other check would catch it, and stamping it
    would make a record confidently name a run that does not exist.
    """

    @pytest.mark.parametrize("bad", ["{run_id}", "{{run_id}}", "iterate-{date}-x", "a}b"])
    def test_placeholder_shaped_values_are_refused(self, bad):
        assert safe_run_id(bad) is None

    def test_the_banner_says_unknown_rather_than_echoing_the_placeholder(self):
        line = banner_line(SourceState(run_id="{run_id}"))
        assert f"run={UNKNOWN_RUN}" in line
        assert "{run_id}" not in line
