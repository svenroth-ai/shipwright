"""A logged "Continue anyway" lets a compliance soft-block through once, within 30 minutes (U13 item 2)."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import compliance_override as co  # noqa: E402

_SHARED_SCRIPTS = str(Path(__file__).resolve().parents[3] / "shared" / "scripts")
if _SHARED_SCRIPTS not in sys.path:
    sys.path.append(_SHARED_SCRIPTS)  # appended: never shadows this plugin's own modules
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import collector_manifest, hook_env, write_manifest  # noqa: E402
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")

HOOKS = Path(__file__).parent.parent / "scripts" / "hooks"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(root: Path, *lines: str) -> None:
    path = root / co.LOG_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(f"{line}\n" for line in lines)


def test_an_entry_is_honoured_inside_its_window_only(tmp_path):
    _log(tmp_path, f"{_stamp(NOW - timedelta(minutes=29))} | check_rtm_coverage | OVERRIDE | ok")
    assert co.active_override(tmp_path, "check_rtm_coverage", NOW).reason == "ok"
    assert co.active_override(tmp_path, "check_rtm_coverage", NOW + timedelta(minutes=2)) is None
    assert co.active_override(tmp_path, "check_security_scan", NOW) is None  # other hook


@pytest.mark.parametrize("line", [
    f"{_stamp(NOW - timedelta(minutes=31))} | check_rtm_coverage | OVERRIDE | expired",
    f"{_stamp(NOW + timedelta(minutes=10))} | check_rtm_coverage | OVERRIDE | pre-dated",
    f"{_stamp(NOW)} | check_rtm_coverage | OVERRIDE |   ",  # no reason
    "yesterday | check_rtm_coverage | OVERRIDE | unreadable time",
    f"{_stamp(NOW)} | check_rtm_coverage | NOTE | not an override",
])
def test_expired_predated_reasonless_or_malformed_entries_are_ignored(tmp_path, line):
    _log(tmp_path, line)
    assert co.active_override(tmp_path, "check_rtm_coverage", NOW) is None


def test_override_logger_shape_is_read_and_the_newest_entry_wins(tmp_path):
    _log(tmp_path,
         f"{_stamp(NOW - timedelta(minutes=20))} | check_security_scan | OVERRIDE | older",
         f'[{(NOW - timedelta(minutes=5)).isoformat()}] OVERRIDE hook=check_security_scan '
         'reason="newer" details={}')
    found = co.active_override(tmp_path, "check_security_scan", NOW)
    assert found.reason == "newer"
    assert "of 2026-10-08T11:55:00Z" in co.notice("check_security_scan", found, "x")


def test_an_override_is_used_once(tmp_path):
    _log(tmp_path, f"{_stamp(NOW - timedelta(minutes=5))} | check_rtm_coverage | OVERRIDE | ok")
    found = co.active_override(tmp_path, "check_rtm_coverage", NOW)
    assert co.consume(tmp_path, "check_rtm_coverage", found, NOW) is None
    assert co.active_override(tmp_path, "check_rtm_coverage", NOW) is None
    assert "| check_rtm_coverage | CONSUMED |" in (tmp_path / co.LOG_RELPATH).read_text("utf-8")


def test_an_unwritable_log_says_the_override_stays_valid(tmp_path):
    (tmp_path / co.LOG_RELPATH).mkdir(parents=True)  # a directory where the log should be
    unmarked = co.consume(tmp_path, "check_rtm_coverage", co.Override(NOW, "ok"), NOW)
    assert "could not be marked used" in unmarked and "NOT applied" in unmarked


def test_rtm_hook_keeps_the_block_when_the_use_cannot_be_recorded(tmp_path, monkeypatch, capsys):
    write_manifest(tmp_path, collector_manifest(3, 10, executed_rest="fail"))
    _log(tmp_path, f"{_stamp(datetime.now(timezone.utc))} | check_rtm_coverage | OVERRIDE | go")
    spec = importlib.util.spec_from_file_location("_rtm_override", HOOKS / "check_rtm_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_resolve_project_root", lambda: str(tmp_path))
    assert mod._lib().override is co  # the hook's compliance_override is this test's module
    monkeypatch.setattr(co, "consume", lambda *_a, **_k: "the log is read-only")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {
        "command": "git commit -m x"}})))
    assert mod.main() == 2 and "the log is read-only" in capsys.readouterr().err


def test_control_characters_in_a_reason_are_not_echoed():
    text = co.notice("check_rtm_coverage", co.Override(NOW, "ok[31mred"), "x")
    assert "" not in text and "" not in text and "ok [31mred" in text


def test_a_bom_and_crlf_from_an_editor_keep_the_first_entry(tmp_path):
    path = tmp_path / co.LOG_RELPATH
    path.parent.mkdir(parents=True)
    path.write_bytes(f"﻿{_stamp(NOW)} | check_rtm_coverage | OVERRIDE | ok\r\n".encode())
    assert co.active_override(tmp_path, "check_rtm_coverage", NOW).reason == "ok"


def test_no_log_is_no_override(tmp_path):
    assert co.active_override(tmp_path, "check_rtm_coverage") is None


def test_the_instructed_line_written_by_bash_is_honoured(tmp_path):
    """Round trip: the exact command the block prints -> the log -> the reader."""
    skip_or_fail_on_missing_binary("bash", "Git for Windows ships bash; CI ubuntu has it.")
    command = co.instruction(tmp_path, "check_rtm_coverage").splitlines()[-1]
    command = command.replace("<the reason the user gave>", "user said continue")
    (tmp_path / co.LOG_RELPATH).parent.mkdir(parents=True)
    subprocess.run(["bash", "-c", command], check=True, timeout=30)
    assert co.active_override(tmp_path, "check_rtm_coverage").reason == "user said continue"


def _rtm_hook(root: Path):
    return subprocess.run(
        [sys.executable, str(HOOKS / "check_rtm_coverage.py")], capture_output=True, text=True,
        input=json.dumps({"tool_input": {"command": "git commit -m x"}}),
        cwd=str(root), env=hook_env(root), timeout=60)


def test_rtm_hook_names_the_line_then_honours_it(tmp_path):
    write_manifest(tmp_path, collector_manifest(3, 10, executed_rest="fail"))
    blocked = _rtm_hook(tmp_path)
    assert blocked.returncode == 2
    assert "| check_rtm_coverage | OVERRIDE |" in blocked.stderr
    assert (tmp_path / co.LOG_RELPATH).as_posix() in blocked.stderr
    _log(tmp_path, f"{_stamp(datetime.now(timezone.utc))} | check_rtm_coverage | OVERRIDE | go")
    allowed = _rtm_hook(tmp_path)
    assert allowed.returncode == 0
    ctx = json.loads(allowed.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "OVERRIDDEN once" in ctx and '"go"' in ctx and "Requirement coverage 30%" in ctx
    assert _rtm_hook(tmp_path).returncode == 2  # used: the next commit needs a new override


def _security_hook():
    spec = importlib.util.spec_from_file_location(
        "_check_security_scan_override", HOOKS / "check_security_scan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_security_hook_names_the_line_then_honours_it(tmp_path, monkeypatch, capsys):
    summary = tmp_path / ".shipwright" / "compliance" / "ci-security.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({
        "schema": 1, "scan_date": "2026-07-28T07:51:37Z", "source": "security.yml#1",
        "by_severity": {"critical": 2, "high": 0, "medium": 0, "low": 0}, "total": 2,
        "open_high_critical": 2, "critical_gate": "fail", "prompt_injection": 0,
        "degraded": False}), encoding="utf-8")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    mod = _security_hook()
    payload = json.dumps({"tool_input": {"command": "deploy to jelastic"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert mod.main() == 2
    err = capsys.readouterr().err
    assert "BLOCKED (check_security_scan)" in err and "| check_security_scan | OVERRIDE |" in err
    _log(tmp_path, f"{_stamp(datetime.now(timezone.utc))} | check_security_scan | OVERRIDE | go")
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert mod.main() == 0
    assert "OVERRIDDEN once" in capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert mod.main() == 2  # used once
