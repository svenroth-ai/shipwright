"""In-process (non-subprocess) coverage for write_context_term.py's bootstrap
sys.path insertion and ``main()``.

``test_write_context_term_cli.py`` and ``test_write_context_term_payload.py``
exercise the CLI's *behavior* correctly, but they do it via
``subprocess.run([sys.executable, str(SCRIPT), ...])`` — a genuinely separate
Python process that this test session's coverage instrumentation never
observes (no ``COVERAGE_PROCESS_START``/``sitecustomize`` subprocess hook is
configured here). That makes ``main()`` invisible to the diff-coverage gate
even though it is behaviorally tested elsewhere. This file re-exercises the
same contracts by importing the module directly and calling ``main()``
in-process, so the coverage tool actually sees the lines execute.

``_write_context_term_cli.py``'s own helper functions
(``build_arg_parser``/``load_payload_file``/``resolve_fields``) get the same
treatment in the sibling ``test_write_context_term_cli_direct.py``.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import tools.write_context_term as wct_module
from lib.file_lock import LockTimeout


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# write_context_term.py — bootstrap sys.path insertion (module-level lines)
# ---------------------------------------------------------------------------

def test_bootstrap_inserts_scripts_root_when_missing_from_syspath(monkeypatch):
    """The ``if str(_SCRIPTS_ROOT) not in sys.path: sys.path.insert(...)``
    bootstrap only executes when the scripts root isn't already present.
    conftest.py always adds it before any test runs, so a normal import never
    exercises the ``True`` branch — force it by removing the entry and
    re-importing fresh."""
    scripts_root = str(Path(__file__).resolve().parents[1] / "scripts")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != scripts_root])
    original_module = sys.modules.pop("tools.write_context_term", None)
    try:
        importlib.import_module("tools.write_context_term")
        assert scripts_root in sys.path
    finally:
        if original_module is not None:
            sys.modules["tools.write_context_term"] = original_module
        else:
            sys.modules.pop("tools.write_context_term", None)


# ---------------------------------------------------------------------------
# write_context_term.py — main(), called in-process
# ---------------------------------------------------------------------------

def _set_argv(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["write_context_term.py", *args])


def test_main_success_path_prints_json_and_returns_0(tmp_path, monkeypatch, capsys):
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--term", "Order",
        "--definition", "a confirmed purchase.",
    )
    rc = wct_module.main()
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "created"
    assert out["term"] == "Order"
    assert "**Order** — a confirmed purchase." in read(tmp_path / "CONTEXT.md")


def test_main_resolve_fields_payload_error_returns_1(tmp_path, monkeypatch, capsys):
    """Neither --payload-file nor --term/--definition given."""
    _set_argv(monkeypatch, "--project-root", str(tmp_path))
    rc = wct_module.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR:" in err
    assert "--term and --definition are required" in err


def test_main_rejects_missing_project_root(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "does-not-exist"
    _set_argv(
        monkeypatch,
        "--project-root", str(missing),
        "--term", "Order",
        "--definition", "x",
    )
    rc = wct_module.main()
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err
    assert not missing.exists()


def test_main_rejects_context_path_with_missing_parent(tmp_path, monkeypatch, capsys):
    bogus = tmp_path / "does-not-exist" / "CONTEXT.md"
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--context-path", str(bogus),
        "--term", "Order",
        "--definition", "x",
    )
    rc = wct_module.main()
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err
    assert not bogus.parent.exists()


def test_main_upsert_value_error_returns_1(tmp_path, monkeypatch, capsys):
    """A blank --term surfaces from upsert_term() as a ValueError, caught by
    main()'s (LockTimeout, OSError, ValueError) handler."""
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--term", "   ",
        "--definition", "x",
    )
    rc = wct_module.main()
    assert rc == 1
    assert "blank" in capsys.readouterr().err
    assert not (tmp_path / "CONTEXT.md").exists()


def test_main_lock_timeout_returns_1(tmp_path, monkeypatch, capsys):
    """A lock that can never be acquired surfaces as LockTimeout, caught the
    same way as OSError/ValueError."""

    class _AlwaysTimesOut:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            raise LockTimeout("could not acquire lock")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(wct_module, "file_lock", _AlwaysTimesOut)
    _set_argv(
        monkeypatch,
        "--project-root", str(tmp_path),
        "--term", "Order",
        "--definition", "x",
    )
    rc = wct_module.main()
    assert rc == 1
    assert "could not acquire lock" in capsys.readouterr().err
    assert not (tmp_path / "CONTEXT.md").exists()
