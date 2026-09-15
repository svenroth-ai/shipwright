"""Direct unit tests for ``rollback_audit.py``.

The CLI path (``test_rollback_e2e_cli.py``) exercises this module through
``rollback.py``, always passing ``--project-root``. These tests cover the
module's own contract in isolation, including a defensive edge the CLI
path never reaches.
"""

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
