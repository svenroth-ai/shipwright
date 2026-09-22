"""In-process (non-subprocess) coverage for codex_hooks_sync.py's bootstrap
sys.path insertion, a few malformed-shape branches not exercised by
test_codex_hooks_sync_errors.py, and main()'s CLI body.

``test_cli_help_exits_zero`` (in the errors file) and
``test_launcher_path_with_spaces_actually_runs``'s POSIX leg (in the main
test file) run the real script as a subprocess — genuinely correct
behaviorally, but invisible to this session's diff-coverage instrumentation
(no ``COVERAGE_PROCESS_START``/``sitecustomize`` subprocess hook is
configured in this repo; same gap ``test_write_grill_trace_direct.py``
documents and fixes for ``write_grill_trace.py``). This file calls
``main()`` directly in-process so the coverage tool actually sees those
lines execute.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))  # shared/scripts/lib
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (fixtures helper)

import codex_hooks_sync as sync_module  # noqa: E402
from _codex_hooks_sync_fixtures import SAMPLE_HOOKS, make_bundle  # noqa: E402
from codex_hooks_sync import (  # noqa: E402
    CodexHooksSyncError,
    _is_shipwright_entry,
    main,
    sync_codex_hooks,
)
from plugin_root import PluginRootUnresolvedError  # noqa: E402


def test_bootstrap_inserts_lib_when_missing_from_syspath(monkeypatch):
    """Same gap as codex_hooks_launcher.py's identical guard (see that
    module's own direct-coverage test) — force the True branch."""
    import importlib

    lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != lib_dir])
    original_module = sys.modules.pop("codex_hooks_sync", None)
    try:
        importlib.import_module("codex_hooks_sync")
        assert lib_dir in sys.path
    finally:
        if original_module is not None:
            sys.modules["codex_hooks_sync"] = original_module
        else:
            sys.modules.pop("codex_hooks_sync", None)


def test_load_hooks_json_wrong_top_level_shape_raises(tmp_path):
    """Valid JSON, but the ``hooks`` key itself is not a dict — distinct
    from test_valid_json_wrong_inner_shape_raises, where ``hooks`` IS a dict
    and only an EVENT's value inside it is malformed."""
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text(json.dumps({"hooks": "oops"}), encoding="utf-8")

    with pytest.raises(CodexHooksSyncError, match="not a valid Codex hooks document"):
        sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_validate_sidecar_wrong_shape_raises(tmp_path):
    """Valid JSON, but ``entries`` is not a list."""
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / ".shipwright-hooks-managed.json").write_text(
        json.dumps({"entries": "oops"}), encoding="utf-8"
    )

    with pytest.raises(CodexHooksSyncError, match="not a valid Shipwright sidecar manifest"):
        sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_is_shipwright_entry_false_for_unparseable_command(tmp_path):
    assert _is_shipwright_entry("", tmp_path / "shipwright-hooks") is False


def test_materialize_error_wrapped_as_sync_error(tmp_path):
    """bundle_hooks with a genuinely wrong inner shape (``hooks`` is a
    string, not a list of handler dicts) makes ``_materialize`` raise
    AttributeError when it calls ``.get`` on a character — must surface as
    CodexHooksSyncError, not an uncaught crash."""
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, {"Stop": [{"hooks": "oops"}]})
    codex_home = tmp_path / "codex_home"

    with pytest.raises(CodexHooksSyncError, match="unexpected shape"):
        sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_stale_launcher_removed_successfully_prints_notice(tmp_path, capsys):
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    changed_hooks = json.loads(json.dumps(SAMPLE_HOOKS))
    del changed_hooks["Stop"]
    (bundle_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": changed_hooks}}), encoding="utf-8"
    )

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    assert "removed stale launcher:" in capsys.readouterr().err


def test_stale_launcher_removal_survives_already_gone(tmp_path, monkeypatch):
    """A stale launcher can vanish between ``iterdir()`` yielding it and the
    ``unlink()`` call reaching it (another concurrent sync already swept it)
    — must be swallowed silently, distinct from the PermissionError-sharing-
    violation warning path."""
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    changed_hooks = json.loads(json.dumps(SAMPLE_HOOKS))
    del changed_hooks["Stop"]
    (bundle_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": changed_hooks}}), encoding="utf-8"
    )

    real_unlink = Path.unlink

    def vanished_unlink(self, *args, **kwargs):
        if self.parent.name == "shipwright-hooks":
            raise FileNotFoundError(2, "already gone")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", vanished_unlink)

    result = sync_codex_hooks(bundle_root, codex_home=codex_home)
    assert result.applied is True


# ---------------------------------------------------------------------------
# main() — called in-process
# ---------------------------------------------------------------------------

def test_main_noop_when_bundle_root_is_not_a_codex_bundle(tmp_path, capsys):
    not_a_bundle = tmp_path / "not-a-bundle"
    not_a_bundle.mkdir()
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(not_a_bundle), "--codex-home", str(codex_home)])

    assert rc == 0
    assert "no-op:" in capsys.readouterr().out


def test_main_success_reports_synced_count(tmp_path, capsys):
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home), "--yes"])

    assert rc == 0
    assert "Synced 2 Shipwright hook(s)" in capsys.readouterr().out


def test_main_allow_empty_flag_used(tmp_path, capsys):
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, {})
    codex_home = tmp_path / "codex_home"

    rc = main([
        "--bundle-root", str(bundle_root),
        "--codex-home", str(codex_home),
        "--allow-empty",
        "--yes",
    ])

    assert rc == 0
    assert "Synced 0 Shipwright hook(s)" in capsys.readouterr().out


def test_main_wraps_sync_codex_hooks_error(tmp_path, capsys):
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text("not json", encoding="utf-8")

    rc = main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home), "--yes"])

    assert rc == 1
    assert "error:" in capsys.readouterr().err


# main()'s interactive y/N confirmation checkpoint (Accepted Risk mitigation)
# is covered in test_codex_hooks_sync_confirm.py, split out to stay under
# the repo's 300-LOC guideline.

def test_main_resolve_plugin_root_failure_when_bundle_root_omitted(monkeypatch, capsys):
    def _raise(*a, **kw):
        raise PluginRootUnresolvedError("no plugin root in this environment")

    monkeypatch.setattr(sync_module, "resolve_plugin_root", _raise)

    rc = main([])

    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_main_resolve_plugin_root_success_when_bundle_root_omitted(tmp_path, monkeypatch, capsys):
    """bundle_root resolved via resolve_plugin_root(), codex_home left at
    its ~/.codex default — safe because a not-a-Codex-bundle root makes
    sync_codex_hooks() return before codex_home is ever touched."""
    not_a_bundle = tmp_path / "not-a-bundle"
    not_a_bundle.mkdir()
    monkeypatch.setattr(sync_module, "resolve_plugin_root", lambda: not_a_bundle)

    rc = main([])

    assert rc == 0
    assert "no-op:" in capsys.readouterr().out
