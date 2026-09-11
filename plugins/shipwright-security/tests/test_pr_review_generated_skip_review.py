"""Tests for `pr_review_generated.is_safe_to_skip_review` — the strictly
narrower sibling of `is_generated_path` used to decide whether the PR-review
GATE ITSELF may post green with no model call at all (as opposed to merely
hiding a section from a model that still reviews the rest of the diff).

Added after a Stage-3 doubt review on iterate-2026-09-10-pr-review-generated-only
found that reusing `is_generated_path` wholesale let a PR touching only the
three agent-instruction-surface docs (`_GENERATED_AGENT_DOCS`) skip review
entirely, and that the basename-only matches (`_GENERATED_BASENAMES`) were not
anchored to their canonical location.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

import pr_review_generated as G  # noqa: E402


def test_compliance_and_changelog_prefixes_stay_safe_to_skip():
    assert G.is_safe_to_skip_review(".shipwright/compliance/dashboard.md")
    assert G.is_safe_to_skip_review(".shipwright/compliance/sbom.md")
    assert G.is_safe_to_skip_review("CHANGELOG-unreleased.d/fix/some-drop.md")
    assert G.is_safe_to_skip_review(".shipwright/agent_docs/iterates/iterate-x.test-results.json")


def test_the_three_agent_instruction_docs_are_NOT_safe_to_skip():
    """High-severity doubt-review finding: these are read back as agent
    context in later sessions and must still get a reviewer's eyes, even
    though `is_generated_path` (correctly) hides them from a diff that is
    otherwise reviewed."""
    for path in (
        ".shipwright/agent_docs/build_dashboard.md",
        ".shipwright/agent_docs/session_handoff.md",
        ".shipwright/agent_docs/triage_inbox.md",
    ):
        assert G.is_generated_path(path), path
        assert not G.is_safe_to_skip_review(path), path


def test_canonical_basename_paths_stay_safe_to_skip():
    assert G.is_safe_to_skip_review("shipwright_test_results.json")
    assert G.is_safe_to_skip_review("shipwright_events.jsonl")
    assert G.is_safe_to_skip_review(".shipwright/triage.jsonl")
    assert G.is_safe_to_skip_review(".shipwright/triage.outbox.jsonl")


def test_an_off_canonical_path_with_a_generated_basename_is_NOT_safe_to_skip():
    """Medium-severity doubt-review finding: a brand-new file merely NAMED
    triage.jsonl at an attacker-chosen path is not the regenerated artifact
    the basename rule exists for."""
    for path in (
        "plugins/shipwright-evil/scripts/tools/triage.jsonl",
        "some/nested/dir/shipwright_events.jsonl",
        "plugins/shipwright-evil/shipwright_test_results.json",
    ):
        assert G.is_generated_path(path), path
        assert not G.is_safe_to_skip_review(path), path


def test_review_evidence_files_stay_safe_to_skip():
    assert G.is_safe_to_skip_review(".shipwright/planning/iterate/iterate-x/reviews.json")


def test_review_evidence_siblings_are_hidden_but_NOT_safe_to_skip():
    """External plan review Round 3 (openai, high severity), iterate-2026-09-
    11-pr-review-evidence-filter-gap: an earlier version of this fix added
    the exact `{spec,code,doubt}_review_reply.json` basenames to the skip
    set too, reasoning they were as tool-adjacent as `reviews.json`. openai
    correctly flagged this as an unforced expansion — an exact basename is
    not PROVENANCE, and nothing required these files to be skip-safe to fix
    PR #722 (that bug was entirely about the reviewer SEEING them, i.e. the
    hide side). Reverted: they now get the same treatment
    `external-*review*` files always had — hidden from the model (lower
    stakes), but a PR touching only one still goes through a real review
    call rather than an automatic skip."""
    run = ".shipwright/planning/iterate/iterate-x"
    for name in (
        "spec_review_reply.json",
        "code_review_reply.json",
        "doubt_review_reply.json",
        "external-code-review-raw.json",
        "external-code-review.json",
        "external-plan-review.md",
    ):
        assert G.is_generated_path(f"{run}/{name}"), name
        assert not G.is_safe_to_skip_review(f"{run}/{name}"), name


def test_an_attacker_chosen_reply_or_external_name_is_NOT_safe_to_skip():
    """Internal Plan Review, high-severity finding on
    iterate-2026-09-11-pr-review-evidence-filter-gap: the first version of the
    widened `_REVIEW_EVIDENCE_RE` matched ANY `*_reply.json` basename with no
    provenance check, so reusing it verbatim for `is_safe_to_skip_review`
    would let a PR whose only changed file is e.g. `evil_reply.json` post
    `success` with no model call — the filename alone is not evidence the
    file is actually a tool-written transcript. The skip-the-gate decision
    uses a closed, anchored set instead, for all three names."""
    run = ".shipwright/planning/iterate/iterate-x"
    for name in (
        "evil_reply.json",
        "notes_reply.json",
        "external-my-own-review-of-this.json",
    ):
        assert not G.is_safe_to_skip_review(f"{run}/{name}"), name


def test_an_attacker_chosen_reply_name_is_not_even_hidden_after_round_2():
    """External plan review round 2 (glm=approve, openai=revise) on
    iterate-2026-09-11-pr-review-evidence-filter-gap closed
    `_REVIEW_EVIDENCE_RE_RUN_ANCHORED`'s reply alternative from a wildcard
    (`[^/]*_reply\\.json`) to the exact three basenames a repo-wide history
    survey confirmed are the only ones ever produced
    (`{spec,code,doubt}_review_reply.json`) — so an attacker-chosen reply
    name is now not even hidden from the model, let alone skip-safe.
    `external-*review*` keeps its wildcard on the hide side (no fixed output
    name to enumerate), so it still gets hidden."""
    run = ".shipwright/planning/iterate/iterate-x"
    assert not G.is_generated_path(f"{run}/evil_reply.json")
    assert not G.is_generated_path(f"{run}/notes_reply.json")
    assert G.is_generated_path(f"{run}/external-my-own-review-of-this.json")


def test_a_mixed_case_basename_borrows_neither_hide_nor_skip():
    """code-reviewer finding (high), iterate-2026-09-11-pr-review-evidence-
    filter-gap: `_REVIEW_EVIDENCE_SKIP_RE` and
    `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` were both compiled `re.IGNORECASE`,
    contradicting the skip set's own "EXACT basenames, zero wildcards"
    design — `record_review_pass.py` only ever writes lowercase
    `reviews.json`, so `REVIEWS.JSON` (a name the real tool never produces)
    must not borrow the skip-safe classification on a case-sensitive CI
    runner, and a differently-cased reply name must not borrow the
    hide-only classification either."""
    run = ".shipwright/planning/iterate/iterate-x"
    assert not G.is_safe_to_skip_review(f"{run}/REVIEWS.JSON")
    assert not G.is_safe_to_skip_review(f"{run}/Reviews.Json")
    assert not G.is_generated_path(f"{run}/Spec_Review_Reply.json")


def test_review_evidence_skip_is_anchored_to_exactly_one_run_segment():
    """A bare top-level file or an extra-nested path is not the shape
    `record_review_pass.py` / `external_review.py` ever write, and admitting
    it would widen the closed set into an open one again."""
    for path in (
        ".shipwright/planning/iterate/reviews.json",  # no run segment
        ".shipwright/planning/iterate/iterate-x/nested/reviews.json",  # extra nesting
    ):
        assert not G.is_safe_to_skip_review(path), path


def test_self_review_payload_is_NOT_safe_to_skip():
    """The one sibling deliberately excluded from `_REVIEW_EVIDENCE_RE`: this
    is the payload SENT TO a review stage, not a transcript OF one, so it is
    closer to author-controlled content — it must still gate on a real
    review, not silently license skipping one."""
    run = ".shipwright/planning/iterate/iterate-x"
    assert not G.is_generated_path(f"{run}/self-review-payload.json")
    assert not G.is_safe_to_skip_review(f"{run}/self-review-payload.json")


def test_ordinary_source_is_never_safe_to_skip():
    assert not G.is_safe_to_skip_review("plugins/shipwright-security/scripts/tools/pr_review.py")


def test_a_lookalike_suffix_does_not_borrow_the_closed_match():
    """External plan review (openai), iterate-2026-09-11-pr-review-evidence-
    filter-gap: `_REVIEW_EVIDENCE_SKIP_RE` is fully anchored with `$`, so a
    trailing suffix like `.bak` — the kind of stray editor/backup artifact a
    careless PR might carry — must not be treated as the real evidence file
    it merely resembles."""
    run = ".shipwright/planning/iterate/iterate-x"
    assert not G.is_safe_to_skip_review(f"{run}/spec_review_reply.json.bak")
