"""Shared fixture-tree builders for build_codex_plugin.py tests.

Not a test module itself (no ``test_`` prefix, so pytest does not collect
it) — split out so both `test_build_codex_plugin.py` (builder-level
concerns) and `test_codex_hook_merge.py` (hook-merge-semantics concerns)
can build the same small fake-plugin trees without duplicating the helpers
or growing past the 300-line source guideline.
"""

from __future__ import annotations

import json
from pathlib import Path

_SHARED_HOOK_CMD = 'uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/shared_hook.py"'


def write_plugin(
    root: Path,
    name: str,
    *,
    hooks: dict | None = None,
    skill_name: str | None = None,
    own_script: str | None = None,
) -> None:
    plugin_dir = root / "plugins" / name
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "description": f"{name} plugin"}),
        encoding="utf-8",
    )
    skill_name = skill_name or name.replace("shipwright-", "")
    skill_dir = plugin_dir / "skills" / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {skill_name}\n", encoding="utf-8")
    if hooks is not None:
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "hooks.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    if own_script:
        script_path = plugin_dir / "scripts" / "hooks" / own_script
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("print('hi')\n", encoding="utf-8")


def write_shared(root: Path) -> None:
    (root / "shared" / "scripts" / "hooks").mkdir(parents=True)
    (root / "shared" / "scripts" / "hooks" / "shared_hook.py").write_text(
        "print('shared')\n", encoding="utf-8"
    )
    (root / "shared" / "tests").mkdir(parents=True)
    (root / "shared" / "tests" / "test_should_be_excluded.py").write_text("", encoding="utf-8")
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "shipwright", "version": "9.9.9"}), encoding="utf-8"
    )
