"""The delivery-refresh F11 push must re-run the marked local CI-gate mirror."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import pr_delivery_host as host  # noqa: E402


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _run(*results):
    calls: list[list[str]] = []
    call_kwargs: list[dict] = []
    queue = list(results)

    def run(argv, **kwargs):
        calls.append(list(argv))
        call_kwargs.append(kwargs)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    run.calls = calls  # type: ignore[attr-defined]
    run.call_kwargs = call_kwargs  # type: ignore[attr-defined]
    return run


def _marked_script(root: Path) -> None:
    script = root / host.VERIFY_LOCAL_RELATIVE_PATH
    script.parent.mkdir(parents=True)
    script.write_text(host.VERIFY_LOCAL_MARKER, encoding="utf-8")


def test_delivery_refresh_checks_the_integrated_tree_before_push(tmp_path):
    _marked_script(tmp_path)
    run = _run(
        _Proc(0, "before\\n"),
        _Proc(0, '{"integrated": true}'),
        _Proc(0),
        _Proc(0),
    )

    result = host.refresh_branch(tmp_path, "iterate-x", "iterate/x", run=run)

    assert result["ok"] is True and result["pushed"] is True
    commands = [" ".join(call) for call in run.calls]
    ensure = next(i for i, command in enumerate(commands) if "ensure_current.py" in command)
    local = next(i for i, command in enumerate(commands) if "verify_local.py" in command)
    push = next(i for i, command in enumerate(commands) if " push origin iterate/x" in command)
    assert ensure < local < push
    assert run.calls[local] == ["uv", "run", "scripts/verify_local.py"]
    assert run.call_kwargs[local]["cwd"] == tmp_path


def test_delivery_refresh_stops_when_the_local_gate_is_red(tmp_path):
    _marked_script(tmp_path)
    run = _run(
        _Proc(0, "before\\n"),
        _Proc(0, '{"integrated": true}'),
        _Proc(1, "failed mirror", "gate red"),
    )

    result = host.refresh_branch(tmp_path, "iterate-x", "iterate/x", run=run)

    assert result["ok"] is False and result["pushed"] is False
    assert "local CI-gate mirror failed" in result["error"]
    assert not any(" push origin " in " ".join(call) for call in run.calls)


def test_unmarked_or_undecodable_unmarked_consumer_script_is_a_no_op(tmp_path):
    script = tmp_path / host.VERIFY_LOCAL_RELATIVE_PATH
    script.parent.mkdir(parents=True)
    run = _run(_Proc(0))

    script.write_text("some other local check", encoding="utf-8")
    assert host.recheck_local_gates(tmp_path, run=run) is True
    assert run.calls == []

    script.write_bytes(b"\xff\xfe")
    assert host.recheck_local_gates(tmp_path, run=run) is True
    assert run.calls == []


def test_undecodable_but_marked_script_still_runs_the_gate(tmp_path):
    script = tmp_path / host.VERIFY_LOCAL_RELATIVE_PATH
    script.parent.mkdir(parents=True)
    script.write_bytes(host.VERIFY_LOCAL_MARKER.encode("ascii") + b"\xff")
    run = _run(_Proc(0))

    assert host.recheck_local_gates(tmp_path, run=run) is True
    assert run.calls == [["uv", "run", "scripts/verify_local.py"]]
