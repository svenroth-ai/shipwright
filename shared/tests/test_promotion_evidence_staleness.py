"""Tests for shared/scripts/lib/promotion_evidence_staleness.py — the per-FR
"nothing invalidating changed since the anchor" guard (P3.4c)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.promotion_evidence_staleness import (
    REASON_EVIDENCE_STALE_SINCE_ANCHOR,
    _looks_like_test_path,
    bound_test_files,
    changed_paths_between,
    dirty_or_untracked_paths,
    evidence_stale_since_anchor,
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


def _init_repo(tmp_path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    return tmp_path


def _commit(project: Path, files: dict[str, str], message: str) -> str:
    for relpath, content in files.items():
        path = project / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", message)
    return _git(project, "rev-parse", "HEAD").strip()


def test_bound_test_files_extracts_the_file_half_of_every_test_id():
    node = {
        "tests": {
            "unit": [{"path": "tests/test_a.py::test_one"}, {"path": "tests/test_a.py::test_two"}],
            "integration": [{"path": "tests/test_b.py::test_three"}],
        },
    }
    assert bound_test_files(node) == {"tests/test_a.py", "tests/test_b.py"}


def test_bound_test_files_falls_back_to_id_when_path_is_absent():
    node = {"tests": {"unit": [{"id": "tests/test_a.py::test_one"}]}}
    assert bound_test_files(node) == {"tests/test_a.py"}


def test_bound_test_files_returns_none_on_a_malformed_non_dict_link():
    node = {"tests": {"unit": ["not-a-dict"]}}
    assert bound_test_files(node) is None


def test_bound_test_files_returns_none_when_path_is_not_a_string():
    node = {"tests": {"unit": [{"path": 5}]}}
    assert bound_test_files(node) is None


def test_bound_test_files_returns_none_when_path_and_id_are_both_absent():
    node = {"tests": {"unit": [{}]}}
    assert bound_test_files(node) is None


def test_bound_test_files_returns_none_when_a_layers_links_are_not_a_list():
    node = {"tests": {"unit": "not-a-list"}}
    assert bound_test_files(node) is None


def test_bound_test_files_empty_when_no_tests():
    assert bound_test_files({}) == set()


def test_evidence_stale_since_anchor_true_when_a_bound_test_file_changed():
    node = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    changed = {"tests/test_a.py"}
    assert evidence_stale_since_anchor(node, node, node, {"spec.md"}, changed) is True


def test_evidence_stale_since_anchor_true_when_the_anchor_spec_path_changed():
    node = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    changed = {"spec.md"}
    assert evidence_stale_since_anchor(node, node, node, {"spec.md"}, changed) is True


def test_evidence_stale_since_anchor_true_when_only_the_head_spec_path_changed():
    # The FR moved to a different spec.md between the anchor and HEAD -- the
    # anchor's own spec.md is untouched, but the NEW one changed. Promoting
    # here would write into a file the anchor run never covered at all
    # (external review, openai/high + glm/low).
    node = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    changed = {"new_spec.md"}
    assert evidence_stale_since_anchor(node, node, node, {"spec.md", "new_spec.md"}, changed) is True


def test_evidence_stale_since_anchor_false_when_nothing_relevant_changed():
    node = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    changed = {"some/unrelated/file.py"}
    assert evidence_stale_since_anchor(node, node, node, {"spec.md"}, changed) is False


def test_evidence_stale_since_anchor_false_on_empty_diff():
    node = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    assert evidence_stale_since_anchor(node, node, node, {"spec.md"}, set()) is False


def test_evidence_stale_since_anchor_true_when_bound_test_files_is_unparseable_at_anchor():
    node_anchor = {"tests": {"unit": ["not-a-dict"]}}
    node_head = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    assert evidence_stale_since_anchor(node_anchor, node_anchor, node_head, {"spec.md"}, set()) is True


def test_evidence_stale_since_anchor_true_when_bound_test_files_is_unparseable_at_head():
    node_anchor = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    node_head = {"tests": {"unit": ["not-a-dict"]}}
    assert evidence_stale_since_anchor(node_anchor, node_anchor, node_head, {"spec.md"}, set()) is True


def test_evidence_stale_since_anchor_true_when_bound_test_files_is_unparseable_at_anchor_ci_evidence():
    # The THIRD source (external code-reviewer, high): a malformed CI
    # evidence node at the anchor is just as invalidating as a malformed
    # committed-manifest node -- neither alone is enough to trust.
    node_anchor = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    ci_node_anchor = {"tests": {"unit": ["not-a-dict"]}}
    node_head = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    assert evidence_stale_since_anchor(node_anchor, ci_node_anchor, node_head, {"spec.md"}, set()) is True


def test_evidence_stale_since_anchor_true_when_a_test_was_newly_bound_at_head():
    # The requirement's traceability BINDING changed between anchor and
    # HEAD -- a test newly bound to this FR -- without either file's own
    # bytes changing at all, so it never shows up in `changed` (external
    # plan review, glm/medium + openai/high, both independently).
    node_anchor = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    node_head = {"tests": {"unit": [
        {"path": "tests/test_a.py::test_one"}, {"path": "tests/test_b.py::test_two"},
    ]}}
    assert evidence_stale_since_anchor(node_anchor, node_anchor, node_head, {"spec.md"}, set()) is True


def test_evidence_stale_since_anchor_true_when_a_test_was_unbound_at_head():
    node_anchor = {"tests": {"unit": [
        {"path": "tests/test_a.py::test_one"}, {"path": "tests/test_b.py::test_two"},
    ]}}
    node_head = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    assert evidence_stale_since_anchor(node_anchor, node_anchor, node_head, {"spec.md"}, set()) is True


def test_evidence_stale_since_anchor_false_when_binding_is_identical_and_nothing_changed():
    node_anchor = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    node_head = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    assert evidence_stale_since_anchor(node_anchor, node_anchor, node_head, {"spec.md"}, set()) is False


def test_evidence_stale_since_anchor_true_when_only_ci_evidence_knew_about_the_changed_file():
    # The core regression pin for the code-reviewer's HIGH finding: `tests`
    # is excluded from `compare_traceability_manifest.structural_diff`, so
    # the anchor's COMMITTED manifest is not proof of what the anchor's CI
    # run actually confirmed. Isolated from the binding-drift check
    # (deliberately NOT covered there): HEAD's own binding already matches
    # the UNION of the anchor's manifest and its CI evidence (no drift), so
    # only the invalidating-FILE-SET path is exercised -- without unioning
    # in `ci_node_at_anchor`'s bound files, a change to test_b (bound only
    # via the CI evidence, e.g. a retag invisible to structural comparison)
    # would never intersect `changed` and would wrongly promote.
    node_anchor = {"tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    ci_node_anchor = {"tests": {"unit": [
        {"path": "tests/test_a.py::test_one"}, {"path": "tests/test_b.py::test_two"},
    ]}}
    node_head = {"tests": {"unit": [
        {"path": "tests/test_a.py::test_one"}, {"path": "tests/test_b.py::test_two"},
    ]}}
    changed = {"tests/test_b.py"}
    assert evidence_stale_since_anchor(node_anchor, ci_node_anchor, node_head, {"spec.md"}, changed) is True


def test_evidence_stale_since_anchor_true_when_the_fr_identity_differs_between_anchor_and_head():
    # Stage-3 doubt review, high (defense-in-depth half): nothing upstream
    # checks that the namespaced manifest key still names the same FR at
    # both commits. A hand-corrupted or reused key must not let one FR's
    # identity borrow another's anchor evidence.
    node_anchor = {"id": "FR-01.01", "tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    ci_node_anchor = node_anchor
    node_head = {"id": "FR-01.02", "tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    assert evidence_stale_since_anchor(node_anchor, ci_node_anchor, node_head, {"spec.md"}, set()) is True


def test_evidence_stale_since_anchor_true_when_a_new_unaccounted_test_file_changed():
    # Stage-3 doubt review, high (the substantive half): a test file added
    # or edited between the anchor and HEAD that no manifest-derived set
    # (anchor's committed manifest, anchor's CI evidence, HEAD's committed
    # manifest) has ever recorded as bound to ANYTHING is exactly the
    # "drifted, unregenerated HEAD manifest" case this whole mechanism
    # exists to operate in -- and none of the other checks in this function
    # can ever catch it, since by construction it is absent from every set
    # they compare. Binding is identical at both ends (no drift trigger);
    # only the unaccounted-file widening is exercised.
    node_anchor = {"id": "FR-01.01", "tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    ci_node_anchor = node_anchor
    node_head = node_anchor
    changed = {"tests/e2e/test_a_flow.py"}  # new file; not in any bound set
    assert evidence_stale_since_anchor(node_anchor, ci_node_anchor, node_head, {"spec.md"}, changed) is True


def test_evidence_stale_since_anchor_false_when_an_unrelated_non_test_file_changed():
    # Control for the unaccounted-test-file widening above: a changed path
    # that does not look like a test file at all must not trip it.
    node_anchor = {"id": "FR-01.01", "tests": {"unit": [{"path": "tests/test_a.py::test_one"}]}}
    ci_node_anchor = node_anchor
    node_head = node_anchor
    changed = {"docs/README.md"}
    assert evidence_stale_since_anchor(node_anchor, ci_node_anchor, node_head, {"spec.md"}, changed) is False


@pytest.mark.parametrize("path", [
    "tests/test_a.py",
    "shared/scripts/tools/tests/test_foo.py",
    "some/dir/foo_test.py",
    "tests\\windows\\test_win.py",
])
def test__looks_like_test_path_recognises_pytest_conventions(path):
    assert _looks_like_test_path(path) is True


@pytest.mark.parametrize("path", [
    "docs/README.md",
    "shared/scripts/tools/promote_required_layers.py",
    "tests/fixtures/data.json",
    "testsuite/helper.py",  # "tests" only as a substring, not a path segment
])
def test__looks_like_test_path_rejects_non_test_paths(path):
    assert _looks_like_test_path(path) is False


def test_changed_paths_between_lists_files_touched_between_two_commits(tmp_path):
    project = _init_repo(tmp_path)
    anchor = _commit(project, {"a.py": "1", "b.py": "1"}, "anchor")
    head = _commit(project, {"a.py": "2"}, "touch a")

    changed = changed_paths_between(anchor, head, project_root=project)
    assert changed == {"a.py"}


def test_changed_paths_between_empty_when_commits_are_identical(tmp_path):
    project = _init_repo(tmp_path)
    sha = _commit(project, {"a.py": "1"}, "only commit")
    assert changed_paths_between(sha, sha, project_root=project) == set()


def test_changed_paths_between_no_renames_shows_the_old_path_on_a_pure_rename(tmp_path):
    # The exact case the module docstring calls out: a test file MOVED to
    # another requirement is a rename by git's own heuristic -- `--no-renames`
    # is what keeps the OLD bound path showing up as "changed" rather than
    # collapsing into a rename entry that could omit it.
    project = _init_repo(tmp_path)
    anchor = _commit(project, {"tests/test_old.py": "def test_x():\n    pass\n" * 5}, "anchor")
    (project / "tests" / "test_old.py").rename(project / "tests" / "test_new.py")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "rename")
    head = _git(project, "rev-parse", "HEAD").strip()

    changed = changed_paths_between(anchor, head, project_root=project)
    assert "tests/test_old.py" in changed
    assert "tests/test_new.py" in changed


def test_changed_paths_between_no_renames_shows_the_old_path_on_a_rename_plus_edit(tmp_path):
    # The trap the module docstring names explicitly: a rename WITH a
    # substantial content edit is exactly where git's similarity-based
    # rename detection is most eager to fire -- if it did, `--name-only`
    # would collapse this into a single rename entry and could omit the old
    # path, the one this guard actually needs to see as "changed".
    project = _init_repo(tmp_path)
    anchor = _commit(project, {"tests/test_old.py": "def test_x():\n    pass\n" * 5}, "anchor")
    (project / "tests" / "test_old.py").rename(project / "tests" / "test_new.py")
    (project / "tests" / "test_new.py").write_text(
        "def test_completely_different():\n    assert 1 == 2\n" * 5, encoding="utf-8",
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "rename and edit")
    head = _git(project, "rev-parse", "HEAD").strip()

    changed = changed_paths_between(anchor, head, project_root=project)
    assert "tests/test_old.py" in changed
    assert "tests/test_new.py" in changed


def test_changed_paths_between_returns_none_on_a_non_sha_commit_without_running_git(tmp_path):
    # External code review, low: both commits reach `git diff ...
    # f"{anchor}..{head}"` with no injection guard otherwise -- a value
    # starting with `-` would be parsed as a git option. Validated the same
    # way `ci_provenance._COMMIT_RE` already validates its own `commit`.
    project = _init_repo(tmp_path)
    sha = _commit(project, {"a.py": "1"}, "only commit")
    assert changed_paths_between("--output=/tmp/pwned", sha, project_root=project) is None
    assert changed_paths_between(sha, "--output=/tmp/pwned", project_root=project) is None


def test_changed_paths_between_returns_none_on_git_failure(tmp_path):
    # Not a git repo at all, and not even valid commit-ish arguments.
    assert changed_paths_between("a" * 40, "b" * 40, project_root=tmp_path) is None


def test_dirty_or_untracked_paths_empty_on_a_clean_tree(tmp_path):
    project = _init_repo(tmp_path)
    _commit(project, {"a.py": "1"}, "only commit")
    assert dirty_or_untracked_paths(project_root=project) == set()


def test_dirty_or_untracked_paths_reports_an_uncommitted_edit_to_a_tracked_file(tmp_path):
    project = _init_repo(tmp_path)
    _commit(project, {"tests/test_a.py": "def test_a(): assert True\n"}, "commit")
    (project / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    assert dirty_or_untracked_paths(project_root=project) == {"tests/test_a.py"}


def test_dirty_or_untracked_paths_reports_a_staged_edit(tmp_path):
    project = _init_repo(tmp_path)
    _commit(project, {"tests/test_a.py": "def test_a(): assert True\n"}, "commit")
    (project / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    _git(project, "add", "-A")
    assert dirty_or_untracked_paths(project_root=project) == {"tests/test_a.py"}


def test_dirty_or_untracked_paths_reports_a_new_untracked_test_file(tmp_path):
    project = _init_repo(tmp_path)
    _commit(project, {"a.py": "1"}, "only commit")
    (project / "tests").mkdir()
    (project / "tests" / "test_new.py").write_text("def test_new(): assert True\n", encoding="utf-8")
    assert dirty_or_untracked_paths(project_root=project) == {"tests/test_new.py"}


def test_dirty_or_untracked_paths_returns_none_on_git_failure(tmp_path):
    assert dirty_or_untracked_paths(project_root=tmp_path) is None


def test_anchor_fallback_treats_an_uncommitted_edit_to_a_bound_test_as_invalidating():
    # This is the fix for the Tier-3 PR review BLOCK on this iterate's own PR:
    # `changed_paths_between` only diffs COMMITS, so an operator's own
    # uncommitted edit to a bound test file must be caught some other way --
    # `dirty_or_untracked_paths` is what `promote_required_layers.py` unions
    # into `changed` before calling this function; prove the union alone
    # (with no committed diff at all) is sufficient to flag staleness.
    node = {
        "id": "FR-01.01", "spec_path": "spec.md",
        "tests": {"unit": [{"path": "tests/test_bound.py::test_x"}]},
    }
    dirty = {"tests/test_bound.py"}  # as `dirty_or_untracked_paths` would report it
    assert evidence_stale_since_anchor(node, node, node, {"spec.md"}, dirty) is True


def test_reason_code_constant_is_the_documented_string():
    assert REASON_EVIDENCE_STALE_SINCE_ANCHOR == "evidence_stale_since_anchor"
