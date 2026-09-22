"""Malformed-input, lock-contention, and CLI-smoke tests for
shared/scripts/tools/codex_hooks_sync.py (R1b). Split out of
test_codex_hooks_sync.py to stay under the repo's 300-LOC guideline.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))  # shared/scripts/lib
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (fixtures helper)

from _codex_hooks_sync_fixtures import SAMPLE_HOOKS, make_bundle  # noqa: E402


def test_malformed_bundle_plugin_json_raises(tmp_path):
    from codex_hooks_sync import CodexHooksSyncError, sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    # Genuinely-shaped, not "{}" — is_codex_runtime() now checks shape, not
    # just presence, so a placeholder manifest would no-op before this
    # test's real malformed-plugin.json case is ever reached.
    (bundle_root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"version": "0.0.0-test", "files": {"plugin.json": "0" * 64}}),
        encoding="utf-8",
    )
    codex_plugin_dir = bundle_root / ".codex-plugin"
    codex_plugin_dir.mkdir()
    (codex_plugin_dir / "plugin.json").write_text("not json", encoding="utf-8")

    with pytest.raises(CodexHooksSyncError):
        sync_codex_hooks(bundle_root, codex_home=tmp_path / "codex_home")


def test_malformed_existing_hooks_json_raises(tmp_path):
    from codex_hooks_sync import CodexHooksSyncError, sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text("not json", encoding="utf-8")

    with pytest.raises(CodexHooksSyncError):
        sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_valid_json_wrong_inner_shape_raises(tmp_path):
    """Distinct from invalid-JSON above: `hooks.json` parses fine but an
    event's value is a string, not a list of groups — the mini-plan's
    'valid JSON but the wrong shape' case, which the top-level `isinstance`
    check in `_load_hooks_json` does not catch on its own (code review,
    medium)."""
    from codex_hooks_sync import CodexHooksSyncError, sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": "oops"}}), encoding="utf-8"
    )

    with pytest.raises(CodexHooksSyncError):
        sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_relative_paths_resolved_to_absolute(tmp_path, monkeypatch):
    """A relative bundle_root/codex_home must still produce absolute
    launcher paths in hooks.json — otherwise the launcher path Codex reads
    back depends on ITS working directory at hook-fire time, not the
    working directory this tool happened to run from (code review,
    medium)."""
    from codex_hooks_sync import sync_codex_hooks

    monkeypatch.chdir(tmp_path)
    bundle_root = Path("bundle")
    make_bundle(tmp_path / bundle_root, SAMPLE_HOOKS)
    codex_home = Path("codex_home")

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    doc = json.loads((tmp_path / "codex_home" / "hooks.json").read_text(encoding="utf-8"))
    launcher = doc["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert Path(launcher).is_absolute()


def test_empty_bundle_raises_unless_allow_empty(tmp_path):
    """A bundle whose hooks map is empty is far more likely a corrupt or
    partial build than a genuine 'no hooks' Shipwright bundle — syncing it
    unguarded would silently strip every previously-synced Shipwright entry
    from hooks.json (doubt-reviewer, medium)."""
    from codex_hooks_sync import CodexHooksSyncError, sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, {})
    codex_home = tmp_path / "codex_home"

    with pytest.raises(CodexHooksSyncError):
        sync_codex_hooks(bundle_root, codex_home=codex_home)

    result = sync_codex_hooks(bundle_root, codex_home=codex_home, allow_empty=True)
    assert result.applied is True
    assert result.hooks_written == 0


def test_malformed_sidecar_raises(tmp_path):
    from codex_hooks_sync import CodexHooksSyncError, sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / ".shipwright-hooks-managed.json").write_text(
        "not json", encoding="utf-8"
    )

    with pytest.raises(CodexHooksSyncError):
        sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_lock_contention_raises_clear_error(tmp_path):
    from codex_hooks_sync import CodexHooksSyncError, sync_codex_hooks
    from file_lock import file_lock

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()

    lock_path = codex_home / ".shipwright-hooks-sync.lock"
    with file_lock(lock_path, timeout_seconds=0):
        # Specifically CodexHooksSyncError, not the too-broad RuntimeError
        # it subclasses — a bare RuntimeError assertion would still pass
        # even if the `except LockTimeout` wrapper below it were deleted
        # (external review, glm leg, low).
        with pytest.raises(CodexHooksSyncError, match=re.escape(str(lock_path))):
            sync_codex_hooks(bundle_root, codex_home=codex_home)


def test_cli_help_exits_zero():
    script = Path(__file__).resolve().parents[1] / "codex_hooks_sync.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
