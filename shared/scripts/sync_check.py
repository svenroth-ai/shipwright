#!/usr/bin/env python3
"""Check that all plugin references are in sync across the codebase.

Usage:
    uv run sync_check.py [--fix]

Checks:
1. Every plugins/ directory has an entry in marketplace.json
2. Every plugins/ directory has an entry in install.sh
3. README.md lists all plugins in the skills table
4. CLAUDE.md lists all plugins in the structure section
5. orchestrator.py PIPELINE_STEPS is a valid subset
6. Plugin versions match between plugin.json and marketplace.json

Exit codes:
    0 = all in sync
    1 = out of sync (details printed)
"""

import json
import re
import sys
from pathlib import Path


def get_repo_root() -> Path:
    """Find repo root (parent of shared/)."""
    return Path(__file__).resolve().parent.parent.parent


def get_actual_plugins(repo: Path) -> set[str]:
    """Get all plugin directory names."""
    plugins_dir = repo / "plugins"
    return {
        d.name
        for d in plugins_dir.iterdir()
        if d.is_dir() and (d / ".claude-plugin" / "plugin.json").exists()
    }


def check_marketplace(repo: Path, plugins: set[str]) -> list[str]:
    """Check marketplace.json has all plugins."""
    errors = []
    mp_path = repo / ".claude-plugin" / "marketplace.json"
    if not mp_path.exists():
        return ["marketplace.json not found"]

    data = json.loads(mp_path.read_text(encoding="utf-8"))
    mp_plugins = {p["name"] for p in data.get("plugins", [])}

    missing = plugins - mp_plugins
    extra = mp_plugins - plugins

    for p in sorted(missing):
        errors.append(f"marketplace.json: missing plugin '{p}'")
    for p in sorted(extra):
        errors.append(f"marketplace.json: extra plugin '{p}' (no directory)")

    return errors


def check_install_sh(repo: Path, plugins: set[str]) -> list[str]:
    """Check install.sh references all plugins."""
    errors = []
    install_path = repo / "scripts" / "install.sh"
    if not install_path.exists():
        return ["scripts/install.sh not found"]

    content = install_path.read_text(encoding="utf-8")
    for p in sorted(plugins):
        if p not in content:
            errors.append(f"install.sh: missing plugin-dir for '{p}'")

    return errors


def check_readme(repo: Path, plugins: set[str]) -> list[str]:
    """Check README.md mentions all plugins."""
    errors = []
    readme_path = repo / "README.md"
    if not readme_path.exists():
        return ["README.md not found"]

    content = readme_path.read_text(encoding="utf-8")
    for p in sorted(plugins):
        # Check for plugin name in any form (with or without shipwright- prefix)
        if p not in content:
            errors.append(f"README.md: plugin '{p}' not mentioned")

    return errors


def check_claude_md(repo: Path, plugins: set[str]) -> list[str]:
    """Check CLAUDE.md lists all plugins."""
    errors = []
    claude_path = repo / "CLAUDE.md"
    if not claude_path.exists():
        return ["CLAUDE.md not found"]

    content = claude_path.read_text(encoding="utf-8")
    for p in sorted(plugins):
        if p not in content:
            errors.append(f"CLAUDE.md: plugin '{p}' not listed in structure")

    return errors


def check_versions(repo: Path) -> list[str]:
    """Check version consistency between plugin.json and marketplace.json."""
    errors = []
    mp_path = repo / ".claude-plugin" / "marketplace.json"
    if not mp_path.exists():
        return []

    mp_data = json.loads(mp_path.read_text(encoding="utf-8"))
    mp_versions = {p["name"]: p.get("version", "") for p in mp_data.get("plugins", [])}

    plugins_dir = repo / "plugins"
    for plugin_dir in sorted(plugins_dir.iterdir()):
        pj = plugin_dir / ".claude-plugin" / "plugin.json"
        if not pj.exists():
            continue
        data = json.loads(pj.read_text(encoding="utf-8"))
        name = data.get("name", plugin_dir.name)
        version = data.get("version", "")

        if name in mp_versions and version != mp_versions[name]:
            errors.append(
                f"Version mismatch: {name} plugin.json={version} marketplace.json={mp_versions[name]}"
            )

    return errors


def check_orchestrator(repo: Path, plugins: set[str]) -> list[str]:
    """Check orchestrator PIPELINE_STEPS is a valid subset of plugins."""
    errors = []
    orch_path = repo / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"
    if not orch_path.exists():
        return []

    content = orch_path.read_text(encoding="utf-8")
    match = re.search(r'PIPELINE_STEPS\s*=\s*\[(.*?)\]', content, re.DOTALL)
    if not match:
        return ["orchestrator.py: PIPELINE_STEPS not found"]

    steps_raw = match.group(1)
    steps = re.findall(r'"(\w+)"', steps_raw)

    plugin_short_names = {p.replace("shipwright-", "") for p in plugins}
    for step in steps:
        if step not in plugin_short_names:
            errors.append(f"orchestrator.py: PIPELINE_STEPS has '{step}' but no shipwright-{step} plugin exists")

    return errors


def main() -> int:
    repo = get_repo_root()
    plugins = get_actual_plugins(repo)

    print(f"Found {len(plugins)} plugins: {', '.join(sorted(plugins))}")
    print()

    all_errors: list[str] = []

    checks = [
        ("Marketplace", check_marketplace(repo, plugins)),
        ("Install Script", check_install_sh(repo, plugins)),
        ("README", check_readme(repo, plugins)),
        ("CLAUDE.md", check_claude_md(repo, plugins)),
        ("Versions", check_versions(repo)),
        ("Orchestrator", check_orchestrator(repo, plugins)),
    ]

    for name, errors in checks:
        if errors:
            print(f"[FAIL] {name}")
            for e in errors:
                print(f"       - {e}")
            all_errors.extend(errors)
        else:
            print(f"[ OK ] {name}")

    print()
    if all_errors:
        print(f"Found {len(all_errors)} sync issue(s). Fix them before pushing.")
        return 1
    else:
        print("All plugin references are in sync.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
