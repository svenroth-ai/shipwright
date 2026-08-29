"""``_run_update_compliance`` must launch via the compliance plugin's own venv.

``update_compliance.py`` needs jsonschema/pyyaml, declared ONLY in the
compliance plugin's own pyproject.toml. Launching it with `sys.executable`
runs it under the SECURITY plugin's own venv, which carries neither —
ModuleNotFoundError (same class of bug as finalize_iterate.py's
`_update_compliance`, reproduced live on macOS). Split into its own file
rather than appended to test_finalize_security_compliance.py, which already
sits at its bloat-baseline cap.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))


def _load_finalize_module():
    """Load via importlib + sentinel name — see test_finalize_security_compliance.py."""
    target = PLUGIN_ROOT / "scripts" / "tools" / "finalize_security_compliance.py"
    sentinel = "_test_security_finalize_uv_env_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, target)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(sentinel, None)
        raise
    return mod


@pytest.fixture
def _Result():
    class Result:
        returncode = 0
        stdout = "{}"
        stderr = ""
    return Result


def test_run_update_compliance_uses_the_compliance_plugins_own_environment(
    tmp_path, monkeypatch, _Result,
):
    fsc = _load_finalize_module()
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(fsc.subprocess, "run", fake_run)
    fsc._run_update_compliance(tmp_path)

    cmd = captured.get("cmd") or []
    assert cmd[:2] == ["uv", "run"], (
        f"must launch via `uv run`, not the caller's bare interpreter: {cmd}")
    assert "--project" in cmd, f"must pin the compliance plugin's own venv: {cmd}"
    plugin_dir = Path(cmd[cmd.index("--project") + 1])
    assert plugin_dir.name == "shipwright-compliance"
    assert sys.executable not in cmd


@pytest.mark.parametrize("exc", [
    subprocess.TimeoutExpired(cmd=["uv"], timeout=60),
    FileNotFoundError("uv not found"),
])
def test_run_update_compliance_does_not_raise_when_uv_itself_fails(
    tmp_path, monkeypatch, exc,
):
    """Unlike the old `sys.executable` call (always present, starts instantly),
    `uv` is an external binary that can be absent or time out on a cold venv
    sync — this must degrade to the same error-dict contract as every other
    failure branch here, not raise (doubt-reviewer HIGH finding)."""
    fsc = _load_finalize_module()

    def raising_run(cmd, **kwargs):
        raise exc

    monkeypatch.setattr(fsc.subprocess, "run", raising_run)
    result = fsc._run_update_compliance(tmp_path)

    assert result["updated_reports"] == []
    assert "error" in result and result["error"]
