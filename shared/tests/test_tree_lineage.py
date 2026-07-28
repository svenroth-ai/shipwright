"""``tree_lineage`` — which tree did a measurement come from?
(iterate-2026-07-28-grade-snapshot-lineage)

A ``grade_snapshot`` records a Control Grade, which is a property of a **tree
state**. Every iterate measures its own worktree and union-merges the event onto
``main``, so without attribution one timeline holds many subjects. This module
resolves the three facts that tell them apart: ``lineage``, ``branch``, ``base``.

This file covers what git **can** answer; the degradation paths (and the event
field projection) live in ``test_tree_lineage_degradation.py``. Fixtures build
real repositories — see ``_tree_lineage_fixtures``.
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

from _tree_lineage_fixtures import commit, git, init_repo  # noqa: E402
from tree_lineage import resolve_tree_lineage  # noqa: E402


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


class TestLineageMainVsBranch:
    def test_default_branch_is_main_lineage(self, repo: Path):
        got = resolve_tree_lineage(repo)
        assert got.lineage == "main"
        assert got.branch == "main"

    def test_branch_with_unmerged_commits_is_branch_lineage(self, repo: Path):
        git(repo, "checkout", "-b", "iterate/x")
        commit(repo, "two.txt")

        got = resolve_tree_lineage(repo)
        assert got.lineage == "branch"
        assert got.branch == "iterate/x"

    def test_branch_with_no_commits_of_its_own_is_still_main_lineage(self, repo: Path):
        # Branched but not yet diverged: the tree contains nothing that is not
        # already on main, so calling it "branch" would misreport the subject.
        git(repo, "checkout", "-b", "iterate/empty")

        assert resolve_tree_lineage(repo).lineage == "main"

    def test_default_branch_ahead_of_its_remote_is_still_main_lineage(self, tmp_path: Path):
        # Local `main` with an unpushed commit is not an ancestor of
        # `origin/main`, so only the NAME comparison can carry this. Reporting
        # "branch" for a checkout literally on the default branch would be
        # indefensible to anyone reading the log.
        origin = init_repo(tmp_path / "origin")
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", str(origin), str(clone)],
                       capture_output=True, text=True, check=True)
        git(clone, "config", "user.email", "fixture@example.invalid")
        git(clone, "config", "user.name", "fixture")
        git(clone, "config", "commit.gpgsign", "false")
        commit(clone, "ahead.txt")

        assert resolve_tree_lineage(clone).lineage == "main"


class TestBase:
    def test_base_is_the_branch_point_not_head(self, repo: Path):
        main_tip = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-b", "iterate/x")
        head = commit(repo, "two.txt")

        got = resolve_tree_lineage(repo)
        assert got.base == main_tip
        assert got.base != head

    def test_base_on_default_branch_is_head(self, repo: Path):
        assert resolve_tree_lineage(repo).base == git(repo, "rev-parse", "HEAD")

    def test_base_is_hex_of_plausible_length(self, repo: Path):
        base = resolve_tree_lineage(repo).base
        assert base is not None
        assert 7 <= len(base) <= 64
        assert base == base.lower()
        assert all(c in "0123456789abcdef" for c in base)


class TestDefaultBranchResolution:
    """Conservative resolution (external plan review, edge-case/high).

    Falling back to the literal string ``main`` would label a regen ON a
    ``master`` repo's default branch as ``"branch"``, and would let a stray local
    ``main`` hijack a repository whose default is something else.
    """

    def test_master_default_repo_is_main_lineage_on_master(self, tmp_path: Path):
        repo = init_repo(tmp_path / "m", branch="master")

        got = resolve_tree_lineage(repo)
        assert got.lineage == "main"
        assert got.branch == "master"

    def test_trunk_default_repo_is_main_lineage_on_trunk(self, tmp_path: Path):
        repo = init_repo(tmp_path / "t", branch="trunk")
        assert resolve_tree_lineage(repo).lineage == "main"

    def test_no_resolvable_default_yields_unknown_not_assumed_main(self, tmp_path: Path):
        # Only a branch named `weird` exists: no origin/HEAD, and none of the
        # candidate default names resolve. Guessing "main" here would invent a
        # default branch that does not exist.
        repo = init_repo(tmp_path / "w", branch="weird")

        got = resolve_tree_lineage(repo)
        assert got.lineage == "unknown"
        assert got.branch == "weird"   # what IS known is still reported
        assert got.base is None

    def test_stray_local_main_does_not_hijack_a_master_repo(self, tmp_path: Path):
        # origin/HEAD exists and says `master`, so it must win over the
        # candidate probe, which would otherwise try `main` first.
        origin = init_repo(tmp_path / "origin", branch="master")
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", str(origin), str(clone)],
                       capture_output=True, text=True, check=True)
        git(clone, "branch", "main")   # stray local branch, not the default

        got = resolve_tree_lineage(clone)
        assert got.branch == "master"
        assert got.lineage == "main"


class TestDetachedHead:
    """Decided by ancestry, not by name (external plan review, edge-case/medium).

    A detached HEAD has no branch name to compare, so only ancestry can say
    whether the measured tree is main lineage. Ordering these correctly is the
    consumer's job via ``base`` — which is why the contract forbids ordering the
    trend by ``ts``.
    """

    def test_detached_at_default_tip_is_main_lineage(self, repo: Path):
        tip = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "--detach", tip)

        assert resolve_tree_lineage(repo).lineage == "main"

    def test_detached_at_older_default_commit_is_main_lineage(self, repo: Path):
        first = git(repo, "rev-parse", "HEAD")
        commit(repo, "two.txt")
        git(repo, "checkout", "--detach", first)

        got = resolve_tree_lineage(repo)
        # An older commit ON the default branch is still the main lineage: the
        # tree holds nothing that is not already on main. `base` pins it to its
        # real position in history, so a consumer ordering by `base` (as the
        # contract requires) places it correctly instead of plotting it as now.
        assert got.lineage == "main"
        assert got.base == first

    def test_detached_at_unmerged_branch_commit_is_branch_lineage(self, repo: Path):
        git(repo, "checkout", "-b", "side")
        side = commit(repo, "two.txt")
        git(repo, "checkout", "--detach", side)

        assert resolve_tree_lineage(repo).lineage == "branch"

    def test_detached_head_reports_no_branch_name(self, repo: Path):
        git(repo, "checkout", "--detach", git(repo, "rev-parse", "HEAD"))

        # git prints the literal "HEAD" here; stamping that as a branch name
        # would put a non-existent branch into the durable log.
        assert resolve_tree_lineage(repo).branch is None
