"""Route reporting extended to the `_status_flip`/`promote` dispatch
(iterate-2026-09-12-triage-route-report).

Split out of `test_triage_route_report.py` to keep that file under the
300-LOC guideline. Covers `dismiss`'s non-`--json` path, `defer`, `unpark`
and `promote` — the four writers that go through
`shared/scripts/tools/triage_promote.py` rather than calling `mark_status`
directly. External code review (GLM via OpenRouter and OpenAI/Codex,
independently) flagged that `dismiss`'s non-JSON path was silent about its
write target even after the direct-`mark_status` call sites were fixed,
since it alone bypassed those call sites for `triage_promote.dismiss()`'s
own result dict.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item  # noqa: E402

CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "commit", "--allow-empty", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")
    _git(tmp_path, "remote", "add", "origin", str(tmp_path / "origin-throwaway"))
    return tmp_path


def _seed(project: Path) -> str:
    return append_triage_item(
        project, source="test", severity="medium", kind="bug",
        title="Route report fixture", detail="d", dedup_key=None,
    )


def _run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--project-root", str(project), *args],
        capture_output=True, text=True, check=False,
    )


def test_dismiss_non_json_reports_the_route(git_repo: Path) -> None:
    outbox_id = _seed(git_repo)
    result = _run(git_repo, "dismiss", outbox_id, "--reason", "r")
    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr

    _git(git_repo, "checkout", "-b", "iterate/some-work")
    branch_id = _seed(git_repo)
    result = _run(git_repo, "dismiss", branch_id, "--reason", "r")
    assert result.returncode == 0, result.stderr
    assert "recorded on branch 'iterate/some-work'" in result.stderr


def test_defer_reports_the_route(git_repo: Path) -> None:
    outbox_id = _seed(git_repo)
    result = _run(git_repo, "defer", outbox_id, "--reason", "r", "--revisit", "2099-01-01")
    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr

    _git(git_repo, "checkout", "-b", "iterate/some-work")
    branch_id = _seed(git_repo)
    result = _run(git_repo, "defer", branch_id, "--reason", "r", "--revisit", "2099-01-01")
    assert result.returncode == 0, result.stderr
    assert "recorded on branch 'iterate/some-work'" in result.stderr


def test_unpark_reports_the_route(git_repo: Path) -> None:
    outbox_id = _seed(git_repo)
    _run(git_repo, "defer", outbox_id, "--reason", "r", "--revisit", "2099-01-01")
    result = _run(git_repo, "unpark", outbox_id, "--reason", "r")
    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr

    _git(git_repo, "checkout", "-b", "iterate/some-work")
    branch_id = _seed(git_repo)
    _run(git_repo, "defer", branch_id, "--reason", "r", "--revisit", "2099-01-01")
    result = _run(git_repo, "unpark", branch_id, "--reason", "r")
    assert result.returncode == 0, result.stderr
    assert "recorded on branch 'iterate/some-work'" in result.stderr


def test_promote_reports_the_route(git_repo: Path) -> None:
    outbox_id = _seed(git_repo)
    result = _run(git_repo, "promote", outbox_id, "--task-ref", "EXT:x-1")
    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr

    _git(git_repo, "checkout", "-b", "iterate/some-work")
    branch_id = _seed(git_repo)
    result = _run(git_repo, "promote", branch_id, "--task-ref", "EXT:x-2")
    assert result.returncode == 0, result.stderr
    assert "recorded on branch 'iterate/some-work'" in result.stderr


@pytest.mark.parametrize("command,extra", (
    ("dismiss", ("--reason", "r")),
    ("defer", ("--reason", "r", "--revisit", "2099-01-01")),
    ("unpark", ("--reason", "r")),
    ("promote", ("--task-ref", "EXT:x-3")),
))
def test_status_flip_and_promote_json_reports_the_route(
    git_repo: Path, command: str, extra: tuple[str, ...],
) -> None:
    item_id = _seed(git_repo)
    if command == "unpark":
        _run(git_repo, "defer", item_id, "--reason", "r", "--revisit", "2099-01-01")
    result = _run(git_repo, command, item_id, *extra, "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["route"] == "outbox"
