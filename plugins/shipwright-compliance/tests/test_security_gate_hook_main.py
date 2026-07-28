"""In-process tests for ``check_security_scan.main()`` — the hook shell.

Split from ``test_security_gate_unit.py`` at the 300-line cap.

The subprocess suites prove the shipped script runs end to end; these reach the
branches coverage.py cannot see through a fork, and pin the one that matters
most: an unloadable gate must BLOCK. Being unable to evaluate a security gate is
not the same as passing it, so that path must not fall through to the hook's
fail-open wrapper.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

SUMMARY_REL = Path(".shipwright") / "compliance" / "ci-security.json"
RELEASE_CMD = {"tool_input": {"command": "deploy to jelastic"}}


def _load_hook():
    """Load the hook as a module under its own name (never `import`ed normally —
    it is a standalone script invoked by Claude Code)."""
    path = (Path(__file__).parent.parent / "scripts" / "hooks"
            / "check_security_scan.py")
    spec = importlib.util.spec_from_file_location("_check_security_scan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_summary(root: Path, *, critical: int = 0) -> None:
    target = root / SUMMARY_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "schema": 1, "scan_date": "2026-07-28T07:51:37Z", "source": "security.yml#1",
        "by_severity": {"critical": critical, "high": 0, "medium": 0, "low": 0},
        "total": critical, "open_high_critical": critical,
        "critical_gate": "fail" if critical else "pass",
        "prompt_injection": 0, "degraded": False,
    }), encoding="utf-8")


def _stdin(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))


def _at(monkeypatch, root: Path) -> None:
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(root))
    monkeypatch.chdir(root)


def test_unparseable_payload_allows(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert _load_hook().main() == 0


def test_non_release_command_allows(monkeypatch, tmp_path: Path):
    _write_summary(tmp_path, critical=9)      # dirty scan, but not a release cmd
    _stdin(monkeypatch, {"tool_input": {"command": "npm test"}})
    _at(monkeypatch, tmp_path)
    assert _load_hook().main() == 0


def test_clean_scan_allows(monkeypatch, tmp_path: Path):
    _write_summary(tmp_path, critical=0)
    _stdin(monkeypatch, RELEASE_CMD)
    _at(monkeypatch, tmp_path)
    assert _load_hook().main() == 0


def test_open_criticals_block_and_emit_hook_json(monkeypatch, tmp_path: Path, capsys):
    _write_summary(tmp_path, critical=2)
    _stdin(monkeypatch, RELEASE_CMD)
    _at(monkeypatch, tmp_path)
    assert _load_hook().main() == 2
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["blocked"] is True
    assert "2 open critical" in out["reason"]
    assert "Continue anyway" in out["additionalContext"]


def test_an_unloadable_gate_blocks_rather_than_assuming_clean(
    monkeypatch, tmp_path: Path, capsys,
):
    mod = _load_hook()
    _stdin(monkeypatch, RELEASE_CMD)
    _at(monkeypatch, tmp_path)
    monkeypatch.delitem(sys.modules, "security_gate", raising=False)
    real_import = __import__

    def boom(name, *a, **kw):
        if name == "security_gate":
            raise ImportError("simulated")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", boom)
    assert mod.main() == 2
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["details"]["state"] == "gate-unavailable"
    assert "refusing to assume a clean scan" in out["reason"]
