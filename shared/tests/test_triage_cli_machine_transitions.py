"""Machine-callable triage transition contract.

The Command Center follow-up consumes these commands as its sole write path, so
these tests exercise the executable rather than only its library helpers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage as triage_module  # noqa: E402
from triage import (  # noqa: E402
    StatusPreconditionError,
    amend_triage_item,
    append_triage_item,
    mark_status,
    read_all_items,
)
from tools.triage_promote import dismiss, promote  # noqa: E402

CLI = _SCRIPTS / "tools" / "triage_cli.py"


def _seed(project: Path) -> str:
    return append_triage_item(
        project, source="test", severity="medium", kind="bug",
        title="Machine transition", detail="fixture", dedup_key=None,
    )


def _run(
    project: Path, *args: str, env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), "--project-root", str(project), *args],
        capture_output=True, text=True, check=False, env=env,
    )


@pytest.mark.parametrize(
    ("command", "status"),
    [
        (("promote", "--task-ref", "EXT:42"), "promoted"),
        (("dismiss", "--reason", "not applicable"), "dismissed"),
        (("defer", "--reason", "later", "--revisit", "2030-01-01"), "snoozed"),
    ],
)
def test_transition_json_returns_resulting_resolved_item(
    tmp_path: Path, command: tuple[str, ...], status: str,
) -> None:
    item_id = _seed(tmp_path)
    result = _run(tmp_path, command[0], item_id, *command[1:], "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["operation"] == command[0]
    assert payload["item"]["id"] == item_id
    assert payload["item"]["status"] == status
    assert payload["item"] == read_all_items(tmp_path)[0]


def test_unpark_and_amend_json_return_resulting_resolved_item(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    assert _run(tmp_path, "defer", item_id, "--reason", "later", "--revisit", "2030-01-01").returncode == 0

    unpark = _run(tmp_path, "unpark", item_id, "--reason", "now", "--json")
    assert unpark.returncode == 0, unpark.stderr
    assert json.loads(unpark.stdout)["item"]["status"] == "triage"

    amend = _run(tmp_path, "amend", item_id, "--title", "Corrected", "--json")
    assert amend.returncode == 0, amend.stderr
    assert json.loads(amend.stdout)["item"] == read_all_items(tmp_path)[0]


def test_webui_snooze_accepts_its_optional_reason_and_revisit(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    result = _run(tmp_path, "snooze", item_id, "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["item"]["status"] == "snoozed"


def test_webui_dismiss_accepts_an_optional_reason_in_json_mode(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    result = _run(tmp_path, "dismiss", item_id, "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["item"]["status"] == "dismissed"
    assert _run(tmp_path, "dismiss", _seed(tmp_path)).returncode == 2


@pytest.mark.parametrize("command", ("dismiss", "snooze"))
@pytest.mark.parametrize("reason", ("bad\nreason", "\n", "\t", "x" * 501))
def test_optional_json_reason_keeps_the_existing_input_guards(
    tmp_path: Path, command: str, reason: str,
) -> None:
    item_id = _seed(tmp_path)
    result = _run(tmp_path, command, item_id, "--reason", reason, "--json")

    assert result.returncode == 2
    assert read_all_items(tmp_path)[0]["status"] == "triage"


@pytest.mark.parametrize("revisit", ("2000-01-01", datetime.now(timezone.utc).date().isoformat()))
def test_webui_snooze_rejects_a_due_revisit_without_writing(tmp_path: Path, revisit: str) -> None:
    item_id = _seed(tmp_path)
    result = _run(tmp_path, "snooze", item_id, "--revisit", revisit, "--json")

    assert result.returncode == 2
    events = [
        json.loads(line) for line in (tmp_path / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not [event for event in events if event.get("event") == "status" and event.get("id") == item_id]


def test_future_snooze_check_uses_the_clock_inside_the_store_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = _seed(tmp_path)
    defer = triage_module._load_triage_defer()
    monkeypatch.setattr(defer, "now_utc", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="future UTC"):
        mark_status(
            tmp_path, item_id, new_status="snoozed", by="test",
            revisit_at="2030-01-01", expected_status="triage",
            require_future_revisit=True,
        )
    with pytest.raises(ValueError, match="accepted only"):
        mark_status(tmp_path, item_id, new_status="dismissed", by="test", require_future_revisit=True)
    assert read_all_items(tmp_path)[0]["status"] == "triage"


def test_amend_refuses_a_card_decided_by_another_transition(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    assert _run(tmp_path, "dismiss", item_id, "--reason", "done").returncode == 0

    result = _run(tmp_path, "amend", item_id, "--title", "Too late", "--json")
    assert result.returncode == 3


def test_library_transition_results_and_amend_cas_are_resolved(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    promoted = promote(tmp_path, item_id=item_id, task_ref="EXT:42", include_item=True)
    assert promoted["item"] == next(item for item in read_all_items(tmp_path) if item["id"] == item_id)
    other_id = _seed(tmp_path)
    dismissed = dismiss(tmp_path, item_id=other_id, reason="done", include_item=True)
    assert dismissed["item"] == next(item for item in read_all_items(tmp_path) if item["id"] == other_id)
    _to_outbox, amended = amend_triage_item(tmp_path, other_id, title="resolved", return_item=True)
    assert amended == next(item for item in read_all_items(tmp_path) if item["id"] == other_id)
    with pytest.raises(StatusPreconditionError):
        amend_triage_item(tmp_path, item_id, title="too late", expected_status="triage")


def test_show_reads_one_resolved_item_and_human_default_is_preserved(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    assert _run(tmp_path, "amend", item_id, "--title", "Resolved", "--detail", "Overlay").returncode == 0
    machine = _run(tmp_path, "show", item_id, "--json")
    human = _run(tmp_path, "show", item_id)

    assert machine.returncode == human.returncode == 0
    assert json.loads(machine.stdout) == {
        "operation": "show", "item": json.loads(machine.stdout)["item"],
    }
    assert json.loads(machine.stdout)["item"] == read_all_items(tmp_path)[0]
    assert item_id in human.stdout


def test_stable_exit_codes_cover_validation_precondition_missing_and_store(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    assert _run(tmp_path, "dismiss", item_id, "--reason", " ").returncode == 2
    assert _run(tmp_path, "dismiss", item_id, "--reason", "done").returncode == 0
    assert _run(tmp_path, "dismiss", item_id, "--reason", "again").returncode == 3
    assert _run(tmp_path, "show", "trg-missing", "--json").returncode == 4
    assert _run(tmp_path / "no-store", "show", "trg-missing", "--json").returncode == 5


def test_lock_timeout_has_its_own_exit_code_at_the_cli_boundary(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    hook_dir = tmp_path / "hook"
    hook_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(
        "import triage\n"
        "from shared_lib_loader import load_shared_lib\n"
        "class TimeoutLock:\n"
        "    def __init__(self, *_args, **_kwargs): pass\n"
        "    def __enter__(self):\n"
        "        raise load_shared_lib('file_lock').LockTimeout('held by another writer')\n"
        "    def __exit__(self, *_args): return False\n"
        "triage._load_file_lock_cls = lambda: TimeoutLock\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(_SCRIPTS), str(hook_dir)))}
    result = _run(tmp_path, "dismiss", item_id, "--reason", "locked", "--json", env=env)

    assert result.returncode == 6


def test_two_cli_writers_racing_one_transition_leave_one_refusal(tmp_path: Path) -> None:
    item_id = _seed(tmp_path)
    hook_dir = tmp_path / "barrier-hook"
    barrier_dir = tmp_path / "barrier"
    hook_dir.mkdir()
    barrier_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(
        "import os\n"
        "import time\n"
        "from pathlib import Path\n"
        "import triage\n"
        "real_lock = triage._load_file_lock_cls()\n"
        "barrier = Path(os.environ['TRIAGE_RACE_BARRIER'])\n"
        "class BarrierLock:\n"
        "    def __init__(self, path): self.inner = real_lock(path)\n"
        "    def __enter__(self):\n"
        "        (barrier / f'{os.getpid()}.ready').write_text('', encoding='utf-8')\n"
        "        deadline = time.monotonic() + 10\n"
        "        while len(list(barrier.glob('*.ready'))) < 2:\n"
        "            if time.monotonic() >= deadline: raise RuntimeError('race barrier timed out')\n"
        "            time.sleep(0.01)\n"
        "        return self.inner.__enter__()\n"
        "    def __exit__(self, *args): return self.inner.__exit__(*args)\n"
        "triage._load_file_lock_cls = lambda: BarrierLock\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(_SCRIPTS), str(hook_dir))),
        "TRIAGE_RACE_BARRIER": str(barrier_dir),
    }
    command = [
        sys.executable, str(CLI), "--project-root", str(tmp_path), "dismiss", item_id,
        "--reason", "concurrent", "--json",
    ]
    first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    second = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    first_out, first_err = first.communicate(timeout=20)
    second_out, second_err = second.communicate(timeout=20)

    assert sorted((first.returncode, second.returncode)) == [0, 3], (first_out, first_err, second_out, second_err)
    assert read_all_items(tmp_path)[0]["status"] == "dismissed"
    status_events = [
        json.loads(line) for line in (tmp_path / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("event") == "status"
    ]
    assert len(status_events) == 1
    successful_output = first_out if first.returncode == 0 else second_out
    assert json.loads(successful_output)["item"]["status"] == status_events[0]["newStatus"] == "dismissed"
