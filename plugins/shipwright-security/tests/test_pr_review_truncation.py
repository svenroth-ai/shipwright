"""Tests for truncate_diff_at_boundary — cutting an over-cap diff safely.

The Tier-3 reviewer fails CLOSED on a diff it could not read in full, so how the
cut is made decides two things: whether the reviewer sees syntactically whole
files, and whether a human can tell WHICH files nobody looked at. Split into its
own module (kept test_pr_review_filter.py under the source-size guideline) —
see iterate-2026-07-27-pr-review-diff-cap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_lib as L  # noqa: E402


def _section(path: str, body: str = "@@ -1 +1 @@\n-old\n+new\n") -> str:
    return f"diff --git a/{path} b/{path}\nindex 111..222 100644\n--- a/{path}\n+++ b/{path}\n{body}"


def _sized(path: str, n_lines: int) -> str:
    return _section(path, body="@@ -1 +1 @@\n" + ("+x\n" * n_lines))


class TestBoundaryTruncation:
    """Cutting an over-cap diff at a file boundary, and naming what fell out."""

    def test_the_cap_still_covers_the_largest_real_diff_measured(self):
        # Every other test here uses MAX_DIFF_CHARS symbolically, so all of them
        # would stay green if the cap were lowered back. This one would not.
        # PR #447 measured 467,591 chars AFTER generated-artifact filtering and
        # could not be reviewed under the old 200,000 cap — it had to be split
        # into three PRs. Drop below that and the splitting comes back.
        assert L.MAX_DIFF_CHARS >= 467_591

    def test_a_diff_under_the_cap_is_untouched(self):
        diff = _section("a.py") + _section("b.py")
        out = L.truncate_diff_at_boundary(diff, 10_000)
        assert out.text == diff
        assert out.incomplete is False
        assert out.omitted == () and out.partial == ()

    def test_exactly_at_the_cap_is_not_truncated(self):
        diff = _section("a.py")
        assert L.truncate_diff_at_boundary(diff, len(diff)).incomplete is False

    def test_every_kept_section_is_whole_and_the_rest_are_named(self):
        first, second = _sized("a.py", 20), _sized("b.py", 4000)
        out = L.truncate_diff_at_boundary(first + second, len(first) + 50)
        assert out.text == first          # ends on a boundary, not mid-hunk
        assert out.incomplete is True
        assert out.omitted == ("b.py",)
        assert out.partial == ()

    def test_a_huge_file_is_omitted_while_a_small_neighbour_is_reviewed_whole(self):
        # Mixed sizes: skipping an over-budget section and continuing reviews
        # MORE complete files than stopping at the first overflow would.
        huge, small = _sized("huge.py", 5000), _sized("small.py", 2)
        out = L.truncate_diff_at_boundary(huge + small, len(small) + 100)
        assert out.text == small
        assert out.omitted == ("huge.py",)
        # ...and the huge file is reported omitted, NOT handed over in part:
        # `partial` is reserved for the case where nothing whole fits at all.
        assert out.partial == ()

    def test_only_when_no_section_fits_is_one_supplied_in_part(self):
        huge = _sized("huge.py", 5000)
        out = L.truncate_diff_at_boundary(huge, 500)
        assert len(out.text) == 500       # non-empty: the reviewer gets material
        assert out.text.startswith("diff --git a/huge.py")
        assert out.partial == ("huge.py",)
        assert out.omitted == ()
        assert out.incomplete is True

    def test_at_most_one_section_is_ever_partial(self):
        diff = _sized("a.py", 3000) + _sized("b.py", 3000) + _sized("c.py", 3000)
        out = L.truncate_diff_at_boundary(diff, 400)
        assert len(out.partial) == 1
        assert set(out.omitted) == {"b.py", "c.py"}

    def test_a_diff_with_no_parseable_header_still_fails_closed(self):
        # A parse surprise must never read as "nothing was dropped" — that would
        # be a size bypass of a required gate.
        out = L.truncate_diff_at_boundary("x" * 5_000, 1_000)
        assert out.incomplete is True
        assert len(out.text) == 1_000
        assert out.omitted == () and out.partial == ()

    def test_an_oversized_preamble_still_respects_the_cap(self):
        diff = ("warning: preamble\n" * 500) + _section("a.py")
        out = L.truncate_diff_at_boundary(diff, 200)
        assert len(out.text) == 200
        assert out.incomplete is True
        assert out.omitted == ("a.py",)

    def test_an_omission_whose_path_cannot_be_parsed_is_counted_not_dropped(self):
        # Git quotes headers for paths with spaces/non-ASCII; the path regex does
        # not match those. A short list must not read as a complete one.
        quoted = 'diff --git "a/od d.py" "b/od d.py"\nBinary files differ\n' + ("x" * 4_000)
        small = _sized("small.py", 1)
        out = L.truncate_diff_at_boundary(small + quoted, len(small) + 50)
        assert out.incomplete is True
        assert out.omitted == ()
        assert out.unidentified == 1

    def test_a_rename_reports_both_ends_when_omitted(self):
        rename = (
            "diff --git a/old.py b/new.py\nsimilarity index 100%\n"
            "rename from old.py\nrename to new.py\n" + ("x" * 3_000)
        )
        small = _sized("small.py", 1)
        out = L.truncate_diff_at_boundary(small + rename, len(small) + 50)
        assert out.omitted == ("new.py", "old.py")

    @pytest.mark.parametrize("cap", [1, 50, 300, 5_000])
    def test_the_reviewed_diff_never_exceeds_the_cap(self, cap):
        diff = ("preamble\n" * 30) + _sized("a.py", 200) + _sized("b.py", 5) + "trailing"
        assert len(L.truncate_diff_at_boundary(diff, cap).text) <= cap

    def test_a_non_positive_cap_is_rejected(self):
        with pytest.raises(ValueError):
            L.truncate_diff_at_boundary(_section("a.py"), 0)

    def test_a_partial_file_whose_own_header_is_unparseable_is_still_disclosed(self):
        # Regression: counting only the *other* sections left this one invisible,
        # and the caller then reported "no parseable file headers" — the message
        # for a different input entirely. A boundary WAS found here.
        quoted = 'diff --git "a/od d.py" "b/od d.py"\nBinary files differ\n' + ("x" * 4_000)
        out = L.truncate_diff_at_boundary(quoted, 500)
        assert out.incomplete is True
        assert out.partial == () and out.omitted == ()
        assert out.unidentified == 1
        body = L.render_comment({"decision": "approve"}, model="m", truncated=True,
                                omitted=out.omitted, partial=out.partial,
                                unidentified=out.unidentified)
        assert "1 section(s) whose path could not be identified" in body
        assert "no parseable file headers" not in body
