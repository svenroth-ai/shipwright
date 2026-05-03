"""Install the suggest_iterate UserPromptSubmit hook idempotently.

Mirrors the pattern from plugins/shipwright-project/skills/project/SKILL.md
Step 7. Safe to call repeatedly — adds the hook entry if missing,
upgrades any of the known legacy forms in place to the canonical form
if present, and is a true no-op when the canonical form is already
installed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Canonical hook command. Two pieces matter and were both added because
# of distinct production failures:
#
#   1. Wrap the path in double quotes. Target projects on paths
#      containing spaces (OneDrive-synced "AI Backup - Documents",
#      "Program Files", Windows usernames with spaces) had the shell
#      word-split the unquoted ${CLAUDE_PLUGIN_ROOT} expansion; uv
#      exited non-zero with "Failed to spawn"; per Claude Code's hook
#      contract a non-zero UserPromptSubmit blocks the user prompt
#      entirely. (See ADR-020.)
#
#   2. Pass --no-project to uv. Without it, uv tries to resolve a
#      project context from the target project's CWD, and a corrupt
#      project .venv stalls the hook on resolution — same effect:
#      blocked prompts. (Same ADR.)
_HOOK_COMMAND = (
    'uv run --no-project '
    '"${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"'
)

# Legacy command strings that earlier versions of this installer (or the
# documented copy-paste snippet in shipwright-{project,run} SKILL.md)
# wrote into the wild. Recognized so re-running install upgrades them
# to the canonical form. The set is closed over the cross product of
# {with, without --no-project} × {quoted, unquoted} ×
# {${CLAUDE_PLUGIN_ROOT}, {plugin_root}}, minus _HOOK_COMMAND itself.
_HOOK_ALIASES = {
    _HOOK_COMMAND,
    # Original buggy forms (unquoted, no --no-project):
    "uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py",
    "uv run {plugin_root}/../../shared/scripts/hooks/suggest_iterate.py",
    # Half-applied patches (--no-project but still unquoted):
    "uv run --no-project ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py",
    "uv run --no-project {plugin_root}/../../shared/scripts/hooks/suggest_iterate.py",
    # Quoted but missing --no-project:
    'uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"',
    'uv run "{plugin_root}/../../shared/scripts/hooks/suggest_iterate.py"',
}


def _build_canonical_entry() -> dict[str, Any]:
    """Build a fresh canonical UserPromptSubmit entry (matcher-group
    Shape B). The outer dict is a matcher group; the actual command
    sits in its inner ``hooks`` array. UserPromptSubmit takes no tool
    matcher, so we omit the ``matcher`` key — see ADR-019."""
    return {"hooks": [{"type": "command", "command": _HOOK_COMMAND}]}


def install_suggest_iterate_hook(settings_path: Path) -> dict[str, Any]:
    """Merge the suggest_iterate UserPromptSubmit hook into settings.json.

    Behavior:
      - File missing: write a new file with the canonical Shape B entry.
      - File present, hook absent: append a new Shape B entry.
      - File present, hook in any legacy form (Shape A bare-command, OR
        Shape B with a legacy command literal): rewrite that entry in
        place to the canonical Shape B + canonical command. Both the
        Shape AND the command may be wrong; both must be fixed, or the
        next user prompt will still be blocked (Claude Code rejects
        Shape A; unquoted commands break on paths with spaces). See
        ADR-019 + ADR-020.
      - File present, hook already canonical (Shape B + canonical
        command): true no-op, do not rewrite the file.

    Returns a status dict::

        {
          "installed": bool,         # True iff a NEW row was appended
          "already_present": bool,   # True iff a matching row existed
          "upgraded": bool,          # True iff a legacy row was rewritten
                                     #   (covers Shape A → Shape B and/or
                                     #   legacy command → canonical)
          "settings_path": str,
          "created_file": bool,
        }
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

    for idx, entry in enumerate(ups):
        if not isinstance(entry, dict):
            continue

        # Shape A (legacy, pre-ADR-019): bare {"type":"command","command":"..."}.
        # Claude Code rejects this format; if we find one matching any
        # known alias, we replace the entire entry with a canonical
        # Shape B entry. That counts as an upgrade regardless of
        # whether the command literal was canonical or legacy — the
        # shape itself was wrong.
        if "command" in entry and "hooks" not in entry:
            if entry.get("command") in _HOOK_ALIASES:
                ups[idx] = _build_canonical_entry()
                settings_path.write_text(
                    json.dumps(data, indent=2) + "\n", encoding="utf-8"
                )
                return {
                    "installed": False,
                    "already_present": True,
                    "upgraded": True,
                    "settings_path": str(settings_path),
                    "created_file": False,
                }
            # Shape A but unrelated command — leave alone.
            continue

        # Shape B (canonical): {"hooks":[{"type":"command","command":"..."}]}.
        nested = entry.get("hooks")
        if not isinstance(nested, list):
            continue
        for sub in nested:
            if not isinstance(sub, dict):
                continue
            sub_cmd = sub.get("command")
            if sub_cmd in _HOOK_ALIASES:
                if sub_cmd != _HOOK_COMMAND:
                    sub["command"] = _HOOK_COMMAND
                    settings_path.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
                    return {
                        "installed": False,
                        "already_present": True,
                        "upgraded": True,
                        "settings_path": str(settings_path),
                        "created_file": False,
                    }
                # Already canonical — true no-op.
                return {
                    "installed": False,
                    "already_present": True,
                    "upgraded": False,
                    "settings_path": str(settings_path),
                    "created_file": False,
                }

    # No existing entry matched — append the canonical Shape B form.
    ups.append(_build_canonical_entry())
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "installed": True,
        "already_present": False,
        "upgraded": False,
        "settings_path": str(settings_path),
        "created_file": created,
    }
