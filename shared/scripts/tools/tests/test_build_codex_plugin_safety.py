"""Destructive-write safety tests for build_codex_plugin.py (M1).

Split out of test_build_codex_plugin.py to keep concerns separated (see that
file's own docstring). ``build_bundle`` deletes its output directory and
overwrites a marketplace manifest in the output directory's PARENT — found
under doubt-review (2026-09-20) to have no guard against an out-dir that
collides with the project root, an out-dir that isn't ours to begin with, or
a pre-existing marketplace.json belonging to something else.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import pytest

from build_codex_plugin import (  # noqa: E402
    BundleCollisionError,
    UnsafeOutputPathError,
    UnsafeSourceSymlinkError,
    build_bundle,
)

from _bundle_fixtures import write_plugin, write_shared  # noqa: E402


def _symlink(src: Path, dst: Path, *, dir_target: bool = False) -> None:
    """Create a symlink, or skip. Windows needs Developer Mode/admin; no CI job
    runs on Windows (same constraint as test_security_gate_symlinks.py), so CI
    must never take the skip silently."""
    try:
        os.symlink(src, dst, target_is_directory=dir_target)
    except (OSError, NotImplementedError) as exc:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                f"symlink creation failed in CI ({exc!r}); this suite must "
                "exercise the symlink-refusal branch of _copy_tree. Run on a "
                "filesystem/user that permits symlinks.")
        pytest.skip(f"symlinks not permitted on this host ({exc!r})")


def test_refuses_an_out_dir_that_is_itself_a_symlink(tmp_path):
    """build_bundle immediately .resolve()s out_dir, which transparently
    follows a symlink to whatever it points at — every later check (incl.
    is_prior_bundle) would then operate on that RESOLVED target, so a
    symlinked --out pointing at some other directory that merely looks like
    a prior bundle could pass every check while the actual rmtree/rebuild
    lands somewhere the operator never typed (local PR-review preflight,
    2026-09-21)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    real_target = tmp_path / "elsewhere"
    (real_target / ".codex-plugin").mkdir(parents=True)
    (real_target / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "shipwright", "version": "1.0.0"}), encoding="utf-8"
    )
    out_link = tmp_path / "dist-link"
    _symlink(real_target, out_link, dir_target=True)

    with pytest.raises(UnsafeOutputPathError, match="symlink"):
        build_bundle(project_root=tmp_path, out_dir=out_link)


