"""In-process (non-subprocess) coverage for write_grill_trace.py's bootstrap
sys.path insertion and ``main()``.

``test_write_grill_trace.py`` covers ``write_trace()`` directly (fine) and
``main()`` behaviorally via ``subprocess.run([sys.executable, str(SCRIPT),
...])`` — a genuinely separate Python process that this test session's
coverage instrumentation never observes (no ``COVERAGE_PROCESS_START``/
``sitecustomize`` subprocess hook is configured here). That makes ``main()``
invisible to the diff-coverage gate even though it is behaviorally tested
elsewhere. This file re-exercises the same contracts by importing the module
directly and calling ``main()`` in-process, so the coverage tool actually
sees the lines execute. Precedent: ``test_write_context_term_direct.py``
(P4.1's identical fix for the identical gap).

``_write_grill_trace_cli.py``'s own helper functions
(``build_arg_parser``/``load_payload_file``) get the same treatment in the
sibling ``test_write_grill_trace_cli_direct.py``.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import tools.write_grill_trace as wgt_module
from lib.file_lock import LockTimeout


def _payload(**overrides) -> dict:
    payload = {
        "requirement_key": "login-rate-limit",
        "requirement_text": "The system SHOULD rate-limit login attempts to 5 per minute per IP.",
        "surface": "project",
        "evidence": ["turn 4: user described repeated failed sign-ins as a concern"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "answered",
            "failure": "answered",
            "glossary": "n/a:no new term introduced",
            "rationale": "n/a:not hard to reverse",
            "out_of_scope": "answered",
        },
        "fit_criterion": "a sixth failed sign-in within a minute from one IP is refused",
        "glossary_delta": [],
        "confirmed_by": "user confirmed the shared understanding in turn 7",
        "terms_used": [],
    }
    payload.update(overrides)
    return payload


def _write_payload_file(tmp_path: Path, **overrides) -> Path:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload(**overrides)), encoding="utf-8")
    return payload_path


# ---------------------------------------------------------------------------
# write_grill_trace.py — bootstrap sys.path insertion (module-level lines)
# ---------------------------------------------------------------------------

def test_bootstrap_inserts_scripts_root_when_missing_from_syspath(monkeypatch):
    """The ``if str(_SCRIPTS_ROOT) not in sys.path: sys.path.insert(...)``
    bootstrap only executes when the scripts root isn't already present.
    conftest.py always adds it before any test runs, so a normal import never
    exercises the ``True`` branch — force it by removing the entry and
    re-importing fresh."""
    scripts_root = str(Path(__file__).resolve().parents[1] / "scripts")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != scripts_root])
    original_module = sys.modules.pop("tools.write_grill_trace", None)
    try:
        importlib.import_module("tools.write_grill_trace")
        assert scripts_root in sys.path
    finally:
        if original_module is not None:
            sys.modules["tools.write_grill_trace"] = original_module
        else:
            sys.modules.pop("tools.write_grill_trace", None)


# ---------------------------------------------------------------------------
# write_grill_trace.py — main(), called in-process
# ---------------------------------------------------------------------------

def _set_argv(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["write_grill_trace.py", *args])


def test_main_success_path_prints_json_and_returns_0(tmp_path, monkeypatch, capsys):
    payload_path = _write_payload_file(tmp_path)
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--payload-file", str(payload_path),
    )
    rc = wgt_module.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "created"
    assert out["requirement_key"] == "login-rate-limit"
    written = tmp_path / ".shipwright" / "planning" / "grill-traces" / "login-rate-limit.json"
    assert written.exists()


def test_main_planning_dir_override_is_honored(tmp_path, monkeypatch, capsys):
    payload_path = _write_payload_file(tmp_path)
    override_dir = tmp_path / "alt-planning"
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--planning-dir", str(override_dir),
        "--payload-file", str(payload_path),
    )
    rc = wgt_module.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "created"
    written = override_dir / "grill-traces" / "login-rate-limit.json"
    assert written.exists()
    default_dir = tmp_path / ".shipwright" / "planning" / "grill-traces"
    assert not default_dir.exists()


def test_main_payload_error_returns_1(tmp_path, monkeypatch, capsys):
    """A --payload-file that doesn't exist surfaces as PayloadError from
    load_payload_file(), caught before any --project-root validation."""
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--payload-file", str(tmp_path / "does-not-exist.json"),
    )
    rc = wgt_module.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR:" in err
    assert "cannot read --payload-file" in err


def test_main_rejects_missing_project_root(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "does-not-exist"
    payload_path = _write_payload_file(tmp_path)
    _set_argv(
        monkeypatch,
        "--project-root", str(missing),
        "--payload-file", str(payload_path),
    )
    rc = wgt_module.main()
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err
    assert not missing.exists()


def test_main_write_trace_grill_trace_error_returns_1(tmp_path, monkeypatch, capsys):
    """A malformed record (blank confirmed_by) surfaces from write_trace()'s
    parse_trace() as GrillTraceError, caught by main()'s
    (GrillTraceError, LockTimeout, OSError, ValueError) handler."""
    payload_path = _write_payload_file(tmp_path, confirmed_by="  ")
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--payload-file", str(payload_path),
    )
    rc = wgt_module.main()
    assert rc == 1
    assert "ERROR:" in capsys.readouterr().err
    assert not (tmp_path / ".shipwright" / "planning" / "grill-traces").exists()


def test_main_lock_timeout_returns_1(tmp_path, monkeypatch, capsys):
    """A lock that can never be acquired surfaces as LockTimeout, caught the
    same way as GrillTraceError/OSError/ValueError."""

    class _AlwaysTimesOut:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            raise LockTimeout("could not acquire lock")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(wgt_module, "file_lock", _AlwaysTimesOut)
    payload_path = _write_payload_file(tmp_path)
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--payload-file", str(payload_path),
    )
    rc = wgt_module.main()
    assert rc == 1
    assert "could not acquire lock" in capsys.readouterr().err
    assert not (tmp_path / ".shipwright" / "planning" / "grill-traces" / "login-rate-limit.json").exists()
