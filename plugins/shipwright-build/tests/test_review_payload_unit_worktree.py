"""The SubagentStop salvage hook finds a campaign unit's ``reviews.json`` in the
unit's own worktree, not only under the session root.

A campaign runner works in its unit worktree, but a reviewer's hook fires with
the session's root; before this, the hook refused (``wrong_root``) and the
salvage never happened. The env cannot name the unit (``SHIPWRIGHT_LOOP_UNIT_ID``
is exported in the runner's Bash), so the worktrees ``loop_state.json`` records
are the candidates.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
RUN_ID = "iterate-2026-10-09-unit-worktree-salvage"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load("write_review_payload_on_stop_uw", "write-review-payload-on-stop.py")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   capture_output=True, text=True, check=True)


def _worktree(root: Path, name: str, run_dir_reviews: bool = True) -> Path:
    """A REGISTERED git worktree of ``root`` (the hook only trusts those)."""
    wt = root.parent / name
    _git(root, "worktree", "add", "-q", "-b", name, str(wt))
    if run_dir_reviews:
        run_dir = wt / ".shipwright" / "planning" / "iterate" / RUN_ID
        run_dir.mkdir(parents=True)
        (run_dir / "reviews.json").write_text(
            json.dumps({"reviews": {"code": {"status": "pending"}}}), encoding="utf-8")
    return wt


def _write_state(root: Path, worktrees: list) -> None:
    (root / ".shipwright").mkdir(exist_ok=True)
    (root / ".shipwright" / "loop_state.json").write_text(
        json.dumps({"units": [{"id": f"U{i}", "worktree": str(w)} for i, w in enumerate(worktrees)]}),
        encoding="utf-8")


def _campaign(tmp_path: Path, with_reviews: bool = True) -> tuple[Path, Path]:
    root = tmp_path / "main"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "commit", "-q", "--allow-empty", "-m", "init")
    unit_wt = _worktree(root, "unit-wt", run_dir_reviews=with_reviews)
    _write_state(root, [unit_wt])
    return root, unit_wt


def _stop(monkeypatch, tmp_path: Path, root: Path) -> int:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(x) for x in [
        {"role": "user", "content": f"This review is part of iterate run {RUN_ID}."},
        {"role": "assistant", "content": '{"section": "x", "review": []}'},
    ]), encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"transcript_path": str(transcript)})))
    monkeypatch.setattr("sys.stderr", io.StringIO())
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(root))
    return hook.main(["--review-type", "code"])


@pytest.mark.covers("FR-01.11")
def test_salvage_lands_in_the_unit_worktree(tmp_path, monkeypatch):
    root, unit_wt = _campaign(tmp_path)
    assert _stop(monkeypatch, tmp_path, root) == 0
    assert hook.salvage_path(unit_wt, RUN_ID, "code").exists()
    assert not hook.salvage_path(root, RUN_ID, "code").parent.exists(), \
        "nothing may be planted in the session root"


@pytest.mark.covers("FR-01.11")
def test_still_refuses_when_no_unit_worktree_holds_the_run(tmp_path, monkeypatch):
    root, unit_wt = _campaign(tmp_path, with_reviews=False)
    assert _stop(monkeypatch, tmp_path, root) == 0
    assert not hook.salvage_path(unit_wt, RUN_ID, "code").parent.exists()
    assert not hook.salvage_path(root, RUN_ID, "code").parent.exists()


@pytest.mark.covers("FR-01.11")
def test_the_same_worktree_listed_twice_is_not_ambiguous(tmp_path, monkeypatch):
    root, unit_wt = _campaign(tmp_path)
    _write_state(root, [unit_wt, str(unit_wt) + "/."])
    assert _stop(monkeypatch, tmp_path, root) == 0
    assert hook.salvage_path(unit_wt, RUN_ID, "code").exists()


@pytest.mark.covers("FR-01.11")
def test_two_distinct_worktrees_holding_the_run_are_ambiguous_and_refused(tmp_path, monkeypatch):
    root, unit_wt = _campaign(tmp_path)
    stale = _worktree(root, "stale-wt")
    _write_state(root, [unit_wt, stale])
    assert _stop(monkeypatch, tmp_path, root) == 0
    assert not hook.salvage_path(unit_wt, RUN_ID, "code").exists()
    assert not hook.salvage_path(stale, RUN_ID, "code").exists()


@pytest.mark.covers("FR-01.11")
def test_a_path_git_does_not_list_is_never_a_salvage_root(tmp_path, monkeypatch):
    """loop_state.json is runner-written: a crafted entry must not steer the write."""
    root, _unit_wt = _campaign(tmp_path, with_reviews=False)
    rogue = tmp_path / "rogue"
    (rogue / ".shipwright" / "planning" / "iterate" / RUN_ID).mkdir(parents=True)
    (rogue / ".shipwright" / "planning" / "iterate" / RUN_ID / "reviews.json").write_text(
        json.dumps({"reviews": {"code": {"status": "pending"}}}), encoding="utf-8")
    _write_state(root, [rogue])
    assert _stop(monkeypatch, tmp_path, root) == 0
    assert not hook.salvage_path(rogue, RUN_ID, "code").exists()


@pytest.mark.covers("FR-01.11")
def test_a_malformed_loop_state_degrades_to_the_session_root(tmp_path, monkeypatch):
    root, unit_wt = _campaign(tmp_path)
    (root / ".shipwright" / "loop_state.json").write_text("{not json", encoding="utf-8")
    assert _stop(monkeypatch, tmp_path, root) == 0
    assert not hook.salvage_path(unit_wt, RUN_ID, "code").exists()
