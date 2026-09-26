"""Tests for build_codex_plugin.py (M1 — deterministic Codex plugin bundle).

Uses small fixture source trees (2-3 fake plugins + a fake ``shared/``)
rather than the real 14-plugin monorepo tree, so these stay fast and the
fixtures can deliberately exercise dedup and collision cases the real,
currently-consistent tree does not have. Hook-merge-semantics tests
(dedup, collision, matcher-distinction, dispatcher-union) live in
`test_codex_hook_merge.py` — this file keeps the builder-level concerns:
skill discovery, shared-tree bundling, per-origin script namespacing,
byte-identical rebuild, and the emitted manifests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from build_codex_plugin import build_bundle  # noqa: E402

from _bundle_fixtures import write_plugin, write_shared  # noqa: E402


@pytest.mark.covers("FR-01.21/AC01")
def test_skills_from_every_plugin_are_discoverable(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")
    write_plugin(tmp_path, "shipwright-beta")

    out_dir = tmp_path / "dist"
    result = build_bundle(project_root=tmp_path, out_dir=out_dir)

    assert (out_dir / "skills" / "alpha" / "SKILL.md").exists()
    assert (out_dir / "skills" / "beta" / "SKILL.md").exists()
    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["skills"] == "./skills/"
    assert result.skill_count == 2


def test_shared_is_bundled_excluding_tests(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    assert (out_dir / "shared" / "scripts" / "hooks" / "shared_hook.py").exists()
    assert not (out_dir / "shared" / "tests").exists()


def test_own_plugin_hook_stays_distinct_per_origin(tmp_path):
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        hooks={
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/alpha_only.py"',
                        }
                    ]
                }
            ]
        },
        own_script="alpha_only.py",
    )
    write_plugin(
        tmp_path,
        "shipwright-beta",
        hooks={
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/beta_only.py"',
                        }
                    ]
                }
            ]
        },
        own_script="beta_only.py",
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    stop_commands = {
        h["command"]
        for group in manifest["hooks"]["hooks"]["Stop"]
        for h in group["hooks"]
    }
    assert stop_commands == {
        'uv run "${CLAUDE_PLUGIN_ROOT}/origin/shipwright-alpha/scripts/hooks/alpha_only.py"',
        'uv run "${CLAUDE_PLUGIN_ROOT}/origin/shipwright-beta/scripts/hooks/beta_only.py"',
    }
    assert (out_dir / "origin" / "shipwright-alpha" / "scripts" / "hooks" / "alpha_only.py").exists()
    assert (out_dir / "origin" / "shipwright-beta" / "scripts" / "hooks" / "beta_only.py").exists()


@pytest.mark.parametrize(
    "pycache_src,pycache_dst",
    [
        (
            "plugins/shipwright-alpha/scripts/hooks/__pycache__",
            "origin/shipwright-alpha/scripts/hooks/__pycache__",
        ),
        (
            "plugins/shipwright-alpha/skills/alpha/__pycache__",
            "skills/alpha/__pycache__",
        ),
        (
            "shared/scripts/hooks/__pycache__",
            "shared/scripts/hooks/__pycache__",
        ),
    ],
    ids=["origin-scripts", "skills", "shared"],
)
def test_pycache_is_excluded_from_every_copied_tree(tmp_path, pycache_src, pycache_dst):
    """Real-repo bug: a developer's local ``__pycache__`` must not leak into
    the bundle from ANY of the three copied trees (a plugin's own scripts,
    its skills, or shared/) — it is machine/run-local generated content, not
    source, and its presence or absence would make AC4's byte-identical-
    rebuild guarantee depend on whether the last person to build happened to
    have compiled bytecode lying around."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha", own_script="alpha_hook.py")

    pycache_dir = tmp_path / pycache_src
    pycache_dir.mkdir(parents=True, exist_ok=True)
    (pycache_dir / "cached.cpython-311.pyc").write_bytes(b"\x00\x01")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    assert not (out_dir / pycache_dst).exists()


@pytest.mark.parametrize(
    "node_modules_src,node_modules_dst",
    [
        (
            "plugins/shipwright-alpha/scripts/hooks/node_modules",
            "origin/shipwright-alpha/scripts/hooks/node_modules",
        ),
        (
            "plugins/shipwright-alpha/skills/alpha/node_modules",
            "skills/alpha/node_modules",
        ),
        (
            "shared/scripts/hooks/node_modules",
            "shared/scripts/hooks/node_modules",
        ),
    ],
    ids=["origin-scripts", "skills", "shared"],
)
def test_node_modules_is_excluded_from_every_copied_tree(tmp_path, node_modules_src, node_modules_dst):
    """Real-repo bug: a locally-installed npm dependency tree (e.g.
    ``shipwright-test/scripts/perf``'s Lighthouse runner) must not be bundled
    from ANY of the three copied trees — it is build/test-time-only JS
    tooling, never something a Codex hook needs at runtime, and a deeply
    nested package (``@scope/pkg/.../file.js``) can exceed Windows' 260-char
    MAX_PATH during the copy, failing the whole build with ``shutil.Error``."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha", own_script="alpha_hook.py")

    node_modules_dir = tmp_path / node_modules_src / "some-pkg"
    node_modules_dir.mkdir(parents=True, exist_ok=True)
    (node_modules_dir / "index.js").write_text("", encoding="utf-8")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    assert not (out_dir / node_modules_dst).exists()


@pytest.mark.covers("FR-01.21/AC03")
def test_clean_rebuild_is_byte_identical(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)
    first_manifest = (out_dir / "BUILD_MANIFEST.json").read_text()
    first_plugin_json = (out_dir / ".codex-plugin" / "plugin.json").read_text()

    build_bundle(project_root=tmp_path, out_dir=out_dir)
    second_manifest = (out_dir / "BUILD_MANIFEST.json").read_text()
    second_plugin_json = (out_dir / ".codex-plugin" / "plugin.json").read_text()

    assert first_manifest == second_manifest
    assert first_plugin_json == second_plugin_json


def test_bundle_version_matches_marketplace_version(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["version"] == "9.9.9"


def test_local_marketplace_manifest_emitted(tmp_path):
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist" / "codex-plugin"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    marketplace = json.loads((out_dir.parent / ".agents" / "plugins" / "marketplace.json").read_text())
    assert marketplace["plugins"][0]["name"] == "shipwright"
    assert marketplace["plugins"][0]["source"]["path"] == "./codex-plugin"
