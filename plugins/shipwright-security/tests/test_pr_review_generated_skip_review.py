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


def test_ordinary_source_is_never_safe_to_skip():
    assert not G.is_safe_to_skip_review("plugins/shipwright-security/scripts/tools/pr_review.py")
