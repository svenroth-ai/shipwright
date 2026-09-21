"""Tests for verify_codex_plugin_bundle.py (M1, AC5 — drift/verifier).

Strategy: rebuild the bundle fresh into a throwaway directory and diff its
file-hash tree against the live bundle directory being checked. This never
trusts the live bundle's own BUILD_MANIFEST.json (which could itself be
stale or tampered) — the fresh rebuild IS the ground truth, exactly as
build_codex_plugin.py's own AC4 byte-identical-rebuild guarantee promises.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from build_codex_plugin import build_bundle  # noqa: E402
from verify_codex_plugin_bundle import verify_bundle  # noqa: E402

from _bundle_fixtures import write_plugin, write_shared  # noqa: E402


def test_clean_bundle_passes(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    bundle_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=bundle_dir)

    result = verify_bundle(project_root=tmp_path, bundle_dir=bundle_dir)

    assert result.ok is True
    assert result.stale_files == []
    assert result.undeclared_files == []
    assert result.missing_files == []


def test_stale_bundle_source_changed_not_rebuilt_fails(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    bundle_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=bundle_dir)

    # Source changes AFTER the build — bundle is not rebuilt.
    (tmp_path / "plugins" / "shipwright-alpha" / "skills" / "alpha" / "SKILL.md").write_text(
        "# alpha\n\nchanged after the build\n", encoding="utf-8"
    )

    result = verify_bundle(project_root=tmp_path, bundle_dir=bundle_dir)

    assert result.ok is False
    assert any("SKILL.md" in f for f in result.stale_files)


def test_undeclared_file_in_bundle_fails(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    bundle_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=bundle_dir)

    # Content inserted directly into the bundle output, never produced by a
    # rebuild from source — e.g. a path-escape or hand-edited addition.
    rogue = bundle_dir / "skills" / "alpha" / "rogue.txt"
    rogue.write_text("not from source\n", encoding="utf-8")

    result = verify_bundle(project_root=tmp_path, bundle_dir=bundle_dir)

    assert result.ok is False
    assert any("rogue.txt" in f for f in result.undeclared_files)


def test_missing_file_source_added_bundle_not_rebuilt_fails(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    bundle_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=bundle_dir)

    # A new source file is added after the build — the bundle now lacks it.
    (tmp_path / "plugins" / "shipwright-alpha" / "skills" / "alpha" / "reference.md").write_text(
        "new reference doc\n", encoding="utf-8"
    )

    result = verify_bundle(project_root=tmp_path, bundle_dir=bundle_dir)

    assert result.ok is False
    assert any("reference.md" in f for f in result.missing_files)
