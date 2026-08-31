"""``run_compliance_update`` must launch via the compliance plugin's own venv.

``update_compliance.py`` needs jsonschema/pyyaml, declared ONLY in the
compliance plugin's own pyproject.toml. Launching it with `sys.executable`
runs it under the orchestrator's OWN venv, which carries neither —
ModuleNotFoundError (same class of bug as finalize_iterate.py's
`_update_compliance`, reproduced live on macOS). Split into its own file
rather than appended to test_orchestrator.py, which already sits at its
bloat-baseline cap.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import run_compliance_update


def test_run_compliance_update_uses_the_compliance_plugins_own_environment(
    tmp_project, mocker,
):
    from orchestrator_pkg import compliance_runner

    real_script = (
        Path(__file__).resolve().parents[2] / "shipwright-compliance"
        / "scripts" / "tools" / "update_compliance.py"
    )
    assert real_script.exists(), f"fixture assumption broken: {real_script}"
    mocker.patch("orchestrator._COMPLIANCE_SCRIPT", real_script)

    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    mocker.patch.object(compliance_runner.subprocess, "run", fake_run)
    run_compliance_update(tmp_project, "project")

    cmd = captured.get("cmd") or []
    assert cmd[:2] == ["uv", "run"], (
        f"must launch via `uv run`, not the caller's bare interpreter: {cmd}")
    assert "--project" in cmd, f"must pin the compliance plugin's own venv: {cmd}"
    plugin_dir = Path(cmd[cmd.index("--project") + 1])
    assert plugin_dir.name == "shipwright-compliance"
    assert sys.executable not in cmd


def test_run_compliance_update_surfaces_generator_errors_from_stdout(
    tmp_project, mocker, capsys,
):
    """On a generator-error exit, ``update_compliance.py`` writes
    ``{"success": false, "generator_errors": [...]}`` to STDOUT and leaves
    stderr EMPTY. The old code logged only ``result.stderr``, so the warn
    line came back with no clue what broke."""
    from orchestrator_pkg import compliance_runner

    real_script = (
        Path(__file__).resolve().parents[2] / "shipwright-compliance"
        / "scripts" / "tools" / "update_compliance.py"
    )
    mocker.patch("orchestrator._COMPLIANCE_SCRIPT", real_script)
    mock_record = mocker.patch("orchestrator._record_compliance_update_failed")

    payload = {
        "success": False,
        "generator_errors": [
            {"report": "dashboard", "error": "KeyError", "detail": "missing 'grade'"},
        ],
    }

    class _Result:
        returncode = 1
        stdout = json.dumps(payload)
        stderr = ""

    mocker.patch.object(compliance_runner.subprocess, "run", lambda *a, **k: _Result())

    result = run_compliance_update(tmp_project, "project")

    assert result is None
    captured = capsys.readouterr()
    logged = json.loads(captured.err.strip())
    assert "KeyError" in logged["detail"]
    assert "missing 'grade'" in logged["detail"]
    mock_record.assert_called_once_with(
        tmp_project, "project", reason="subprocess_exit_1",
    )


def test_run_compliance_update_falls_back_to_stderr_when_stdout_is_not_json(
    tmp_project, mocker, capsys,
):
    """A failure that never produces JSON on stdout (uv error, bare traceback)
    must keep falling back to the real stderr — the generator-error path must
    not swallow this other failure class."""
    from orchestrator_pkg import compliance_runner

    real_script = (
        Path(__file__).resolve().parents[2] / "shipwright-compliance"
        / "scripts" / "tools" / "update_compliance.py"
    )
    mocker.patch("orchestrator._COMPLIANCE_SCRIPT", real_script)
    mocker.patch("orchestrator._record_compliance_update_failed")

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "uv: command not found"

    mocker.patch.object(compliance_runner.subprocess, "run", lambda *a, **k: _Result())

    result = run_compliance_update(tmp_project, "project")

    assert result is None
    captured = capsys.readouterr()
    logged = json.loads(captured.err.strip())
    assert "uv: command not found" in logged["detail"]


@pytest.mark.parametrize("malformed_generator_errors", ["failure", [None], [42]])
def test_run_compliance_update_malformed_generator_errors_falls_back_to_stderr(
    tmp_project, mocker, capsys, malformed_generator_errors,
):
    """A malformed-but-JSON-valid `generator_errors` (not a list of dicts) must
    not raise `AttributeError` from `e.get(...)` — it must fall back to the
    real stderr (external code-review finding, openai/medium)."""
    from orchestrator_pkg import compliance_runner

    real_script = (
        Path(__file__).resolve().parents[2] / "shipwright-compliance"
        / "scripts" / "tools" / "update_compliance.py"
    )
    mocker.patch("orchestrator._COMPLIANCE_SCRIPT", real_script)
    mocker.patch("orchestrator._record_compliance_update_failed")

    payload = {"success": False, "generator_errors": malformed_generator_errors}

    class _Result:
        returncode = 1
        stdout = json.dumps(payload)
        stderr = "real stderr text"

    mocker.patch.object(compliance_runner.subprocess, "run", lambda *a, **k: _Result())

    result = run_compliance_update(tmp_project, "project")

    assert result is None
    captured = capsys.readouterr()
    logged = json.loads(captured.err.strip())
    assert "real stderr text" in logged["detail"]
