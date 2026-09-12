"""Tests for `pr_review_skip_safety.is_safe_to_skip_review` — the strictly
narrower sibling of `pr_review_generated.is_generated_path` used to decide
whether the PR-review GATE ITSELF may post green with no model call at all
(as opposed to merely hiding a section from a model that still reviews the
rest of the diff).

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
import pr_review_skip_safety as S  # noqa: E402


def test_compliance_prefix_is_no_longer_safe_to_skip():
    """iterate-2026-09-12-generated-prefixes-provenance-anchor: `ci-security.json`
    is read by `security_gate.py` as a deploy-gate pass/fail oracle with no
    provenance check — the same "exact path isn't provenance" shape Round 4
    closed for `reviews.json`. Its siblings have no closed set either, so the
    whole prefix lost skip-safety, not just the one file. Still hidden from
    the model (`is_generated_path`, unaffected)."""
    for path in (
        ".shipwright/compliance/ci-security.json",
        ".shipwright/compliance/dashboard.md",
        ".shipwright/compliance/sbom.md",
    ):
        assert G.is_generated_path(path), path
        assert not S.is_safe_to_skip_review(path), path


def test_runtime_prefix_is_no_longer_safe_to_skip():
    """`.shipwright/agent_docs/runtime/` is gitignored and empirically never
    tracked (shared/tests/test_runtime_dir_gitignored.py); granting it
    skip-safety was pure downside with no legitimate write to preserve."""
    path = ".shipwright/agent_docs/runtime/session_handoff.md"
    assert G.is_generated_path(path)
    assert not S.is_safe_to_skip_review(path)


def test_changelog_drop_anchored_shape_stays_safe_to_skip():
    assert S.is_safe_to_skip_review(
        "CHANGELOG-unreleased.d/Fixed/iterate-2026-01-01-x_001.md"
    )
    assert S.is_safe_to_skip_review(
        "CHANGELOG-unreleased.d/Security/iterate-2026-01-01-x_012.md"
    )


def test_changelog_drop_off_shape_is_NOT_safe_to_skip():
    """An attacker-chosen category, a missing counter suffix, or an extra
    nesting level no longer borrow the anchored category+drop shape. Each
    case isolates exactly one failing axis (code review, iterate-2026-09-12-
    generated-prefixes-provenance-anchor)."""
    for path in (
        "CHANGELOG-unreleased.d/fix/iterate-x_001.md",  # not a real category name
        "CHANGELOG-unreleased.d/FIXED/iterate-x_001.md",  # not a real category case
        "CHANGELOG-unreleased.d/Fixed/some-drop.md",  # no _NNN counter
        "CHANGELOG-unreleased.d/Fixed/iterate-x_1.md",  # counter not 3 digits
        "CHANGELOG-unreleased.d/Fixed/nested/iterate-x_001.md",  # extra nesting
        "CHANGELOG-unreleased.d/Fixed/iterate-x_١٢٣.md",  # Unicode digits, not ASCII
        "CHANGELOG-unreleased.d/Fixed/_001.md",  # empty name before the counter
    ):
        assert not S.is_safe_to_skip_review(path), path


def test_iterates_prefix_is_no_longer_safe_to_skip():
    """iterate-2026-09-12-generated-prefixes-provenance-anchor, Stage-3 doubt
    review: an earlier version of this fix anchored the filename to
    `<run_id>.json` / `<run_id>.test-results.json`, reasoning that
    `RUN_ID_STRICT` shape was already enforced at write time. Disproved:
    `RUN_ID_STRICT` is a public, freely-choosable shape, not a signature — a
    contributor's own PR can commit a brand-new, self-authored, shape-valid
    file under this prefix with forged content. A concrete real consumer
    trusts that content unauthenticated: `complexity_history.load_history_
    prior` globs every `*.json` directly under this dir and accepts any file
    with a valid `complexity` + parseable `date`, feeding it into later
    iterates' complexity default. Same "shape is not provenance" defect
    Round 4 closed for `reviews.json` and this iterate closed for
    `ci-security.json` — removed entirely rather than left narrower-but-
    still-forgeable. Still hidden from the model (`is_generated_path`,
    unaffected)."""
    for path in (
        ".shipwright/agent_docs/iterates/iterate-2026-01-01-x.json",
        ".shipwright/agent_docs/iterates/iterate-2026-01-01-x.test-results.json",
        ".shipwright/agent_docs/iterates/_quarantine/legacy.json",
        ".shipwright/agent_docs/iterates/nested/iterate-2026-01-01-x.json",
    ):
        assert G.is_generated_path(path), path
        assert not S.is_safe_to_skip_review(path), path


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
        assert not S.is_safe_to_skip_review(path), path


def test_canonical_basename_paths_stay_safe_to_skip():
    assert S.is_safe_to_skip_review("shipwright_test_results.json")
    assert S.is_safe_to_skip_review("shipwright_events.jsonl")
    assert S.is_safe_to_skip_review(".shipwright/triage.jsonl")
    assert S.is_safe_to_skip_review(".shipwright/triage.outbox.jsonl")


def test_whitespace_variant_of_a_skip_safe_shape_is_NOT_safe_to_skip():
    """Live PR-review gate, this iterate's own PR #746 (blocking): the
    classifier used to `.strip()` its input before matching, so a real,
    distinct on-disk path differing only by leading/trailing whitespace from
    a canonical skip-safe shape could borrow that shape's classification.
    `is_safe_to_skip_review` no longer normalizes at all — every one of these
    must be rejected, not merely "still passes because whitespace happens to
    collapse the same way"."""
    for path in (
        " shipwright_test_results.json",
        "shipwright_test_results.json ",
        " shipwright_events.jsonl",
        " .shipwright/triage.jsonl",
        ".shipwright/triage.outbox.jsonl ",
        " CHANGELOG-unreleased.d/Fixed/x_001.md",
        "CHANGELOG-unreleased.d/Fixed/x_001.md ",
        "\tCHANGELOG-unreleased.d/Security/x_012.md",
        "CHANGELOG-unreleased.d/Security/x_012.md\n",
    ):
        assert not S.is_safe_to_skip_review(path), path


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
        assert not S.is_safe_to_skip_review(path), path


