"""Route reporting for triage status/amend writes (iterate-2026-09-12-triage-
route-report).

`mark_status` / `amend_triage_item` derive the outbox-vs-tracked write target
(`should_route_to_outbox`) but, until this change, `mark_status` never told
the caller which one it picked and neither CLI writer said so to the
operator. Three same-session flips (`trg-ff6ea5f0`/`trg-5ae23b62`/
`trg-4fac93bf`) landed tracked-on-a-freshly-created-branch instead of the
outbox an idle-main flip would have used, and each needed its own PR before
the operator noticed. This is a dedicated module (not folded into
`test_triage_outbox.py`/`test_triage_cli_machine_transitions.py`) so those
files' own bloat-baseline entries aren't ratcheted by an unrelated feature's
tests.

Library-level: `mark_status(return_item=True)`'s new `(previous, item,
to_outbox)` triple. CLI-level: the `route` key in `--json` output and the
stderr note for the human path, for `dismiss --json`/`snooze`/`amend`/`show`
plus the negative (no-note) case. The extended dispatch coverage (`dismiss`
non-json, `defer`, `unpark`, `promote`) lives in
`test_triage_route_report_dispatch.py` to keep this file under budget.
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

from triage import (  # noqa: E402
    OUTBOX_FILE,
    TRIAGE_FILE,
    append_triage_item,
    mark_status,
    should_route_to_outbox,
)

CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"


def _tracked_path(project: Path) -> Path:
    return project / ".shipwright" / TRIAGE_FILE


def _outbox_path(project: Path) -> Path:
    return project / ".shipwright" / OUTBOX_FILE


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


@pytest.fixture
def git_repo_no_origin(tmp_path: Path) -> Path:
    """No origin remote → `should_route_to_outbox` is always False (tracked),
    even while idle on the default branch — the case a note must stay silent for."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "commit", "--allow-empty", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")
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


# ---------------------------------------------------------------------------
# Library contract: mark_status(return_item=True) -> (previous, item, to_outbox)
# ---------------------------------------------------------------------------

def test_mark_status_return_item_reports_outbox_route(git_repo: Path) -> None:
    """Idle main + origin: the third element matches `should_route_to_outbox`."""
    item_id = _seed(git_repo)
    assert should_route_to_outbox(git_repo) is True  # precondition

    previous, resulting_item, to_outbox = mark_status(
        git_repo, item_id, new_status="dismissed", by="op", reason="r", return_item=True,
    )
    assert previous == "triage"
    assert resulting_item["status"] == "dismissed"
    assert to_outbox is True
    assert _outbox_path(git_repo).exists()


def test_mark_status_return_item_reports_tracked_route(git_repo: Path) -> None:
    """A non-default (iterate) branch: the third element is False — tracked,
    shipping in the PR — matching the residence it actually used."""
    item_id = _seed(git_repo)
    _git(git_repo, "checkout", "-b", "iterate/some-work")
    assert should_route_to_outbox(git_repo) is False  # precondition

    _previous, _item, to_outbox = mark_status(
        git_repo, item_id, new_status="dismissed", by="op", reason="r", return_item=True,
    )
    assert to_outbox is False
    assert '"event":"status"' in _tracked_path(git_repo).read_text(encoding="utf-8")


def test_mark_status_return_item_unpacks_as_three_values(tmp_path: Path) -> None:
    """Regression guard: the new element is APPENDED (index 2), not inserted —
    `previous`/`resulting_item` keep their original meaning at indices 0/1."""
    item_id = _seed(tmp_path)
    result = mark_status(tmp_path, item_id, new_status="dismissed", by="op", return_item=True)
    assert len(result) == 3
    assert result[0] == "triage"
    assert result[1]["status"] == "dismissed"
    assert result[2] is False  # no git repo here — should_route_to_outbox fails safe


# ---------------------------------------------------------------------------
# CLI contract: `route` in --json, stderr note for the human path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", ("dismiss", "snooze"))
def test_status_flip_json_reports_tracked_route_on_a_branch(git_repo: Path, command: str) -> None:
    _git(git_repo, "checkout", "-b", "iterate/some-work")
    item_id = _seed(git_repo)

    result = _run(git_repo, command, item_id, "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["route"] == "tracked"


@pytest.mark.parametrize("command", ("dismiss", "snooze"))
def test_status_flip_json_reports_outbox_route_on_idle_main(git_repo: Path, command: str) -> None:
    item_id = _seed(git_repo)  # git_repo starts on "main" (idle)

    result = _run(git_repo, command, item_id, "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["route"] == "outbox"


def test_amend_json_reports_the_route(git_repo: Path) -> None:
    idle_id = _seed(git_repo)
    idle_result = _run(git_repo, "amend", idle_id, "--title", "Corrected", "--json")
    assert idle_result.returncode == 0, idle_result.stderr
    assert json.loads(idle_result.stdout)["route"] == "outbox"

    _git(git_repo, "checkout", "-b", "iterate/some-work")
    branch_id = _seed(git_repo)
    branch_result = _run(git_repo, "amend", branch_id, "--title", "Corrected", "--json")
    assert branch_result.returncode == 0, branch_result.stderr
    assert json.loads(branch_result.stdout)["route"] == "tracked"


def test_show_json_carries_no_route_key(tmp_path: Path) -> None:
    """`show` is a read, not a write — nothing to derive a route from."""
    item_id = _seed(tmp_path)
    result = _run(tmp_path, "show", item_id, "--json")
    assert "route" not in json.loads(result.stdout)


def test_snooze_prints_the_outbox_note_on_idle_main(git_repo: Path) -> None:
    item_id = _seed(git_repo)
    result = _run(git_repo, "snooze", item_id)
    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr


def test_snooze_prints_the_tracked_branch_note_on_a_branch(git_repo: Path) -> None:
    _git(git_repo, "checkout", "-b", "iterate/some-work")
    item_id = _seed(git_repo)
    result = _run(git_repo, "snooze", item_id)
    assert result.returncode == 0, result.stderr
    assert "recorded on branch 'iterate/some-work'" in result.stderr
    assert "reaches main only with this branch's PR" in result.stderr


def test_amend_prints_the_tracked_branch_note_on_a_branch(git_repo: Path) -> None:
    _git(git_repo, "checkout", "-b", "iterate/some-work")
    item_id = _seed(git_repo)
    result = _run(git_repo, "amend", item_id, "--title", "Corrected")
    assert result.returncode == 0, result.stderr
    assert "recorded on branch 'iterate/some-work'" in result.stderr
    assert "reaches main only with this branch's PR" in result.stderr


def test_amend_prints_the_outbox_note_on_idle_main(git_repo: Path) -> None:
    item_id = _seed(git_repo)
    result = _run(git_repo, "amend", item_id, "--title", "Corrected")
    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr


def test_route_note_is_silent_when_tracked_on_the_default_branch(git_repo_no_origin: Path) -> None:
    """GLM finding: no origin remote → tracked, but idle on `main` — neither
    note applies, and a bug that fires the branch note on default-branch idle
    would only be caught here."""
    item_id = _seed(git_repo_no_origin)
    result = _run(git_repo_no_origin, "dismiss", item_id, "--reason", "r", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["route"] == "tracked"

    result = _run(git_repo_no_origin, "snooze", _seed(git_repo_no_origin))
    assert result.returncode == 0, result.stderr
    assert "note:" not in result.stderr
