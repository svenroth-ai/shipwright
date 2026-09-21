#!/usr/bin/env python3
"""Deterministic Codex plugin bundle builder (M1).

Builds one real, installable Codex plugin bundle from the canonical monorepo
source tree — never a hand-edited second copy. Reads every
``plugins/*/.claude-plugin/plugin.json`` + ``hooks/hooks.json`` + ``skills/``
+ ``scripts/``, plus ``shared/`` (excluding ``shared/tests/`` and other
non-runtime dirs), and emits:

- ``<out>/.codex-plugin/plugin.json`` — the umbrella manifest, with an
  inline, deduplicated hook inventory (Codex accepts an inline ``hooks``
  object shaped like Claude's own ``hooks.json``, confirmed against a real
  installed Codex plugin during Repo Scout — see the iterate spec's Design
  Notes);
- ``<out>/skills/<name>/`` — every plugin's skill folder, flattened (no name
  collisions across the 14 source plugins);
- ``<out>/origin/<plugin-name>/scripts/`` — each plugin's own scripts,
  namespaced by origin so a plugin-own hook command still resolves once
  there is only one umbrella plugin;
- ``<out>/shared/`` — the shared runtime, copied once;
- ``<out>/BUILD_MANIFEST.json`` — source-path -> bundled-path + sha256 map,
  consumed by ``verify_codex_plugin_bundle.py``'s drift checks;
- ``<out-parent>/.agents/plugins/marketplace.json`` — a local, file-based
  Codex marketplace entry, so the bundle is installable via
  ``codex plugin marketplace add <out-parent>`` + ``codex plugin add
  shipwright@shipwright`` during development (mirrors the pattern
  ``shared/prompts/writing-plugin.md`` already documents for Claude's own
  dev-sync flow).

Hook command paths are rewritten so the bundle is self-contained (M1: "no
skill depends on ``~/.claude/plugins/cache``"), keeping the SAME variable
name Codex already sets (compatibility mode) for a plugin-bundled hook —
``${CLAUDE_PLUGIN_ROOT}`` — rather than an application-level convention
nothing exports at shell-expansion time (see ``codex_hook_merge._rewrite_command``):

- ``${CLAUDE_PLUGIN_ROOT}/../../shared/...`` -> ``${CLAUDE_PLUGIN_ROOT}/shared/...``
- ``${CLAUDE_PLUGIN_ROOT}/...`` (a plugin's own script) ->
  ``${CLAUDE_PLUGIN_ROOT}/origin/<plugin-name>/...``

This only rewrites bundled **hook command** paths — the machine-executed
integration point. It does not rewrite path templates embedded in each
``SKILL.md``'s own prose; see the iterate spec's Out of Scope for why.

Dedup and collision rule (M1: "declares deduplication keys... and fail
policy instead of concatenating fourteen manifests"): after rewriting, two
hook entries for the same event are the same hook iff their rewritten
command strings are byte-identical (this naturally dedupes every
shared-referencing hook that today is registered near-identically across
~12 of the 14 plugins per ``shared/prompts/writing-plugin.md``'s own
convention, and naturally keeps every plugin-own hook distinct, since origin
is now part of the rewritten path). Two entries whose commands reference the
same target script (basename) on the same event but are NOT byte-identical
after rewriting are a real collision — raises :class:`BundleCollisionError`
rather than silently picking one, since Codex would otherwise get whichever
happened to sort first.

Usage:
    uv run shared/scripts/tools/build_codex_plugin.py \\
        --project-root . --out dist/codex-plugin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from codex_bundle_safety import (
    BUNDLE_NAME,
    UnsafeOutputPathError,
    refuse_foreign_marketplace,
    refuse_unsafe_output_path,
)
from codex_hook_inventory import BundleCollisionError, build_hook_inventory

# Applied to every copied source tree (skills, per-origin scripts, and
# shared/), not only shared/: a developer's local __pycache__ under any
# plugin's scripts/ is machine/run-local generated content, not source, and
# its presence would otherwise make AC4's byte-identical-rebuild guarantee
# depend on whether the last person to build had compiled bytecode lying
# around (found building against the real 14-plugin tree).
SOURCE_EXCLUDE_DIRS = {"tests", "__pycache__", ".venv", ".git", ".ruff_cache", ".mypy_cache", ".pytest_cache"}

__all__ = [
    "BundleCollisionError",
    "UnsafeOutputPathError",
    "build_hook_inventory",
    "BuildResult",
    "discover_plugins",
    "build_bundle",
    "main",
]


@dataclass
class BuildResult:
    skill_count: int
    plugin_count: int
    manifest_path: Path
    bundle_dir: Path
    file_hashes: dict[str, str] = field(default_factory=dict)


def discover_plugins(project_root: Path) -> list[Path]:
    plugins_dir = project_root / "plugins"
    if not plugins_dir.is_dir():
        return []
    return sorted(
        p for p in plugins_dir.iterdir()
        if p.is_dir() and (p / ".claude-plugin" / "plugin.json").is_file()
    )


def _copy_tree(src: Path, dst: Path, *, exclude_dirnames: set[str] | None = None) -> None:
    exclude_dirnames = exclude_dirnames or set()

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        return {n for n in names if n in exclude_dirnames}

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)


def _sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root)).replace("\\", "/")] = _sha256_of_file(path)
    return hashes


def build_bundle(*, project_root: Path, out_dir: Path) -> BuildResult:
    project_root = Path(project_root).resolve()
    out_dir = Path(out_dir).resolve()
    refuse_unsafe_output_path(project_root=project_root, out_dir=out_dir)
    refuse_foreign_marketplace(out_dir.parent / ".agents" / "plugins" / "marketplace.json")
    marketplace_meta = json.loads(
        (project_root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    version = marketplace_meta.get("version", "0.0.0")

    plugin_dirs = discover_plugins(project_root)
    hook_inventory = build_hook_inventory(plugin_dirs)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    # The bundle marker is written FIRST, before any copying, not last: a
    # build interrupted partway through (Ctrl-C, disk full, a file an
    # editor/AV holds open) would otherwise leave a non-empty, marker-less
    # out_dir that refuse_unsafe_output_path then refuses to touch on retry
    # — "did not create" would be wrong on the facts, since this tool DID
    # create it (code-review round, 2026-09-20). Both `version` and
    # `hook_inventory` are already known at this point, so there is nothing
    # to defer.
    codex_plugin_dir = out_dir / ".codex-plugin"
    codex_plugin_dir.mkdir()
    plugin_manifest = {
        "name": BUNDLE_NAME,
        "version": version,
        "description": "Shipwright SDLC framework — every phase skill in one installable plugin.",
        "skills": "./skills/",
        "hooks": hook_inventory,
    }
    (codex_plugin_dir / "plugin.json").write_text(
        json.dumps(plugin_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    skills_root = out_dir / "skills"
    skills_root.mkdir()
    skill_count = 0
    skill_origins: dict[str, str] = {}
    for plugin_dir in plugin_dirs:
        src_skills = plugin_dir / "skills"
        if not src_skills.is_dir():
            continue
        for skill_dir in sorted(src_skills.iterdir()):
            if not skill_dir.is_dir():
                continue
            # Skill folders flatten into one shared namespace (docstring
            # above), so a same-named skill in two plugins would otherwise
            # silently overwrite one with the other via _copy_tree's rmtree
            # — refuse rather than lose content, mirroring the hook-merge
            # module's collision-refusal philosophy (Internal Plan Review).
            if skill_dir.name in skill_origins:
                raise BundleCollisionError(
                    f"Skill {skill_dir.name!r} is declared by both "
                    f"{skill_origins[skill_dir.name]!r} and {plugin_dir.name!r} — "
                    "flattening would silently discard one"
                )
            skill_origins[skill_dir.name] = plugin_dir.name
            _copy_tree(skill_dir, skills_root / skill_dir.name, exclude_dirnames=SOURCE_EXCLUDE_DIRS)
            skill_count += 1

    origin_root = out_dir / "origin"
    for plugin_dir in plugin_dirs:
        src_scripts = plugin_dir / "scripts"
        if src_scripts.is_dir():
            _copy_tree(
                src_scripts, origin_root / plugin_dir.name / "scripts",
                exclude_dirnames=SOURCE_EXCLUDE_DIRS,
            )

    shared_src = project_root / "shared"
    if shared_src.is_dir():
        _copy_tree(shared_src, out_dir / "shared", exclude_dirnames=SOURCE_EXCLUDE_DIRS)

    file_hashes = _hash_tree(out_dir)
    manifest_path = out_dir / "BUILD_MANIFEST.json"
    manifest_path.write_text(
        json.dumps({"version": version, "files": file_hashes}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    marketplace_dir = out_dir.parent / ".agents" / "plugins"
    marketplace_dir.mkdir(parents=True, exist_ok=True)
    (marketplace_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": BUNDLE_NAME,
                "interface": {"displayName": "Shipwright"},
                "plugins": [
                    {
                        "name": BUNDLE_NAME,
                        "source": {"source": "local", "path": f"./{out_dir.name}"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Developer Tools",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return BuildResult(
        skill_count=skill_count,
        plugin_count=len(plugin_dirs),
        manifest_path=manifest_path,
        bundle_dir=out_dir,
        file_hashes=file_hashes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Monorepo root (default: cwd)")
    parser.add_argument("--out", required=True, help="Build-output directory for the bundle")
    args = parser.parse_args(argv)

    try:
        result = build_bundle(project_root=Path(args.project_root), out_dir=Path(args.out))
    except (BundleCollisionError, UnsafeOutputPathError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Built Codex plugin bundle: {result.plugin_count} source plugins, "
        f"{result.skill_count} skills -> {result.bundle_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