def test_refuses_when_out_dir_is_the_project_root(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    # match= proves the project-root guard fired specifically, not the
    # separate non-bundle-directory guard — tmp_path is also non-empty and
    # marker-less, so both would independently raise here without it
    # (code-review round, 2026-09-20).
    with pytest.raises(UnsafeOutputPathError, match="project root"):
        build_bundle(project_root=tmp_path, out_dir=tmp_path)


def test_refuses_when_out_dir_is_an_ancestor_of_the_project_root(tmp_path):
    project_root = tmp_path / "repo"
    project_root.mkdir()
    write_shared(project_root)
    write_plugin(project_root, "shipwright-alpha")

    with pytest.raises(UnsafeOutputPathError, match="project root"):
        build_bundle(project_root=project_root, out_dir=tmp_path)


def test_refuses_to_clobber_a_directory_that_is_not_a_prior_bundle(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "not-a-bundle"
    out_dir.mkdir()
    (out_dir / "important.txt").write_text("someone else's file", encoding="utf-8")

    with pytest.raises(UnsafeOutputPathError):
        build_bundle(project_root=tmp_path, out_dir=out_dir)


def test_rebuilding_into_a_prior_bundle_directory_is_allowed(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)
    build_bundle(project_root=tmp_path, out_dir=out_dir)  # must not raise

    assert (out_dir / ".codex-plugin" / "plugin.json").exists()


def test_refuses_a_same_named_skill_declared_by_two_plugins(tmp_path):
    """Skill folders flatten into one shared namespace (build_codex_plugin's
    own docstring: "no name collisions across the 14 source plugins") —
    without a guard, _copy_tree's rmtree would silently discard one plugin's
    skill in favor of the other's (Internal Plan Review, 2026-09-20)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha", skill_name="shared-name")
    write_plugin(tmp_path, "shipwright-beta", skill_name="shared-name")

    with pytest.raises(BundleCollisionError, match="shared-name"):
        build_bundle(project_root=tmp_path, out_dir=tmp_path / "dist")


def test_recovers_from_an_interrupted_build(tmp_path, monkeypatch):
    """A build interrupted after out_dir.mkdir() but before copying finishes
    (Ctrl-C, disk full, a file an editor/AV holds open) must not leave a
    directory the NEXT build refuses to touch — the marker is written before
    any copying starts specifically so a retry recognizes its own partial
    work (code-review round, 2026-09-20; this bug was introduced by the
    output-path safety guards themselves)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    import build_codex_plugin

    original_copy_tree = build_codex_plugin._copy_tree
    calls = {"n": 0}

    def _fail_first_copy(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated interruption")
        return original_copy_tree(*args, **kwargs)

    monkeypatch.setattr(build_codex_plugin, "_copy_tree", _fail_first_copy)
    out_dir = tmp_path / "dist"
    with pytest.raises(OSError, match="simulated interruption"):
        build_bundle(project_root=tmp_path, out_dir=out_dir)

    assert (out_dir / ".codex-plugin" / "plugin.json").exists()

    monkeypatch.setattr(build_codex_plugin, "_copy_tree", original_copy_tree)
    build_bundle(project_root=tmp_path, out_dir=out_dir)  # must not raise


def test_refuses_a_symlink_inside_a_plugin_source_tree(tmp_path):
    """shutil.copytree defaults to symlinks=False, which FOLLOWS a symlink and
    copies its target's content — a symlink inside a plugin's source tree
    could point anywhere on disk and have that content silently bundled with
    no provenance record (local PR-review preflight, 2026-09-21)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    outside_target = tmp_path / "outside-the-repo.txt"
    outside_target.write_text("not part of any declared source", encoding="utf-8")
    _symlink(
        outside_target,
        tmp_path / "plugins" / "shipwright-alpha" / "skills" / "alpha" / "escape.txt",
    )

    with pytest.raises(UnsafeSourceSymlinkError, match="escape.txt"):
        build_bundle(project_root=tmp_path, out_dir=tmp_path / "dist")


def test_a_symlink_inside_an_excluded_dir_does_not_false_block(tmp_path):
    """A symlink under an excluded dirname (e.g. tests/) is never copied, so
    it must not be flagged either — only symlinks that would actually reach
    the bundle are the builder's problem."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    outside_target = tmp_path / "outside-the-repo.txt"
    outside_target.write_text("irrelevant", encoding="utf-8")
    tests_dir = tmp_path / "plugins" / "shipwright-alpha" / "scripts" / "tests"
    tests_dir.mkdir(parents=True)
    _symlink(outside_target, tests_dir / "escape.txt")

    build_bundle(project_root=tmp_path, out_dir=tmp_path / "dist")  # must not raise


def test_refuses_a_symlinked_agents_dir_ancestor_of_the_marketplace_path(tmp_path):
    """A symlink at an ANCESTOR of marketplace.json (.agents or
    .agents/plugins) is just as unsafe as a symlinked marketplace.json
    itself: mkdir(parents=True) and write_text() both transparently follow a
    symlinked ancestor directory, letting the write land somewhere the
    operator never asked for — checking only the exact marketplace.json
    path missed this (local PR-review preflight, 2026-09-21)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist" / "codex-plugin"
    out_dir.parent.mkdir()
    elsewhere = tmp_path / "elsewhere-entirely"
    elsewhere.mkdir()
    _symlink(elsewhere, out_dir.parent / ".agents", dir_target=True)

    with pytest.raises(UnsafeOutputPathError, match="symlink"):
        build_bundle(project_root=tmp_path, out_dir=out_dir)


def test_refuses_a_symlinked_marketplace_json_even_with_valid_looking_content(tmp_path):
    """refuse_foreign_marketplace's content check alone is not enough: a
    symlink at the marketplace.json path whose TARGET happens to contain a
    valid {"name": "shipwright"} manifest would pass the content check, and
    write_text's own symlink-following would then overwrite whatever that
    target actually is — reject the symlink outright, before reading its
    content (local PR-review preflight, 2026-09-21)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist" / "codex-plugin"
    marketplace_dir = out_dir.parent / ".agents" / "plugins"
    marketplace_dir.mkdir(parents=True)

    real_target = tmp_path / "somewhere-else-entirely.json"
    real_target.write_text(json.dumps({"name": "shipwright", "plugins": []}), encoding="utf-8")
    _symlink(real_target, marketplace_dir / "marketplace.json")

    with pytest.raises(UnsafeOutputPathError, match="symlink"):
        build_bundle(project_root=tmp_path, out_dir=out_dir)


def test_refuses_to_overwrite_a_foreign_marketplace_json(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist" / "codex-plugin"
    marketplace_dir = out_dir.parent / ".agents" / "plugins"
    marketplace_dir.mkdir(parents=True)
    (marketplace_dir / "marketplace.json").write_text(
        json.dumps({"name": "someone-elses-marketplace", "plugins": []}), encoding="utf-8"
    )

    with pytest.raises(UnsafeOutputPathError):
        build_bundle(project_root=tmp_path, out_dir=out_dir)


def test_refuses_a_directory_at_the_marketplace_json_path(tmp_path):
    """A pre-existing directory at the marketplace.json path is not something
    this builder ever created — without a check, write_text() raises an
    uncaught IsADirectoryError instead of a clean refusal (local PR-review
    preflight, 2026-09-21)."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist" / "codex-plugin"
    marketplace_dir = out_dir.parent / ".agents" / "plugins"
    (marketplace_dir / "marketplace.json").mkdir(parents=True)

    with pytest.raises(UnsafeOutputPathError, match="not a regular file"):
        build_bundle(project_root=tmp_path, out_dir=out_dir)
