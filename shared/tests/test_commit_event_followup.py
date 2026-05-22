"""Tests for ``shared/scripts/tools/commit_event_followup.py``.

The F7-followup-commit tool exists because the iterate skill's F7 step writes
``shipwright_events.jsonl`` post-F6 — and in repos that *track* the event log
(via a ``!/shipwright_events.jsonl`` negation in .gitignore) the post-F6
write leaves a tracked-dirty file that vanishes on the next
``git reset --hard``. Each test sets up an isolated git repo with the
matching configuration and exercises one branch of the decision tree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "shared/scripts/tools/commit_event_followup.py"


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
        encoding="utf-8",
    )


def _init_repo(root: Path) -> None:
    """Initialize a minimal git repo with deterministic identity."""
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    _git(["config", "commit.gpgsign", "false"], root)


def _run_tool(project_root: Path, run_id: str = "iterate-test", **kwargs) -> dict:
    cmd = [sys.executable, str(TOOL), "--project-root", str(project_root), "--run-id", run_id]
    for k, v in kwargs.items():
        if v is None:
            continue
        if v is True:
            cmd.append(f"--{k.replace('_', '-')}")
            continue
        cmd.extend([f"--{k.replace('_', '-')}", str(v)])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding="utf-8")
    assert result.returncode == 0, f"tool failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    return json.loads(result.stdout)


@pytest.fixture
def tracked_repo(tmp_path: Path) -> Path:
    """events.jsonl is TRACKED (e.g. shipwright dev repo configuration)."""
    _init_repo(tmp_path)
    # Track shipwright_events.jsonl by committing it.
    (tmp_path / "shipwright_events.jsonl").write_text("{\"id\": \"evt-0001\"}\n", encoding="utf-8")
    _git(["add", "shipwright_events.jsonl"], tmp_path)
    _git(["commit", "-q", "-m", "init events log"], tmp_path)
    return tmp_path


@pytest.fixture
def ignored_repo(tmp_path: Path) -> Path:
    """events.jsonl is GITIGNORED (default Shipwright profile assumption)."""
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("shipwright_events.jsonl\n", encoding="utf-8")
    _git(["add", ".gitignore"], tmp_path)
    _git(["commit", "-q", "-m", "ignore events"], tmp_path)
    (tmp_path / "shipwright_events.jsonl").write_text("{\"id\": \"evt-0001\"}\n", encoding="utf-8")
    return tmp_path


def test_tracked_dirty_produces_followup_commit(tracked_repo: Path) -> None:
    # Simulate F7 append.
    events = tracked_repo / "shipwright_events.jsonl"
    events.write_text(events.read_text(encoding="utf-8") + "{\"id\": \"evt-0002\"}\n", encoding="utf-8")

    head_before = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()
    result = _run_tool(tracked_repo, run_id="iterate-2026-05-23-foo", event_id="evt-0002")
    head_after = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()

    assert result["status"] == "committed"
    assert head_before != head_after
    assert result["commit"] == head_after
    # commit message references run-id + event-id
    msg = _git(["log", "-1", "--format=%B", "HEAD"], tracked_repo).stdout
    assert "iterate-2026-05-23-foo" in msg
    assert "evt-0002" in msg
    # working tree is now clean
    assert _git(["diff", "--quiet", "--", "shipwright_events.jsonl"], tracked_repo, check=False).returncode == 0


def test_tracked_clean_is_noop(tracked_repo: Path) -> None:
    head_before = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()
    result = _run_tool(tracked_repo)
    head_after = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()

    assert result["status"] == "clean"
    assert head_before == head_after


def test_gitignored_is_noop_even_when_dirty(ignored_repo: Path) -> None:
    events = ignored_repo / "shipwright_events.jsonl"
    events.write_text(events.read_text(encoding="utf-8") + "{\"id\": \"evt-0002\"}\n", encoding="utf-8")

    head_before = _git(["rev-parse", "HEAD"], ignored_repo).stdout.strip()
    result = _run_tool(ignored_repo)
    head_after = _git(["rev-parse", "HEAD"], ignored_repo).stdout.strip()

    assert result["status"] == "ignored"
    assert head_before == head_after


def test_dry_run_makes_no_commit(tracked_repo: Path) -> None:
    events = tracked_repo / "shipwright_events.jsonl"
    events.write_text(events.read_text(encoding="utf-8") + "{\"id\": \"evt-0002\"}\n", encoding="utf-8")

    head_before = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()
    result = _run_tool(tracked_repo, dry_run=True)
    head_after = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()

    assert result["status"] == "dry_run"
    assert head_before == head_after
    # original dirty modification is still present
    assert _git(["diff", "--quiet", "--", "shipwright_events.jsonl"], tracked_repo, check=False).returncode != 0


def test_idempotency_after_first_commit(tracked_repo: Path) -> None:
    """Running the tool twice in a row after a single F7 append should produce
    one commit, not two. The second call sees a clean tree → noop."""
    events = tracked_repo / "shipwright_events.jsonl"
    events.write_text(events.read_text(encoding="utf-8") + "{\"id\": \"evt-0002\"}\n", encoding="utf-8")

    first = _run_tool(tracked_repo)
    assert first["status"] == "committed"
    second = _run_tool(tracked_repo)
    assert second["status"] == "clean"


def test_worktree_resolves_to_main_repo_and_commits_there(tracked_repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Mirror record_event.py's worktree resolution: F7b invoked with
    ``--project-root`` inside a linked worktree targets the MAIN repo's
    events.jsonl (where record_event.py actually wrote). Without this,
    the helper would check the worktree's copy (clean) and report
    ``clean`` even when the real log is dirty."""
    # Create a linked worktree from the tracked_repo.
    worktree_path = tmp_path_factory.mktemp("worktree")
    worktree_path.rmdir()  # mktemp creates it; git worktree add needs a non-existent path
    _git(["worktree", "add", "-b", "iterate/test-branch", str(worktree_path)], tracked_repo)

    # Dirty the main repo's events.jsonl (simulating an F7 record_event call
    # from inside the worktree — which resolves to the main repo).
    main_events = tracked_repo / "shipwright_events.jsonl"
    main_events.write_text(main_events.read_text(encoding="utf-8") + "{\"id\": \"evt-0002\"}\n", encoding="utf-8")

    head_before = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()
    result = _run_tool(worktree_path, run_id="iterate-worktree-test", event_id="evt-0002")
    head_after_main = _git(["rev-parse", "HEAD"], tracked_repo).stdout.strip()

    assert result["status"] == "committed", result
    # The commit landed on the MAIN repo, not the worktree branch.
    assert head_before != head_after_main
    assert result["commit"] == head_after_main
    # main_repo_root should be reported for observability
    assert "main_repo_root" in result
    assert Path(result["main_repo_root"]).resolve() == tracked_repo.resolve()


def test_commit_message_includes_co_author(tracked_repo: Path) -> None:
    events = tracked_repo / "shipwright_events.jsonl"
    events.write_text(events.read_text(encoding="utf-8") + "{\"id\": \"evt-0002\"}\n", encoding="utf-8")

    result = _run_tool(
        tracked_repo,
        run_id="iterate-2026-05-23-foo",
        co_author="Claude <noreply@anthropic.com>",
    )
    assert result["status"] == "committed"
    msg = _git(["log", "-1", "--format=%B", "HEAD"], tracked_repo).stdout
    assert "Co-Authored-By: Claude <noreply@anthropic.com>" in msg
