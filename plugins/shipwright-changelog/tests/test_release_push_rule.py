"""Unit P5: the shared "tip is the release" rule on real git (the hook and ``release.py push-tag`` judge every history shape alike)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lib import release_commit, release_push
from lib.release_runner import Recorder, subprocess_runner
from .test_release_p4_cli import HEAD, VERSION, seed  # noqa: F401

pytestmark = pytest.mark.covers("FR-01.09/AC01")

PLUGIN = Path(__file__).resolve().parents[1]
HOOKS = PLUGIN / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import release_descent  # noqa: E402
import release_guard  # noqa: E402

# ---- the one rule "this tip is the release", on real git ---------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", check=True)
    return done.stdout.strip()


def _commit(repo: Path, path: str, text: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _history(tmp_path: Path, case: str) -> tuple[Path, str, str]:
    """``(repo, release_commit, tip)`` for a history shape."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "base.txt", "base", "base")
    release_commit_sha = _commit(repo, "CHANGELOG.md", "release", "chore(release): v1")
    if case == "event":
        _commit(repo, "shipwright_events.jsonl", "{}", "event")
        _commit(repo, ".shipwright/events/drops/a.jsonl", "{}", "event drop")
    elif case == "amended":
        _git(repo, "commit", "-q", "--amend", "-m", "chore(release): v1 amended")
    elif case == "revert-pair":
        _commit(repo, "src/app.py", "x", "change")
        _git(repo, "revert", "--no-edit", "HEAD")
    elif case == "merge":
        _git(repo, "checkout", "-q", "-b", "side")
        _commit(repo, "shipwright_events.jsonl", "{}", "side event")
        _git(repo, "checkout", "-q", "main")
        _commit(repo, ".shipwright/events/drops/b.jsonl", "{}", "main event")
        _git(repo, "merge", "--no-ff", "-q", "-m", "merge", "side")
    elif case == "empty":
        _git(repo, "commit", "-q", "--allow-empty", "-m", "empty")
    elif case == "rebased":
        _git(repo, "reset", "-q", "--hard", "HEAD~1")
        _commit(repo, "other.txt", "other", "unrelated")
        _git(repo, "cherry-pick", release_commit_sha)
    elif case == "unrelated":
        _commit(repo, "src/app.py", "x", "feature")
    return repo, release_commit_sha, _git(repo, "rev-parse", "HEAD")


CASES = [("same", True), ("event", True), ("amended", False), ("revert-pair", False), ("merge", False), ("empty", False), ("rebased", False), ("unrelated", False)]


@pytest.mark.parametrize(("case", "is_release"), CASES)
def test_the_hook_and_push_tag_judge_every_history_shape_the_same_way(tmp_path, plugin_root, case, is_release):
    repo, commit, tip = _history(tmp_path, case)

    def git(*args: str) -> tuple[int, str]:
        done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
        return done.returncode, done.stdout

    assert release_guard._is_the_release(repo, commit, tip) is is_release  # the hook
    assert release_descent.is_the_release(git, commit, tip) is is_release  # the shared rule
    release_commit.write_state(repo, {"version": VERSION, "commit": commit, "tag": f"v{VERSION}", "checks_passed": []})
    seed(repo, mode="standalone", branch="main", on_trunk=True)
    _git(repo, "tag", "-f", f"v{VERSION}", commit)
    code, out = release_push.push_tag(Recorder(subprocess_runner, repo), plugin_root, version=VERSION)  # push-tag, real git
    assert (code, out["status"]) == ((0, "ok") if is_release else (1, "refused"))
    if not is_release:
        assert out["reason"] == "head_moved_since_release"


def test_the_hook_and_push_tag_share_one_rule_file_and_cannot_drift():
    assert "release_descent.is_the_release" in (HOOKS / "release_guard.py").read_text(encoding="utf-8")
    assert "release_descent.is_the_release" in (PLUGIN / "scripts" / "lib" / "release_push.py").read_text(encoding="utf-8")
    assert "merge-base" not in (HOOKS / "release_guard.py").read_text(encoding="utf-8") or "--is-ancestor" not in (HOOKS / "release_guard.py").read_text(encoding="utf-8")


