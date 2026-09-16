"""iterate-2026-09-16-generated-path-no-strip: `is_generated_path` no longer
`.strip()`s its input before matching, mirroring the sibling
`is_safe_to_skip_review` fix (PR #746, iterate-2026-09-12-generated-prefixes-
provenance-anchor) — a real, distinct on-disk path differing only by
leading/trailing whitespace from a generated shape must not borrow that
shape's classification. Split out of `test_pr_review_filter.py` to keep that
file under the source-size guideline, following the same precedent as
`test_pr_review_generated_skip_review.py` / `test_pr_review_forged_boundary.py`.

**A Stage-2 code review on this same iterate raised, then this file's own
tests DISPROVED, a claimed end-to-end gap.** The reviewer traced only the
`--- a/` / `+++ b/` lines through `_clean_diff_path` (which had its own
blanket `.strip()`) and concluded a trailing-whitespace-padded lookalike
would still reach `is_generated_path` normalized, reproducing the bug one
layer up. That trace missed that `_section_paths` ALSO collects paths from
the `diff --git a/X b/X` header line itself (via `_DIFF_GIT_RE`), and that a
non-rename header for a real file whose name ends in whitespace inherently
produces a DOUBLE space before its `b/` token (the git-format literal space
plus the name's own trailing space) — which the header's own non-greedy
regex resolves by keeping the padding on the `a/`-side capture. Combined with
`filter_generated_paths`'s "every collected path must be generated to
exclude" rule (kept for renames), that header-side leak alone is *already*
enough to keep such a file reviewable, independent of `_clean_diff_path`.
`test_trailing_whitespace_lookalike_stays_reviewable_end_to_end` below proves
this empirically: it fails identically whether or not `_clean_diff_path`
normalizes trailing whitespace (verified by hand during triage — reverting
`_clean_diff_path` to a blanket `.strip()` left this test green).

`_clean_diff_path`'s blanket `.strip()` was narrowed anyway
(`plugins/shipwright-security/scripts/lib/pr_review_diff_filter.py`,
`_clean_diff_path`, now `.rstrip("\\r")` only) — not because it was an active
end-to-end vulnerability (it was not, per the above), but because a blanket
`.strip()` had no legitimate purpose beyond the CRLF artifact the module's own
LF-only line-splitting leaves behind, and normalizing more than that is
exactly the pattern this whole iterate exists to remove. `test_clean_diff_path_*`
below tests that function directly, in isolation from the header's redundant
capture, since the end-to-end test cannot distinguish the two mechanisms.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_diff_filter as F  # noqa: E402
import pr_review_lib as L  # noqa: E402


def _section(path: str, body: str = "@@ -1 +1 @@\n-old\n+new\n") -> str:
    return f"diff --git a/{path} b/{path}\nindex 111..222 100644\n--- a/{path}\n+++ b/{path}\n{body}"


def test_whitespace_variant_of_a_generated_shape_is_NOT_generated():
    """Direct call, all three internal match strategies `is_generated_path`
    uses. Leading space breaks a `startswith`-matched prefix or exact-path
    membership; trailing space breaks an exact-membership match (basename or
    full path) — a prefix match alone is unaffected by TRAILING whitespace,
    since a trailing-space file still starts with the same directory prefix,
    so that combination is deliberately absent here."""
    for path in (
        " .shipwright/compliance/dashboard.md",          # prefix: leading space
        " CHANGELOG-unreleased.d/Added/foo_001.md",       # prefix: leading space
        " shipwright_test_results.json",                  # basename: leading space
        "shipwright_events.jsonl ",                       # basename: trailing space
        " .shipwright/agent_docs/build_dashboard.md",     # exact path: leading space
        ".shipwright/agent_docs/build_dashboard.md ",     # exact path: trailing space
        " .shipwright/planning/iterate/run-x/reviews.json",           # review-evidence: legacy regex, leading space
        " .shipwright/planning/iterate/run-x/spec_review_reply.json",  # review-evidence: run-anchored regex, leading space
    ):
        assert not L.is_generated_path(path), path


def test_review_evidence_paths_are_still_generated_unpadded():
    """Positive control for the review-evidence cases in the test above —
    proves those two paths genuinely are classified generated in their
    canonical (unpadded) form, so the padded assertions above are a real
    behavior change, not a vacuous pass against paths that were never
    matched in the first place."""
    assert L.is_generated_path(".shipwright/planning/iterate/run-x/reviews.json")
    assert L.is_generated_path(".shipwright/planning/iterate/run-x/spec_review_reply.json")


def test_trailing_whitespace_lookalike_stays_reviewable_end_to_end():
    """Exercises the real call path (`filter_generated_paths` ->
    `_section_paths` -> `is_generated_path`), not `is_generated_path` called
    directly — proving the file stays in the reviewed diff, not merely that
    the classifier alone returns the right bool. See the module docstring for
    why this passes independent of `_clean_diff_path`'s own normalization."""
    padded = ".shipwright/agent_docs/build_dashboard.md "  # trailing space
    diff = _section("shared/scripts/tools/foo.py") + _section(padded)
    filtered, excluded = L.filter_generated_paths(diff)
    assert excluded == []
    assert padded in filtered


def test_clean_diff_path_preserves_real_trailing_whitespace():
    """`_clean_diff_path` in isolation (bypassing the header line's redundant
    capture — see module docstring): a `+++ b/…`/`--- a/…` remainder whose
    path genuinely ends in whitespace must keep it, not silently normalize a
    real, distinct filename to its unpadded look-alike."""
    assert F._clean_diff_path("b/.shipwright/agent_docs/build_dashboard.md ") == (
        ".shipwright/agent_docs/build_dashboard.md ")
    assert F._clean_diff_path(" a/leading-space-is-not-a-real-diff-shape") == (
        " a/leading-space-is-not-a-real-diff-shape")


def test_clean_diff_path_still_strips_trailing_CR():
    """The one legitimate normalization this function ever needed: a CRLF
    diff leaves a trailing `\\r` on every line, since the module splits
    sections on LF only (see `_split_sections`'s own docstring)."""
    assert F._clean_diff_path("b/shared/real.py\r") == "shared/real.py"
    assert F._clean_diff_path("/dev/null\r") == ""
