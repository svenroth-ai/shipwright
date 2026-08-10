"""`_reclaim_orphaned_merge_worktrees` (P2.59): self-heals a merge-scope
worktree a prior killed run orphaned, scoped by name so it cannot touch a
different session's parallel iterate worktree, and age-gated so it cannot
touch a SAME-prefix worktree a concurrent merge audit still has open.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "shared" / "scripts" / "tools" / "audit_compliance_lifecycle.py"
_spec = importlib.util.spec_from_file_location("lifecycle_reclaim_tool", TOOL)
lifecycle_tool = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(lifecycle_tool)


def _worktree_paths(work: Path) -> set[Path]:
    listed = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=work,
                            capture_output=True, text=True, check=True)
    return {Path(line[len("worktree "):]) for line in listed.stdout.splitlines()
           if line.startswith("worktree ")}


def _backdate(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def _make_detached_worktree(work: Path, suffix: str) -> Path:
    """Mirror exactly how `main()`'s merge scope creates one: `mkdtemp` under
    the SAME prefix the sweep matches on, then a detached checkout into it —
    the only shape `_is_own_detached_worktree` now accepts (code review
    MEDIUM: name-prefix alone was not a safe delete guard)."""
    path = Path(tempfile.mkdtemp(prefix=f"{lifecycle_tool._WORKTREE_PREFIX}{suffix}-"))
    subprocess.run(["git", "-C", str(work), "worktree", "add", "--detach", str(path), "HEAD"],
                   capture_output=True, text=True, check=True)
    return path


def test_reclaims_only_its_own_orphaned_worktree(git_origin_repo, make_worktree):
    work, _origin = git_origin_repo
    orphan = _make_detached_worktree(work, "orphan")
    _backdate(orphan, lifecycle_tool._RECLAIM_MIN_AGE_SECONDS + 60)
    other_session = make_worktree(work, "unrelated-iterate")

    lifecycle_tool._reclaim_orphaned_merge_worktrees(work)

    paths = _worktree_paths(work)
    assert orphan not in paths
    assert other_session in paths
    assert not orphan.exists()
    assert other_session.exists()


def test_leaves_a_branch_checked_out_same_prefix_worktree_alone(git_origin_repo, make_worktree):
    """The exact collision the guard exists to prevent: an iterate branch
    checked out under `.worktrees/<slug>` whose slug happens to start with
    the tool's prefix. Old (or a young) is irrelevant — it is neither
    detached nor under the system temp dir, so it can never be one of this
    tool's own worktrees (code review MEDIUM, P2.59)."""
    work, _origin = git_origin_repo
    branch_checkout = make_worktree(work, f"{lifecycle_tool._WORKTREE_PREFIX}slug")
    _backdate(branch_checkout, lifecycle_tool._RECLAIM_MIN_AGE_SECONDS + 60)

    lifecycle_tool._reclaim_orphaned_merge_worktrees(work)

    paths = _worktree_paths(work)
    assert branch_checkout in paths
    assert branch_checkout.exists()


def test_no_op_when_nothing_matches_the_prefix(git_origin_repo, make_worktree):
    work, _origin = git_origin_repo
    kept = make_worktree(work, "unrelated-iterate")

    lifecycle_tool._reclaim_orphaned_merge_worktrees(work)

    assert kept in _worktree_paths(work)


def test_leaves_a_fresh_same_prefix_worktree_alone(git_origin_repo):
    """A second merge audit landing within the same short window creates a
    prefix-matching, detached, tempdir-rooted worktree that is still live,
    not orphaned — the reclaim sweep's age gate must not delete it out from
    under that run."""
    work, _origin = git_origin_repo
    live = _make_detached_worktree(work, "live")

    lifecycle_tool._reclaim_orphaned_merge_worktrees(work)

    paths = _worktree_paths(work)
    # Windows' ``tempfile`` can return an 8.3 path (``RUNNER~1``), while
    # ``git worktree list`` expands it to the long user-profile path.  They
    # identify the same directory, so compare filesystem identity rather than
    # the two spellings.
    assert any(live.samefile(path) for path in paths)
    assert live.exists()


def test_failed_worktree_add_does_not_leak_the_temp_directory(git_origin_repo, monkeypatch, tmp_path):
    """`mkdtemp` creates its directory before `worktree add` can fail on an
    unfetchable sha — never registered as a real worktree, so the reclaim
    sweep (which iterates `git worktree list`) can never find it. `main()`
    must remove it directly in that branch (doubt review round 3, LOW)."""
    work, _origin = git_origin_repo
    leaked = tmp_path / f"{lifecycle_tool._WORKTREE_PREFIX}leak"
    monkeypatch.setattr(lifecycle_tool.tempfile, "mkdtemp",
                        lambda prefix: (leaked.mkdir(), str(leaked))[1])
    monkeypatch.setattr(lifecycle_tool, "_merge_sha", lambda pr, repo: "b" * 40)

    assert lifecycle_tool.main([
        "--scope", "merge", "--project-root", str(work), "--pr", "1", "--repo", "o/r",
    ]) == 1
    assert not leaked.exists()
