"""Tests for verify_codex_plugin_bundle.py (M1, AC5 — drift/verifier).

Strategy: rebuild the bundle fresh into a throwaway directory and diff its
file-hash tree against the live bundle directory being checked. This never
trusts the live bundle's own BUILD_MANIFEST.json (which could itself be
stale or tampered) — the fresh rebuild IS the ground truth, exactly as
build_codex_plugin.py's own AC4 byte-identical-rebuild guarantee promises.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import pytest

from build_codex_plugin import UnsafeSourceSymlinkError, build_bundle  # noqa: E402
from verify_codex_plugin_bundle import verify_bundle  # noqa: E402

from _bundle_fixtures import write_plugin, write_shared  # noqa: E402


def _symlink(src: Path, dst: Path) -> None:
    """Create a symlink, or skip. Windows needs Developer Mode/admin; no CI job
    runs on Windows (same constraint as test_security_gate_symlinks.py), so CI
    must never take the skip silently."""
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError) as exc:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                f"symlink creation failed in CI ({exc!r}); this suite must "
                "exercise the live-bundle symlink-refusal branch of _hash_tree. "
                "Run on a filesystem/user that permits symlinks.")
        pytest.skip(f"symlinks not permitted on this host ({exc!r})")


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


@pytest.mark.covers("FR-01.21/AC03")
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


def test_a_symlink_planted_in_the_live_bundle_is_refused(tmp_path):
    """A symlink added directly to an already-built bundle (never produced by
    build_bundle, which refuses symlinks in its own source trees) would
    otherwise have its target's content hashed as bundle content by
    _hash_tree — refuse rather than compare a tampered tree (local PR-review
    preflight comment, 2026-09-21)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    bundle_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=bundle_dir)

    outside_target = tmp_path / "outside-the-repo.txt"
    outside_target.write_text("not part of any declared source", encoding="utf-8")
    _symlink(outside_target, bundle_dir / "skills" / "alpha" / "escape.txt")

    with pytest.raises(UnsafeSourceSymlinkError, match="escape.txt"):
        verify_bundle(project_root=tmp_path, bundle_dir=bundle_dir)


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
