"""``run_compliance_update`` must launch via the compliance plugin's own venv.

``update_compliance.py`` needs jsonschema/pyyaml, declared ONLY in the
compliance plugin's own pyproject.toml. Launching it with `sys.executable`
runs it under the orchestrator's OWN venv, which carries neither —
ModuleNotFoundError (same class of bug as finalize_iterate.py's
`_update_compliance`, reproduced live on macOS). Split into its own file
rather than appended to test_orchestrator.py, which already sits at its
bloat-baseline cap.
"""

import sys
from pathlib import Path

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
