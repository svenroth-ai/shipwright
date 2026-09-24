"""Real-git tests for ``check_review_attribution.py --mode invalidate`` and
the staleness-cascade behavior it exists to support (campaign-dag-scheduler
R5b, ``sub-iterates/R5b-merge-lane.md``).

Lives in its own file (not ``test_review_attribution.py``, bloat-baseline
pinned with zero headroom at 640 lines) — same one-root convention as its
sibling, reusing the ``git_origin_repo`` fixture.

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
import subprocess
from pathlib import Path

import pytest

from lib.review_attribution import pin, ship, verify

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


class TestTwoSequentialMergesComposition:
    """The spec's own required integration test (R5b-merge-lane.md, Test
    strategy): "a real-git composition test across two sequential merges,
    asserting shipped_head/PR-identity checks at merge time." (External
    review, glm + openai: flagged as missing entirely from this file's first
    draft, which covered only the staleness-cascade pair.)

    No ``gh`` calls (this repo's test style avoids a live GitHub dependency
    for pure-git composition — see
    ``test_campaign_serial_composition_integration.py``'s own
    ``git push origin iterate/s1:main`` idiom, reused here): a "PR merge" is
    simulated as pushing the unit's branch onto ``main`` directly, which is
    exactly what ``gh pr merge --squash`` does from the git object model's
    own point of view.

    File name note (external review, glm, low): this file grew beyond pure
    ``--mode invalidate`` coverage into the staleness-cascade and (now) the
    composition test — both real-git scenarios sharing the same
    ``git_origin_repo`` fixture setup, which is why they live here rather
    than fragmenting one more file for each new real-git scenario.
    """

    def test_shipped_head_and_pr_identity_survive_two_sequential_merges(self, git_origin_repo):
        work, origin = git_origin_repo

        # --- Unit A: pin, ship (simulating 3f-bis's reviews.json commit),
        # verify at merge time, then land on main (the "PR merge"). ---
        _git(work, "checkout", "-b", "iterate/unit-a", "main")
        _commit_file(work, "a.txt", "v1\n")
        state_path = work / ".shipwright" / "loop_state.json"
        _write_loop_state(state_path, [
            {"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0},
            {"id": "B", "branch": "iterate/unit-b", "worktree": str(work), "attempt": 0},
        ])
        pinned_a = pin(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                       loop_id="r5b-test", default_branch="main",
                       pr_node_id="PR_NODE_A", pr_head_ref="iterate/unit-a", pr_base_ref="main")
        _commit_file(work, ".shipwright/planning/iterate/run-a/reviews.json", '{"self":"completed"}\n')
        shipped_a = _git(work, "rev-parse", "HEAD")
        ship(state_path, "A", project_root=str(work), campaign_worktree=str(work),
             loop_id="r5b-test", shipped_head=shipped_a)

        # Merge-time checks, mirroring 3g's own order: shipped_head first,
        # then the PR-identity fields the new pre-merge check (campaign-mode.md
        # 3g, R5b) compares against a fresh `gh pr view`.
        verified_a = verify(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                            loop_id="r5b-test", against="shipped_head")
        assert verified_a["ok"] is True
        assert verified_a["pin"]["pr_node_id"] == "PR_NODE_A"
        assert verified_a["pin"]["pr_head_ref"] == "iterate/unit-a"
        assert verified_a["pin"]["pr_base_ref"] == "main"
        assert verified_a["pin"]["shipped_head"] == shipped_a

        # "PR merge" — push A's branch onto main directly (git-object-model
        # equivalent of `gh pr merge --squash`), without ever advancing the
        # local `main` ref this worktree happens to have checked out.
        _git(work, "push", "origin", "iterate/unit-a:main")

        # --- Unit B: branches off the FRESH remote main (containing A's
        # merge), goes through the identical pin/ship/verify cycle, and its
        # own merge-time checks must be unaffected by A's unrelated merge. ---
        _git(work, "fetch", "origin")
        _git(work, "checkout", "-b", "iterate/unit-b", "origin/main")
        composed = (work / "a.txt").read_text(encoding="utf-8")
        assert composed == "v1\n", "B must compose on top of A's merge"
        _commit_file(work, "b.txt", "v1\n")
        pinned_b = pin(state_path, "B", project_root=str(work), campaign_worktree=str(work),
                       loop_id="r5b-test", default_branch="main",
                       pr_node_id="PR_NODE_B", pr_head_ref="iterate/unit-b", pr_base_ref="main")
        _commit_file(work, ".shipwright/planning/iterate/run-b/reviews.json", '{"self":"completed"}\n')
        shipped_b = _git(work, "rev-parse", "HEAD")
        ship(state_path, "B", project_root=str(work), campaign_worktree=str(work),
             loop_id="r5b-test", shipped_head=shipped_b)

        verified_b = verify(state_path, "B", project_root=str(work), campaign_worktree=str(work),
                            loop_id="r5b-test", against="shipped_head")
        assert verified_b["ok"] is True, (
            "A's unrelated merge to main must not affect B's own shipped_head "
            "verification at B's own merge time"
        )
        assert verified_b["pin"]["pr_node_id"] == "PR_NODE_B"
        assert verified_b["pin"]["pr_head_ref"] == "iterate/unit-b"
        assert verified_b["pin"]["pr_base_ref"] == "main"
        assert pinned_a["pr_node_id"] != pinned_b["pr_node_id"], (
            "sanity: the two units' PR identities must never be conflated"
        )