def test_reviews_json_is_hidden_but_NOT_safe_to_skip():
    """Round 4 (the live PR-review gate's own bot, on this iterate's own
    PR #727): even the exact, run-anchored, case-sensitive `reviews.json`
    match was an unforced bypass — an exact PATH is not PROVENANCE, and a
    contributor's own PR can commit a forged `reviews.json` at a
    self-chosen run directory. No review-evidence path grants skip-safety
    any more; `reviews.json` keeps only its hide-side treatment."""
    path = ".shipwright/planning/iterate/iterate-x/reviews.json"
    assert G.is_generated_path(path)
    assert not S.is_safe_to_skip_review(path)


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
    call rather than an automatic skip. Round 4 later removed
    `reviews.json`'s own skip-safety too, making every review-evidence file
    behave identically here."""
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
        assert not S.is_safe_to_skip_review(f"{run}/{name}"), name


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
        assert not S.is_safe_to_skip_review(f"{run}/{name}"), name


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
    filter-gap: `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` was compiled
    `re.IGNORECASE`, contradicting "EXACT basenames, zero wildcards" —
    `record_review_pass.py` only ever writes lowercase `reviews.json`, and a
    differently-cased reply name must not borrow the hide-only
    classification either. `reviews.json` itself is no longer skip-safe in
    any casing as of Round 4, so only the hide-side assertion remains
    meaningful here."""
    run = ".shipwright/planning/iterate/iterate-x"
    assert not S.is_safe_to_skip_review(f"{run}/REVIEWS.JSON")
    assert not S.is_safe_to_skip_review(f"{run}/Reviews.Json")
    assert not G.is_generated_path(f"{run}/Spec_Review_Reply.json")


def test_review_evidence_is_never_safe_to_skip_in_any_shape():
    """Round 4: no review-evidence path grants skip-safety any more, so a
    bare top-level file, an extra-nested path, or a stray `.bak` suffix —
    shapes that used to matter only for anchoring a since-removed closed
    match — all land on the same answer as the canonical shape."""
    for path in (
        ".shipwright/planning/iterate/reviews.json",  # no run segment
        ".shipwright/planning/iterate/iterate-x/nested/reviews.json",  # extra nesting
        ".shipwright/planning/iterate/iterate-x/spec_review_reply.json.bak",  # lookalike suffix
    ):
        assert not S.is_safe_to_skip_review(path), path


def test_self_review_payload_is_NOT_safe_to_skip():
    """The one sibling deliberately excluded from `_REVIEW_EVIDENCE_RE`: this
    is the payload SENT TO a review stage, not a transcript OF one, so it is
    closer to author-controlled content — it must still gate on a real
    review, not silently license skipping one."""
    run = ".shipwright/planning/iterate/iterate-x"
    assert not G.is_generated_path(f"{run}/self-review-payload.json")
    assert not S.is_safe_to_skip_review(f"{run}/self-review-payload.json")


def test_ordinary_source_is_never_safe_to_skip():
    assert not S.is_safe_to_skip_review("plugins/shipwright-security/scripts/tools/pr_review.py")


