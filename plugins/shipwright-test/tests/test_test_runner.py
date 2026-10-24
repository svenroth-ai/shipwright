"""Tests for test_runner module."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.test_runner import get_test_command, parse_test_output, run_tests

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "test_runner.py"


def test_get_command_supabase_nextjs_unit():
    cmd = get_test_command("supabase-nextjs", "unit")
    assert "vitest" in cmd


def test_get_command_supabase_nextjs_e2e():
    cmd = get_test_command("supabase-nextjs", "e2e")
    assert "playwright" in cmd


@pytest.mark.covers("FR-01.06")
def test_get_command_unknown_profile_is_an_error_not_npm_test():
    with pytest.raises(ValueError, match="unknown-profile"):
        get_test_command("unknown-profile", "unit")


@pytest.mark.covers("FR-01.06")
def test_get_command_generic_sentinel_uses_the_built_in_defaults():
    assert get_test_command("generic", "unit") == "npm test"


def test_parse_vitest_output():
    output = "Tests  42 passed (42)\nDuration  3.5s"
    result = parse_test_output(output)
    assert result["passed"] == 42
    assert result["total"] == 42


def test_parse_pytest_output():
    output = "===== 15 passed, 2 failed in 1.23s ====="
    result = parse_test_output(output)
    assert result["passed"] == 15
    assert result["failed"] == 2
    assert result["total"] == 17


def test_run_tests_echo():
    """Run a simple echo command as test."""
    result = run_tests("echo 'all good'")
    assert result["success"] is True
    assert result["exit_code"] == 0


@pytest.mark.covers("FR-01.06/AC01")
def test_run_tests_failing():
    """AC1 — a real command is actually run and its real outcome is reported,
    not a summary of what was expected: a failing command must be reported as
    failed even though the caller never told the runner to expect a failure."""
    result = run_tests("exit 1")
    assert result["success"] is False
    assert result["exit_code"] == 1


@pytest.mark.covers("FR-01.06/AC04")
def test_skip_if_missing_records_not_run_with_a_reason_never_a_pass(tmp_path):
    """AC4 — a level that could not reach what it needs (no
    tests/integration/ directory here) is recorded as not-run, with the
    reason, and never as passed."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--layer", "integration",
         "--cwd", str(tmp_path), "--skip-if-missing"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["skipped"] is True
    assert result["skip_reason"] == "no tests/integration/ directory"
    # Never silently promoted into "passed": zero tests were counted, and the
    # record itself carries a reason rather than a bare pass.
    assert result["passed"] == 0
    assert result["total"] == 0


# ---- profile-driven commands (no hardcoded `npm test` for non-node stacks) ----


@pytest.mark.covers("FR-01.06/AC01")
def test_python_profile_unit_command_comes_from_profile():
    assert get_test_command("python-plugin-monorepo", "unit") == "uv run pytest"


@pytest.mark.covers("FR-01.06/AC01")
def test_profile_path_flat_unit_string(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"name": "x", "testing": {"unit": "make test"}}), encoding="utf-8")
    assert get_test_command("x", "unit", p) == "make test"


@pytest.mark.covers("FR-01.06/AC01")
def test_resolve_profile_name_reads_run_config(tmp_path):
    from lib.test_runner import resolve_profile_name

    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"profile": "python-plugin-monorepo"}), encoding="utf-8"
    )
    assert resolve_profile_name(None, str(tmp_path)) == "python-plugin-monorepo"
    assert resolve_profile_name("vite-hono", str(tmp_path)) == "vite-hono"
    assert resolve_profile_name(None, str(tmp_path / "missing")) == "supabase-nextjs"


@pytest.mark.covers("FR-01.06/AC04")
def test_layer_the_profile_does_not_define_is_skipped_not_run_as_npx(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--profile", "python-plugin-monorepo",
         "--layer", "pgtap", "--cwd", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["skipped"] is True
    assert "python-plugin-monorepo" in result["skip_reason"]


# ---- in-process coverage of the profile resolution paths ----


def _run_main(monkeypatch, capsys, argv):
    from lib import test_runner

    monkeypatch.setattr(sys, "argv", ["test_runner.py", *argv])
    code = test_runner.main()
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.covers("FR-01.06/AC04")
def test_main_skips_layer_profile_does_not_declare(monkeypatch, capsys, tmp_path):
    code, out = _run_main(monkeypatch, capsys,
                          ["--profile", "python-plugin-monorepo", "--layer", "pgtap",
                           "--cwd", str(tmp_path)])
    assert code == 0 and out["skipped"] is True


@pytest.mark.covers("FR-01.06/AC01")
def test_main_runs_profile_command_from_run_config(monkeypatch, capsys, tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"profile": "python-plugin-monorepo"}), encoding="utf-8")
    from lib import test_runner

    seen = []
    monkeypatch.setattr(test_runner, "run_tests",
                        lambda cmd, cwd=None: seen.append(cmd) or {"success": True})
    code, out = _run_main(monkeypatch, capsys, ["--layer", "unit", "--cwd", str(tmp_path)])
    assert code == 0 and seen == ["uv run pytest"]


@pytest.mark.covers("FR-01.06/AC01")
def test_profile_helpers_tolerate_bad_input(tmp_path):
    from types import SimpleNamespace as NS

    from lib.test_runner import _profile_layer_command, profile_declares_no_layer

    def res(source, name, data):
        return NS(source=source, name=name, data=data)

    assert _profile_layer_command({}, "unit") == ""
    assert _profile_layer_command({"testing": {"integration": {"command": "x"}}}, "integration") == "x"
    assert profile_declares_no_layer(None, "e2e") is False
    assert profile_declares_no_layer(res("builtin", "generic", {}), "e2e") is False
    assert profile_declares_no_layer(res("bundled", "supabase-nextjs", {"testing": {}}), "e2e") is False
    assert profile_declares_no_layer(res("bundled", "other", {"testing": {}}), "unit") is False
    assert profile_declares_no_layer(res("bundled", "other", {"testing": {"e2e": {}}}), "e2e") is False
    # D9: provenance, not the name, selects the legacy table - a PROJECT profile named
    # supabase-nextjs that declares no e2e layer is skipped, not run via `npx playwright`.
    assert profile_declares_no_layer(res("project", "supabase-nextjs", {"testing": {}}), "e2e") is True


@pytest.mark.covers("FR-01.06/AC01")
def test_profile_name_is_validated_before_touching_the_filesystem(tmp_path):
    from lib.test_runner import load_resolved, resolve_profile_name

    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"profile": "../../etc/x"}), encoding="utf-8")
    name = resolve_profile_name(None, str(tmp_path))
    assert name == "../../etc/x"  # NOT silently supabase-nextjs (S2: no silent fallback)
    with pytest.raises(ValueError, match="Invalid profile name"):
        load_resolved(name, None, str(tmp_path), quiet=True)
