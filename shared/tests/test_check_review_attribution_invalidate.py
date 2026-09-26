"""Real-git tests for ``check_review_attribution.py --mode invalidate`` and
the staleness-cascade behavior it exists to support (campaign-dag-scheduler
R5b, ``sub-iterates/R5b-merge-lane.md``).

Lives in its own file (not ``test_review_attribution.py``, bloat-baseline
pinned with zero headroom at 640 lines) — same one-root convention as its
sibling, reusing the ``git_origin_repo`` fixture. The spec's own required
two-sequential-merges composition test lives in the sibling
``test_check_review_attribution_composition.py`` (split out round 2, when
this file crossed the 300-line guideline).

Covers the sub-iterate spec's own two required staleness-cascade tests:
- NEGATIVE: an unrelated sibling merge advancing ``origin/main`` must NOT
  invalidate this unit's own pin (``verify`` keys off the branch's own tip,
  never off how far ``origin/<default>`` has moved).
- POSITIVE: an actual rebase of the unit's own branch changes its tip, so
  ``verify`` now BLOCKs, and ``invalidate`` deletes the pin so nothing can
  accidentally re-verify it against the old (pre-rebase) SHA.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from lib.review_attribution import pin, verify

# Mirrors test_check_review_attribution.py's own load-by-path convention:
# `shared/scripts/checks/` is not a package on sys.path, so the CLI module is
# loaded directly from its file rather than imported by dotted name.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_review_attribution.py"
_spec = importlib.util.spec_from_file_location("check_review_attribution_invalidate_for_test", _CLI)
assert _spec is not None and _spec.loader is not None
cra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cra)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write_loop_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "r5b-test", "kind": "sub_iterate", "units": units}),
                     encoding="utf-8")


def _commit_file(repo: Path, name: str, content: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"write {name}")
    return _git(repo, "rev-parse", "HEAD")


def test_invalidate_deletes_an_existing_pin(git_origin_repo):
    work, _origin = git_origin_repo
    _git(work, "checkout", "-b", "iterate/unit-a", "main")
    _commit_file(work, "a.txt", "v1\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])

    pin(state_path, "A", project_root=str(work), campaign_worktree=str(work),
        loop_id="r5b-test", default_branch="main")

    pin_path = work / ".shipwright" / "runs" / "r5b-test" / "A" / "a0" / "review_pin.json"
    legacy_path = work / ".shipwright" / "runs" / "r5b-test" / "A" / "reviewed_head"
    assert pin_path.exists() and legacy_path.exists()

    result = cra.invalidate(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                             loop_id="r5b-test", reason="rebase")
    assert result == {"unit_id": "A", "invalidated": True, "pin_existed": True, "reason": "rebase"}
    assert not pin_path.exists()
    assert not legacy_path.exists()


def test_invalidate_is_a_legal_noop_when_no_pin_exists(git_origin_repo):
    """The rebase cascade may re-enter more than once (max_rebase_reviews);
    invalidating an already-invalidated unit must never raise."""
    work, _origin = git_origin_repo
    _git(work, "checkout", "-b", "iterate/unit-a", "main")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])

    result = cra.invalidate(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                             loop_id="r5b-test", reason="rebase")
    assert result["pin_existed"] is False
    assert result["invalidated"] is True


def test_invalidate_rejects_a_control_character_in_reason(git_origin_repo):
    work, _origin = git_origin_repo
    _git(work, "checkout", "-b", "iterate/unit-a", "main")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])
    try:
        cra.invalidate(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                        loop_id="r5b-test", reason="bad\x00reason")
        raise AssertionError("expected a rejection for a control character in --reason")
    except cra.ReviewAttributionError:
        pass


def test_invalidate_rejects_a_path_traversal_loop_id(git_origin_repo):
    """Tier-3 review, R5b round 2, security finding: `loop_id` is a raw CLI
    argument joined straight into a path later passed to `unlink` — a crafted
    `--loop-id` containing `..` must be rejected before it can escape the
    intended `.shipwright/runs/<loop_id>/` tree, never silently deleting a
    file elsewhere in the project."""
    work, _origin = git_origin_repo
    _git(work, "checkout", "-b", "iterate/unit-a", "main")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])

    # A traversal loop_id of ".." resolves runs/../A to .shipwright/A — a file
    # this call must never be able to reach, let alone delete.
    canary = work / ".shipwright" / "A" / "reviewed_head"
    canary.parent.mkdir(parents=True, exist_ok=True)
    canary.write_text("do not delete", encoding="utf-8")

    try:
        cra.invalidate(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                        loop_id="..", reason="rebase")
        raise AssertionError("expected a rejection for a path-traversal loop_id")
    except cra.ReviewAttributionError:
        pass
    assert canary.exists(), "a rejected loop_id must never reach unlink()"


def test_invalidate_rejects_a_symlinked_unit_directory(git_origin_repo, tmp_path):
    """Tier-3 review, R5b round 4, security finding: `_safe_segment` rejects
    traversal in a segment's NAME, but a `unit_id` directory component that
    is itself a SYMLINK pointing outside `.shipwright/runs` would still let
    `unlink()` delete a file elsewhere. Plant exactly that and confirm
    `invalidate()` refuses rather than following it."""
    work, _origin = git_origin_repo
    _git(work, "checkout", "-b", "iterate/unit-a", "main")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])

    # A victim directory OUTSIDE .shipwright/runs entirely, holding a canary
    # this call must never be able to reach.
    victim = tmp_path / "victim"
    victim.mkdir()
    canary = victim / "reviewed_head"
    canary.write_text("do not delete", encoding="utf-8")

    runs_dir = work / ".shipwright" / "runs" / "r5b-test"
    runs_dir.mkdir(parents=True, exist_ok=True)
    unit_link = runs_dir / "A"
    try:
        os.symlink(victim, unit_link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        cra.invalidate(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                        loop_id="r5b-test", reason="rebase")
        raise AssertionError("expected a rejection for a symlinked unit directory")
    except cra.ReviewAttributionError:
        pass
    assert canary.exists(), "a rejected symlinked path component must never reach unlink()"
    assert canary.read_text(encoding="utf-8") == "do not delete"


def test_cli_invalidate_mode_end_to_end(git_origin_repo, capsys):
    work, _origin = git_origin_repo
    _git(work, "checkout", "-b", "iterate/unit-a", "main")
    _commit_file(work, "a.txt", "v1\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])
    pin(state_path, "A", project_root=str(work), campaign_worktree=str(work),
        loop_id="r5b-test", default_branch="main")

    rc = cra.main([
        "--mode", "invalidate", "--state", str(state_path), "--unit-id", "A",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "r5b-test", "--reason", "rebase", "--json",
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"unit_id": "A", "invalidated": True, "pin_existed": True, "reason": "rebase"}


def test_cli_rejects_a_flag_from_a_different_mode():
    with pytest.raises(SystemExit) as exc:
        cra.main([
            "--mode", "invalidate", "--state", "x", "--unit-id", "A",
            "--project-root", ".", "--campaign-worktree", ".", "--loop-id", "l",
            "--shipped-head", "deadbeef" * 5,
        ])
    assert exc.value.code == 2  # argparse.error() exits 2


class TestStalenessCascade:
    """The spec's own required negative/positive staleness-cascade pair."""

    def test_unrelated_sibling_merge_does_not_invalidate_this_units_pin(self, git_origin_repo):
        """NEGATIVE: origin/main advancing from an unrelated sibling's merge
        must not be mistaken for THIS unit's branch going stale."""
        work, origin = git_origin_repo
        _git(work, "checkout", "-b", "iterate/unit-a", "main")
        _commit_file(work, "a.txt", "v1\n")
        state_path = work / ".shipwright" / "loop_state.json"
        _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])
        pinned = pin(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r5b-test", default_branch="main")

        # An unrelated sibling merges its own unit B directly to origin/main,
        # advancing the default branch — A's own branch tip is untouched.
        _git(work, "checkout", "main")
        _commit_file(work, "b.txt", "sibling change\n")
        _git(work, "push", "origin", "main")
        _git(work, "checkout", "iterate/unit-a")

        result = verify(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                         loop_id="r5b-test", against="reviewed_head")
        assert result["ok"] is True
        assert result["current_tip"] == pinned["reviewed_head"]

    def test_an_actual_rebase_invalidates_the_pin(self, git_origin_repo):
        """POSITIVE: rebasing the unit's OWN branch changes its tip — verify
        now BLOCKs, and invalidate() removes the stale pin so nothing can
        accidentally trust it again."""
        work, origin = git_origin_repo
        _git(work, "checkout", "-b", "iterate/unit-a", "main")
        _commit_file(work, "a.txt", "v1\n")
        state_path = work / ".shipwright" / "loop_state.json"
        _write_loop_state(state_path, [{"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0}])
        pin(state_path, "A", project_root=str(work), campaign_worktree=str(work),
            loop_id="r5b-test", default_branch="main")

        # Advance main, then rebase A's own branch onto it -- A's tip moves.
        _git(work, "checkout", "main")
        _commit_file(work, "b.txt", "advance main\n")
        _git(work, "push", "origin", "main")
        _git(work, "checkout", "iterate/unit-a")
        _git(work, "rebase", "main")

        result = verify(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                         loop_id="r5b-test", against="reviewed_head")
        assert result["ok"] is False, "a rebase must change the branch tip and BLOCK verify"

        invalidated = cra.invalidate(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                                      loop_id="r5b-test", reason="rebase")
        assert invalidated["pin_existed"] is True
        pin_path = work / ".shipwright" / "runs" / "r5b-test" / "A" / "a0" / "review_pin.json"
        assert not pin_path.exists()
