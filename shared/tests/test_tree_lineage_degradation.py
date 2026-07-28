"""``tree_lineage`` when git cannot answer
(iterate-2026-07-28-grade-snapshot-lineage).

Attribution is best-effort metadata on a producer — the compliance regen — that
must never fail because of it. Split from ``test_tree_lineage.py`` (which covers
what git *can* answer) when that file crossed the 300-line guideline; the seam is
the subject itself: resolution vs. degradation, plus the projection onto event
fields, which is where a partial answer either survives or is thrown away.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _tree_lineage_fixtures import ancestry_blinded, commit, git, init_repo  # noqa: E402
from tree_lineage import TreeLineage, lineage_fields, resolve_tree_lineage  # noqa: E402


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


class TestDegradation:
    def test_not_a_repo(self, tmp_path: Path):
        assert resolve_tree_lineage(tmp_path) == TreeLineage("unknown", None, None)

    def test_missing_directory(self, tmp_path: Path):
        assert resolve_tree_lineage(tmp_path / "nope") == TreeLineage("unknown", None, None)

    def test_empty_repo_with_no_commits(self, tmp_path: Path):
        root = tmp_path / "empty"
        root.mkdir()
        git(root, "init", "-b", "main")

        got = resolve_tree_lineage(root)
        assert got.lineage == "unknown"
        assert got.base is None

    def test_unrelated_histories_keep_lineage_and_branch_but_drop_base(self, repo: Path):
        # An orphan branch shares no ancestor with the default branch, so
        # merge-base has no answer. The two facts that ARE known must survive —
        # discarding all three because one is missing would lose real signal.
        git(repo, "checkout", "--orphan", "orphan")
        commit(repo, "solo.txt")

        got = resolve_tree_lineage(repo)
        assert got.branch == "orphan"
        assert got.lineage == "branch"
        assert got.base is None

    def test_absent_git_binary_degrades_to_unknown(self, repo: Path, monkeypatch):
        import tree_lineage

        def _boom(*_a, **_k):
            raise FileNotFoundError("git")

        monkeypatch.setattr(tree_lineage.subprocess, "run", _boom)
        assert resolve_tree_lineage(repo) == TreeLineage("unknown", None, None)

    def test_undecodable_git_output_degrades_instead_of_raising(self, repo: Path, monkeypatch):
        """git output need not be valid UTF-8 (external code review, low).

        A ``UnicodeDecodeError`` is a ``ValueError`` — caught by neither
        ``OSError`` nor ``SubprocessError`` — so strict decoding would raise
        straight through the module's "nothing here raises" contract. Direct
        callers of the resolver, unlike the two event producers, have no outer
        handler to save them. The resolver defends this twice: ``errors="replace"``
        so the decode cannot fail, and this catch so the contract survives anyone
        later tightening it.
        """
        import tree_lineage

        def _undecodable(*_a, **_k):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        monkeypatch.setattr(tree_lineage.subprocess, "run", _undecodable)

        assert resolve_tree_lineage(repo) == TreeLineage("unknown", None, None)

    def test_git_timeout_degrades_to_unknown(self, repo: Path, monkeypatch):
        import tree_lineage

        def _slow(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=5)

        monkeypatch.setattr(tree_lineage.subprocess, "run", _slow)
        assert resolve_tree_lineage(repo) == TreeLineage("unknown", None, None)


class TestUnresolvableAncestry:
    """git exits 0 = ancestor, 1 = not an ancestor, anything else = could not
    tell. Collapsing that third case into "not an ancestor" would silently
    relabel main-lineage trees as branches (external code review, bug/medium)."""

    def test_error_does_not_override_a_default_branch_checkout(self, repo: Path, monkeypatch):
        # Still on the default branch, so the NAME comparison must carry it.
        assert ancestry_blinded(monkeypatch, repo).lineage == "main"

    def test_a_named_branch_never_reaches_the_ancestry_check(self, repo: Path, monkeypatch):
        # Since the fork-point fix a NAMED branch is decided by name alone, so
        # blinding ancestry must make no difference at all. Kept as the guard
        # that the two code paths stay separated.
        git(repo, "checkout", "-b", "iterate/x")
        commit(repo, "two.txt")

        assert ancestry_blinded(monkeypatch, repo).lineage == "branch"
        assert resolve_tree_lineage(repo).lineage == "branch"

    def test_detached_head_becomes_unknown_not_branch(self, repo: Path, monkeypatch):
        # Detached, so there is no name to fall back on and ancestry was the
        # only thing that could decide. Guessing "branch" here would file a
        # main-lineage measurement under the wrong subject.
        first = git(repo, "rev-parse", "HEAD")
        commit(repo, "two.txt")
        git(repo, "checkout", "--detach", first)

        assert ancestry_blinded(monkeypatch, repo).lineage == "unknown"


class TestLineageFields:
    """The projection onto event keys — where a partial answer either survives
    or is silently thrown away."""

    def test_resolved_tree_projects_all_three(self, repo: Path):
        fields = lineage_fields(resolve_tree_lineage(repo))
        assert fields["lineage"] == "main"
        assert fields["branch"] == "main"
        # Width is NOT pinned to SHA-1's 40: the production rule is hex 7-64 so
        # a SHA-256 repository keeps its attribution, and asserting 40 here
        # would turn red on a git defaulting to sha256 while the code is right.
        assert 7 <= len(fields["base"]) <= 64

    def test_unknown_projects_lineage_only(self):
        # `lineage: "unknown"` is emitted EXPLICITLY rather than by omitting the
        # field: a producer that tried and could not tell must not be
        # indistinguishable from a legacy event written before attribution.
        assert lineage_fields(TreeLineage("unknown", None, None)) == {"lineage": "unknown"}

    def test_an_overlong_or_control_laden_branch_name_is_dropped(self):
        # `branch` is untrusted external data landing on a tracked, cross-repo,
        # append-only artifact that cannot honestly be rewritten. git's own ref
        # grammar makes these unreachable through the producers today, but "the
        # writer happens not to emit it" is not a bound.
        assert "branch" not in lineage_fields(TreeLineage("branch", "a" * 256, None))
        assert "branch" not in lineage_fields(TreeLineage("branch", "we\x00ird", None))
        assert lineage_fields(TreeLineage("branch", "a" * 255, None))["branch"] == "a" * 255

    def test_a_non_path_project_root_degrades_instead_of_raising(self):
        # `Path(project_root)` was the one statement that could raise past the
        # module's "nothing here raises" contract.
        assert resolve_tree_lineage(None) == TreeLineage("unknown", None, None)
        assert resolve_tree_lineage(3) == TreeLineage("unknown", None, None)

    def test_partial_resolution_keeps_what_is_known(self):
        got = lineage_fields(TreeLineage("branch", "iterate/x", None))
        assert got == {"lineage": "branch", "branch": "iterate/x"}

    def test_implausible_base_is_dropped_not_stamped(self):
        assert "base" not in lineage_fields(TreeLineage("branch", "b", "not-a-sha"))

    def test_sha256_width_object_name_is_accepted(self):
        # base is validated as hex 7-64 rather than assumed to be 40-char SHA-1,
        # so a SHA-256 repository is not silently stripped of its attribution.
        assert lineage_fields(TreeLineage("branch", "b", "a" * 64))["base"] == "a" * 64
