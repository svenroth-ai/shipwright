"""Regression test for ADR-022: every command string in
plugins/*/hooks/hooks.json that references ${CLAUDE_PLUGIN_ROOT} must
wrap the placeholder + path in double quotes.

Prevents the failure mode where Claude Code expands
${CLAUDE_PLUGIN_ROOT} to a path containing spaces (e.g. Windows username
"John Doe") and the shell word-splits the resulting command, producing
a non-zero hook exit that blocks SessionStart / Stop / PreToolUse hooks
and silently breaks the SDLC pipeline for that user.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_GLOB = "plugins/*/hooks/hooks.json"


def _collect_command_strings(node: object) -> list[str]:
    """Walk an arbitrary JSON tree and yield every value whose key is
    "command" — these are the strings shell-executed by Claude Code."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_collect_command_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_command_strings(item))
    return found


def _hook_files() -> list[Path]:
    files = sorted(REPO_ROOT.glob(PLUGINS_GLOB))
    assert files, (
        f"no hooks.json files found under {PLUGINS_GLOB}; test fixture "
        f"is wrong or repo layout changed"
    )
    return files


# Match an UNQUOTED reference to ${CLAUDE_PLUGIN_ROOT} — i.e. one whose
# preceding character is NOT a double quote. After json.loads() parses
# hooks.json, the JSON-escaped \" sequences become literal " characters
# in the Python string, so the lookbehind targets the bare quote (not
# the escaped form).
_UNQUOTED_PLUGIN_ROOT = re.compile(
    r'(?<!")\$\{CLAUDE_PLUGIN_ROOT\}(?:/[^\s"\\]+)?'
)


@pytest.mark.parametrize("hooks_path", _hook_files(), ids=lambda p: p.parent.parent.name)
def test_hooks_json_quotes_plugin_root_path(hooks_path: Path) -> None:
    """AC-1 + AC-3 (ADR-022): every ``command`` value in this hooks.json
    that references ${CLAUDE_PLUGIN_ROOT} must wrap the placeholder +
    path in escaped double quotes. Without quoting, the shell splits
    the command on spaces in the resolved path and the hook fails on
    Windows usernames containing spaces — which silently breaks the
    SDLC pipeline for that user.
    """
    raw = hooks_path.read_text(encoding="utf-8")
    config = json.loads(raw)
    commands = _collect_command_strings(config)
    assert commands, f"{hooks_path} has no hook commands — fixture broken?"

    offenders: list[str] = []
    for cmd in commands:
        if "${CLAUDE_PLUGIN_ROOT}" not in cmd:
            continue  # No placeholder, no quoting concern.
        if _UNQUOTED_PLUGIN_ROOT.search(cmd):
            offenders.append(cmd)

    assert not offenders, (
        f"{hooks_path.relative_to(REPO_ROOT)}: {len(offenders)} hook "
        f"command(s) embed ${{CLAUDE_PLUGIN_ROOT}} unquoted; on Windows "
        f"usernames containing spaces the shell will word-split the "
        f"resolved path and the hook will exit non-zero, blocking the "
        f"SDLC event. Wrap in escaped double quotes:\n"
        + "\n".join(f"    {c}" for c in offenders)
    )


def test_all_hooks_json_files_parse_as_valid_json() -> None:
    """AC-2: regex-based sweeps must not corrupt JSON syntax."""
    for hooks_path in _hook_files():
        try:
            json.loads(hooks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"{hooks_path.relative_to(REPO_ROOT)} is not valid JSON: {exc}"
            )
