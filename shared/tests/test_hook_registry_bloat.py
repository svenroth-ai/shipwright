"""Meta-test: every plugin's hooks.json registers both bloat hooks.

Drift-protection per ADR-044 — registry → disk requires BOTH directions:
- Forward: every plugin lists check_file_size.py (PostToolUse on
  Write|Edit) AND bloat_gate_on_stop.py (Stop).
- Reverse: every plugin's hooks.json points at a shared-scripts path
  that resolves to a real file (no orphan registrations).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGINS_DIR = _REPO_ROOT / "plugins"
_SHARED_HOOKS = _REPO_ROOT / "shared" / "scripts" / "hooks"


def _all_plugins_with_hooks_json() -> list[Path]:
    return sorted(p for p in _PLUGINS_DIR.iterdir()
                  if (p / "hooks" / "hooks.json").is_file())


def _load(plugin_dir: Path) -> dict:
    return json.loads((plugin_dir / "hooks" / "hooks.json").read_text(encoding="utf-8"))


def _collect_commands(hook_block: list, event: str) -> list[str]:
    """Flatten ``hooks.json[event]`` into a list of command strings."""
    out: list[str] = []
    for matcher_block in hook_block:
        if not isinstance(matcher_block, dict):
            continue
        for hook in matcher_block.get("hooks", []):
            cmd = hook.get("command", "")
            if isinstance(cmd, str):
                out.append(cmd)
    return out


@pytest.mark.parametrize(
    "plugin", _all_plugins_with_hooks_json(), ids=lambda p: p.name,
)
def test_plugin_registers_check_file_size_in_post_tool_use(plugin: Path):
    doc = _load(plugin)
    commands = _collect_commands(doc.get("hooks", {}).get("PostToolUse", []), "PostToolUse")
    assert any("check_file_size.py" in c for c in commands), (
        f"{plugin.name}/hooks/hooks.json missing PostToolUse: check_file_size.py"
    )


@pytest.mark.parametrize(
    "plugin", _all_plugins_with_hooks_json(), ids=lambda p: p.name,
)
def test_plugin_registers_bloat_gate_in_stop(plugin: Path):
    doc = _load(plugin)
    commands = _collect_commands(doc.get("hooks", {}).get("Stop", []), "Stop")
    assert any("bloat_gate_on_stop.py" in c for c in commands), (
        f"{plugin.name}/hooks/hooks.json missing Stop: bloat_gate_on_stop.py"
    )


@pytest.mark.parametrize(
    "plugin", _all_plugins_with_hooks_json(), ids=lambda p: p.name,
)
def test_post_tool_use_check_file_size_uses_write_edit_matcher(plugin: Path):
    """The PostToolUse entry must scope to Write|Edit to avoid firing on every tool."""
    doc = _load(plugin)
    found = False
    for matcher_block in doc.get("hooks", {}).get("PostToolUse", []):
        if not isinstance(matcher_block, dict):
            continue
        matcher = matcher_block.get("matcher", "")
        for hook in matcher_block.get("hooks", []):
            cmd = hook.get("command", "")
            if "check_file_size.py" in cmd:
                assert "Write" in matcher and "Edit" in matcher, (
                    f"{plugin.name}: check_file_size.py matcher must include Write|Edit, "
                    f"got {matcher!r}"
                )
                found = True
    assert found


def test_referenced_scripts_exist():
    """Reverse direction: both shared scripts referenced actually exist on disk."""
    assert (_SHARED_HOOKS / "check_file_size.py").is_file()
    assert (_SHARED_HOOKS / "bloat_gate_on_stop.py").is_file()


@pytest.mark.parametrize(
    "plugin", _all_plugins_with_hooks_json(), ids=lambda p: p.name,
)
def test_hook_commands_quote_plugin_root_placeholder(plugin: Path):
    """ADR-020: every uv-run command quotes the ${CLAUDE_PLUGIN_ROOT} placeholder."""
    doc = _load(plugin)
    for event in ("PostToolUse", "Stop"):
        for matcher_block in doc.get("hooks", {}).get(event, []):
            if not isinstance(matcher_block, dict):
                continue
            for hook in matcher_block.get("hooks", []):
                cmd = hook.get("command", "")
                if "${CLAUDE_PLUGIN_ROOT}" in cmd and "bloat" in cmd or "check_file_size" in cmd:
                    assert '"${CLAUDE_PLUGIN_ROOT}' in cmd or "'${CLAUDE_PLUGIN_ROOT}" in cmd, (
                        f"{plugin.name} hook command missing quoted plugin-root: {cmd!r}"
                    )
