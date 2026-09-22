"""CLI tests for shared/scripts/checks/check_review_attribution.py (R3)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_review_attribution.py"

_spec = importlib.util.spec_from_file_location("check_review_attribution_for_test", _CLI)
assert _spec is not None and _spec.loader is not None
check_review_attribution = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_review_attribution)


def _write_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "test-loop", "units": units}), encoding="utf-8")


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", f"add {name}"],
                    check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()


def test_pin_then_verify_reviewed_head_allow(git_origin_repo, capsys):
    work, _ = git_origin_repo
    head = _commit(work, "x.txt")
    state = work / ".shipwright" / "loop_state.json"
    _write_state(state, [{"id": "P", "branch": "main", "attempt": 0}])

    rc = check_review_attribution.main([
        "--mode", "pin", "--state", str(state), "--unit-id", "P",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop", "--json",
    ])
    assert rc == 0
    pin_payload = json.loads(capsys.readouterr().out)
    assert pin_payload["reviewed_head"] == head

    rc = check_review_attribution.main([
        "--mode", "verify", "--state", str(state), "--unit-id", "P",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop", "--against", "reviewed_head", "--json",
    ])
    assert rc == 0
    verify_payload = json.loads(capsys.readouterr().out)
    assert verify_payload["decision"] == "allow"


def test_verify_block_on_moved_branch(git_origin_repo, capsys):
    work, _ = git_origin_repo
    _commit(work, "y.txt")
    state = work / ".shipwright" / "loop_state.json"
    _write_state(state, [{"id": "Q", "branch": "main", "attempt": 0}])

    check_review_attribution.main([
        "--mode", "pin", "--state", str(state), "--unit-id", "Q",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop",
    ])
    capsys.readouterr()
    _commit(work, "z.txt")

    rc = check_review_attribution.main([
        "--mode", "verify", "--state", str(state), "--unit-id", "Q",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop", "--against", "reviewed_head",
    ])
    assert rc == 1
    assert "BLOCK" in capsys.readouterr().out


def test_verify_exits_nonzero_for_unknown_unit(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R", "branch": "main", "attempt": 0}])

    rc = check_review_attribution.main([
        "--mode", "verify", "--state", str(state), "--unit-id", "does-not-exist",
        "--project-root", str(tmp_path), "--campaign-worktree", str(tmp_path),
        "--loop-id", "test-loop", "--against", "reviewed_head",
    ])
    assert rc == 1
    assert "BLOCK" in capsys.readouterr().err


def test_pin_then_ship_then_verify_shipped_head_allow(git_origin_repo, capsys):
    work, _ = git_origin_repo
    _commit(work, "s1.txt")
    state = work / ".shipwright" / "loop_state.json"
    _write_state(state, [{"id": "S", "branch": "main", "attempt": 0}])

    check_review_attribution.main([
        "--mode", "pin", "--state", str(state), "--unit-id", "S",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop",
    ])
    capsys.readouterr()
    shipped = _commit(work, "reviews.json")

    rc = check_review_attribution.main([
        "--mode", "ship", "--state", str(state), "--unit-id", "S",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop", "--shipped-head", shipped, "--json",
    ])
    assert rc == 0
    ship_payload = json.loads(capsys.readouterr().out)
    assert ship_payload["shipped_head"] == shipped

    rc = check_review_attribution.main([
        "--mode", "verify", "--state", str(state), "--unit-id", "S",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "test-loop", "--against", "shipped_head", "--json",
    ])
    assert rc == 0
    verify_payload = json.loads(capsys.readouterr().out)
    assert verify_payload["decision"] == "allow"


def test_mode_ship_requires_shipped_head_flag(tmp_path):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "T", "branch": "main", "attempt": 0}])

    try:
        check_review_attribution.main([
            "--mode", "ship", "--state", str(state), "--unit-id", "T",
            "--project-root", str(tmp_path), "--campaign-worktree", str(tmp_path),
            "--loop-id", "test-loop",
        ])
        assert False, "expected SystemExit for a missing --shipped-head"
    except SystemExit as exc:
        assert exc.code == 2


def test_mode_pin_rejects_a_ship_only_flag(tmp_path):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "U", "branch": "main", "attempt": 0}])

    try:
        check_review_attribution.main([
            "--mode", "pin", "--state", str(state), "--unit-id", "U",
            "--project-root", str(tmp_path), "--campaign-worktree", str(tmp_path),
            "--loop-id", "test-loop", "--shipped-head", "a" * 40,
        ])
        assert False, "expected SystemExit: --shipped-head is not valid with --mode pin"
    except SystemExit as exc:
        assert exc.code == 2


def test_mode_ship_rejects_a_verify_only_flag(tmp_path):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "W", "branch": "main", "attempt": 0}])

    try:
        check_review_attribution.main([
            "--mode", "ship", "--state", str(state), "--unit-id", "W",
            "--project-root", str(tmp_path), "--campaign-worktree", str(tmp_path),
            "--loop-id", "test-loop", "--shipped-head", "b" * 40,
            "--against", "reviewed_head",
        ])
        assert False, "expected SystemExit: --against is not valid with --mode ship"
    except SystemExit as exc:
        assert exc.code == 2


def test_mode_verify_rejects_a_pin_only_flag(tmp_path):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "V", "branch": "main", "attempt": 0}])

    try:
        check_review_attribution.main([
            "--mode", "verify", "--state", str(state), "--unit-id", "V",
            "--project-root", str(tmp_path), "--campaign-worktree", str(tmp_path),
            "--loop-id", "test-loop", "--against", "reviewed_head",
            "--pr-node-id", "PR_kwDO",
        ])
        assert False, "expected SystemExit: --pr-node-id is not valid with --mode verify"
    except SystemExit as exc:
        assert exc.code == 2
