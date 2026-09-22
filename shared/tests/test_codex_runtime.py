"""Tests for shared/scripts/lib/codex_runtime.py (R1b — AC1).

``is_codex_runtime()`` must be true ONLY when the resolved plugin root is a
real, on-disk Codex bundle — both of ``build_codex_plugin.py``'s own root
markers present (``BUILD_MANIFEST.json`` and ``.codex-plugin/plugin.json``)
AND genuinely shaped like that builder's real output, never a bare
presence/env-var check. See the iterate spec's AC1 for the full contract
and why: a plain Claude plugin-cache root, a stray unrelated env-var value,
or a placeholder/empty marker pair must not be mistaken for a bundle
(external code review, both legs, medium — presence-only trust let two
empty marker files pass)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_bundle(root: Path, *, manifest: bool, plugin_json: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if manifest:
        (root / "BUILD_MANIFEST.json").write_text(
            json.dumps({"version": "0.0.0-test", "files": {"plugin.json": "0" * 64}}),
            encoding="utf-8",
        )
    if plugin_json:
        codex_plugin_dir = root / ".codex-plugin"
        codex_plugin_dir.mkdir(parents=True, exist_ok=True)
        (codex_plugin_dir / "plugin.json").write_text(
            json.dumps({"hooks": {"hooks": {}}}), encoding="utf-8"
        )


def test_true_when_both_markers_present(tmp_path):
    bundle_root = tmp_path / "bundle"
    _make_bundle(bundle_root, manifest=True, plugin_json=True)

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(bundle_root) is True


def test_false_with_only_build_manifest(tmp_path):
    bundle_root = tmp_path / "bundle"
    _make_bundle(bundle_root, manifest=True, plugin_json=False)

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(bundle_root) is False


def test_false_with_only_plugin_json(tmp_path):
    bundle_root = tmp_path / "bundle"
    _make_bundle(bundle_root, manifest=False, plugin_json=True)

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(bundle_root) is False


def test_false_with_neither_marker(tmp_path):
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(bundle_root) is False


def test_false_when_path_does_not_exist(tmp_path):
    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(tmp_path / "does-not-exist") is False


def test_false_for_unrelated_real_directory(tmp_path):
    """A stray env-var value pointing at some other real, populated
    directory (e.g. a Claude per-plugin cache dir, which has its own
    ``.claude-plugin/plugin.json`` — a DIFFERENT path — but never the Codex
    bundle's two markers together) must not be mistaken for a bundle."""
    unrelated = tmp_path / "cache" / "shipwright" / "shipwright-iterate" / "0.4.1"
    unrelated.mkdir(parents=True)
    (unrelated / ".claude-plugin").mkdir()
    (unrelated / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(unrelated) is False


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SHIPWRIGHT_PLUGIN_ROOT", "PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        monkeypatch.delenv(var, raising=False)


def test_resolves_plugin_root_from_env_when_not_given(monkeypatch, tmp_path):
    bundle_root = tmp_path / "bundle"
    _make_bundle(bundle_root, manifest=True, plugin_json=True)
    monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle_root))

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime() is True


def test_false_when_no_plugin_root_env_var_resolvable(monkeypatch):
    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime() is False


def test_false_with_empty_placeholder_markers(tmp_path):
    """Two present-but-empty marker files (the cheapest possible spoof —
    ``touch BUILD_MANIFEST.json``) must not pass; presence alone used to be
    sufficient (external code review, both legs, medium)."""
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    (bundle_root / "BUILD_MANIFEST.json").write_text("{}", encoding="utf-8")
    codex_plugin_dir = bundle_root / ".codex-plugin"
    codex_plugin_dir.mkdir()
    (codex_plugin_dir / "plugin.json").write_text("{}", encoding="utf-8")

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(bundle_root) is False


def test_false_with_malformed_build_manifest(tmp_path):
    """Only BUILD_MANIFEST.json is shape-checked here — a malformed
    plugin.json on an otherwise-genuine bundle is `_read_bundle_hooks()`'s
    job to raise loudly on, not this function's to silently no-op (module
    docstring)."""
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    (bundle_root / "BUILD_MANIFEST.json").write_text("not json", encoding="utf-8")
    codex_plugin_dir = bundle_root / ".codex-plugin"
    codex_plugin_dir.mkdir()
    (codex_plugin_dir / "plugin.json").write_text("{}", encoding="utf-8")

    from lib.codex_runtime import is_codex_runtime
    assert is_codex_runtime(bundle_root) is False
