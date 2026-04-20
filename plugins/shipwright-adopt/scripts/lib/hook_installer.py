"""Install the suggest_iterate UserPromptSubmit hook idempotently.

Mirrors the pattern from plugins/shipwright-project/skills/project/SKILL.md
Step 7. Safe to call repeatedly — only adds the hook entry if not already
present in .claude/settings.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_HOOK_COMMAND = (
    "uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"
)
# Also handle legacy {plugin_root} syntax found in some older plugins
_HOOK_ALIASES = {
    _HOOK_COMMAND,
    "uv run {plugin_root}/../../shared/scripts/hooks/suggest_iterate.py",
}


def install_suggest_iterate_hook(settings_path: Path) -> dict[str, Any]:
    """Merge the suggest_iterate UserPromptSubmit hook into settings.json.

    Returns a status dict: {"installed": bool, "already_present": bool,
                             "settings_path": str, "created_file": bool}
    """
    created = False
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        created = True

    hooks = data.setdefault("hooks", {})
    ups = hooks.setdefault("UserPromptSubmit", [])

    # Check for an existing matching hook (by command)
    for entry in ups:
        if not isinstance(entry, dict):
            continue
        # Shape A: {"type":"command","command":"..."}
        if entry.get("command") in _HOOK_ALIASES:
            return {
                "installed": False,
                "already_present": True,
                "settings_path": str(settings_path),
                "created_file": False,
            }
        # Shape B (some Claude Code versions): {"hooks":[{"command":"..."}]}
        nested = entry.get("hooks")
        if isinstance(nested, list):
            for sub in nested:
                if isinstance(sub, dict) and sub.get("command") in _HOOK_ALIASES:
                    return {
                        "installed": False,
                        "already_present": True,
                        "settings_path": str(settings_path),
                        "created_file": False,
                    }

    # Append the hook in Claude Code's canonical shape
    ups.append({"type": "command", "command": _HOOK_COMMAND})

    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "installed": True,
        "already_present": False,
        "settings_path": str(settings_path),
        "created_file": created,
    }
