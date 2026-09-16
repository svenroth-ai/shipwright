"""Regression coverage for iterate-2026-09-11-pr-review-evidence-filter-gap.

PR #722's automated "PR Review" gate BLOCKed twice on the same finding:
`.shipwright/planning/iterate/<run>/spec_review_reply.json` and
`external-code-review-raw.json` — tool-written transcripts of this repo's own
review pipeline — were fed to the reviewer instead of being filtered out like
`reviews.json` already is. `_REVIEW_EVIDENCE_RE` in `pr_review_generated.py`
matched `reviews.json` and the legacy `[^/]*-external-[^/]*review[^/]*\\.json`
shape, but missed `external-code-review-raw.json` (nothing precedes
"external-") and the `*_reply.json` convention entirely.

Split out of `test_pr_review_filter.py` to keep that file under the size
guideline — these tests are additive to (not a replacement for) its existing
`TestReviewEvidenceExcluded` coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

import pr_review_generated as G  # noqa: E402

RUN = ".shipwright/planning/iterate/iterate-2026-07-27-a-run"


def test_review_reply_and_external_raw_siblings_are_excluded():
    """`reviews.json` was excluded but its four same-directory siblings were
    not, so a reviewer was fed tool-written review transcripts it should
    never see (circular review) despite the module docstring naming exactly
    this class of file as in-scope. `external-code-review-raw.json` doesn't
    match the older `[^/]*-external-[^/]*review[^/]*\\.json` shape (nothing
    precedes "external-"), and the `*_reply.json` files are a distinct
    naming convention `record_review_pass.py`'s callers use today."""
    for name in (
        "spec_review_reply.json",
        "code_review_reply.json",
        "doubt_review_reply.json",
        "external-code-review-raw.json",
        "external-code-review.json",
    ):
        assert G.is_generated_path(f"{RUN}/{name}"), name


def test_raw_review_transcripts_in_markdown_are_also_excluded():
    """Internal Plan Review, medium-severity completeness finding: merged
    run dirs also carry `.md` raw transcripts (e.g.
    `external-code-review.raw.md`, `external-plan-review.md`) with the same
    verdict-shaped text that caused PR #722's BLOCK — the `.json`-only regex
    only closed half the gap."""
    for name in (
        "external-code-review.md",
        "external-code-review.raw.md",
        "external-plan-review.md",
    ):
        assert G.is_generated_path(f"{RUN}/{name}"), name


def test_self_review_payload_stays_reviewable():
    """Deliberately NOT excluded: this is the payload SENT TO a review
    stage, not a transcript OF one — the module docstring's warning about an
    over-broad entry ("silently hides the file AND tells the maintainer it
    carried nothing worth reading") applies most sharply here, since it is
    closer to author-controlled content than the other tool-written
    replies."""
    assert not G.is_generated_path(f"{RUN}/self-review-payload.json")


def test_reply_and_external_hiding_requires_a_run_directory_segment():
    """External plan review round 1 (glm + openai), iterate-2026-09-11-pr-
    review-evidence-filter-gap: the first version of this fix's new
    alternatives were unanchored, matching `*_reply.json` /
    `external-...review....json` at ANY depth under
    `.shipwright/planning/iterate/` — not just inside a genuine run's own
    directory. A bare top-level file, or a file nested two levels deep, is
    not the shape either tool ever writes and must not be hidden from the
    reviewer on a self-chosen name.

    Uses `spec_review_reply.json` (a real basename) for the reply case,
    since round 2 later closed the reply alternative to an exact three-name
    set — see `test_an_attacker_chosen_reply_name_is_not_even_hidden_after_round_2`
    in test_pr_review_generated_skip_review.py for the attacker-chosen-name
    case, which is now never hidden regardless of depth.

    Also covers an over-nested `external-*review*` path (external code
    review, openai, low): a regression allowing the external branch two or
    more directory segments while the reply branch stayed correctly
    anchored would otherwise pass unnoticed."""
    for path in (
        ".shipwright/planning/iterate/spec_review_reply.json",  # no run segment
        ".shipwright/planning/iterate/a/b/spec_review_reply.json",  # too deep
        ".shipwright/planning/iterate/evil-external-review.md",  # no run segment
        ".shipwright/planning/iterate/a/b/external-code-review.md",  # too deep
    ):
        assert not G.is_generated_path(path), path
    # Exactly one run-directory segment is the shape that DOES get hidden —
    # this is what makes the run-directory-anchored alternatives useful at
    # all, not just narrower than nothing.
    assert G.is_generated_path(".shipwright/planning/iterate/other-tree/spec_review_reply.json")
