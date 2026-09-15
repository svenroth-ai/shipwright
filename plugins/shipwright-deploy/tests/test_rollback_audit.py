"""Direct unit tests for ``rollback_audit.py``.

The CLI path (``test_rollback_e2e_cli.py``) exercises this module through
``rollback.py``, always passing ``--project-root``. These tests cover the
module's own contract in isolation, including a defensive edge the CLI
path never reaches.
"""

import json
from pathlib import Path

import rollback_audit


def test_history_path_resolves_relative_to_project_root(tmp_path):
    resolved = rollback_audit.history_path(tmp_path)
    assert resolved == tmp_path / ".shipwright" / "deploy" / "rollback-history.jsonl"


def test_history_path_falls_back_to_cwd_when_project_root_is_none(tmp_path, monkeypatch):
    """External code review (rounds 1 and 2, e4-checks-deploy-changelog):
    defensive coverage for a ``None`` project root, even though no CLI
    invocation currently reaches this — verified separately by the CLI's
    own argparse default (``"."``), never ``None``.
    """
    monkeypatch.chdir(tmp_path)
    resolved = rollback_audit.history_path(None)
    assert resolved == Path.cwd() / ".shipwright" / "deploy" / "rollback-history.jsonl"


def test_record_with_a_none_project_root_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    entry = rollback_audit.record(None, {"success": True, "env_name": "dev"})
    assert entry["env_name"] == "dev"
    assert (tmp_path / ".shipwright" / "deploy" / "rollback-history.jsonl").exists()


def test_two_records_append_rather_than_overwrite(tmp_path):
    """Code review (e4-checks-deploy-changelog): the module's own docstring
    calls the trail "append-only" — assert it, not merely that a call
    succeeds."""
    rollback_audit.record(tmp_path, {"success": True, "env_name": "first"})
    rollback_audit.record(tmp_path, {"success": False, "env_name": "second"})
    lines = rollback_audit.history_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["env_name"] == "first"
    assert json.loads(lines[1])["env_name"] == "second"


def test_a_reason_containing_a_newline_stays_on_one_jsonl_line(tmp_path):
    """Code review (e4-checks-deploy-changelog): the module's own docstring
    claims ``json.dumps`` escapes an embedded newline so one ``record()``
    call can never itself tear a line — assert it round-trips, not merely
    that the module's prose says so."""
    reason = "line one\nline two"
    rollback_audit.record(tmp_path, {"success": True, "env_name": "dev", "override_reason": reason})
    lines = rollback_audit.history_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["override_reason"] == reason


def test_result_cannot_clobber_the_audit_recorded_at_or_invocation_fields(tmp_path):
    """Code review (e4-checks-deploy-changelog): a ``result`` dict that
    happens to carry its own ``invocation`` or ``recorded_at`` key must
    never displace the audit-owned values — ``check_manual_rollback_proves_alive``
    filters and orders on exactly these two fields.
    """
    entry = rollback_audit.record(
        tmp_path,
        {"success": True, "env_name": "dev", "invocation": "auto", "recorded_at": "bogus"},
        invocation="manual",
    )
    assert entry["invocation"] == "manual"
    assert entry["recorded_at"] != "bogus"


def test_record_degraded_writes_a_marker_next_to_the_history_file(tmp_path):
    rollback_audit.record_degraded(tmp_path, invocation="manual", reason="lock timeout")
    marker = tmp_path / ".shipwright" / "deploy" / "rollback-audit-degraded.jsonl"
    lines = marker.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["invocation"] == "manual"
    assert entry["reason"] == "lock timeout"
    assert "at" in entry


def test_record_degraded_never_raises_even_when_the_write_itself_fails(tmp_path, monkeypatch):
    """This runs from inside rollback.py's own except handler around a
    failed audit write — a SECOND storage failure here must never mask the
    real rollback outcome (exit code / operator_message) that already
    happened (Tier-3 PR review round 4)."""
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", _boom)
    rollback_audit.record_degraded(tmp_path, invocation="manual", reason="lock timeout")


def test_module_bootstraps_its_own_sys_path_when_not_already_present(monkeypatch):
    """The module's own sys.path bootstrap (mirroring ``rollback.py``'s,
    independently — the docstring's claim is that this module's import order
    never depends on a caller having extended sys.path first). Removing the
    shared-scripts path and re-importing fresh proves the guard actually
    re-adds it, not merely that it no-ops because something else already did.
    """
    import importlib
    import sys

    shared_scripts = str(rollback_audit._SHARED_SCRIPTS)
    original_module = sys.modules.get("rollback_audit")

    pruned_path = [p for p in sys.path if p != shared_scripts]
    monkeypatch.setattr(sys, "path", pruned_path)
    sys.modules.pop("rollback_audit", None)
    try:
        reloaded = importlib.import_module("rollback_audit")
        assert shared_scripts in sys.path
        assert reloaded.HISTORY_RELATIVE_PATH == rollback_audit.HISTORY_RELATIVE_PATH
    finally:
        if original_module is not None:
            sys.modules["rollback_audit"] = original_module
