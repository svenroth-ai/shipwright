"""Regression test for ADR-039: every plugins/*/hooks/hooks.json must
wrap its event-name dict under a top-level "hooks" key.

Required by Claude Code 2.1.132+. Without the wrapper the harness rejects
the plugin with `Hook load failed: expected record, received undefined
at path ["hooks"]` and NO hooks fire — silently breaks the SDLC pipeline
for every user on the supported Claude Code floor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_GLOB = "plugins/*/hooks/hooks.json"

# The set of Claude Code event names that currently appear in Shipwright
# plugin hooks. New events Claude Code introduces would just need adding
# here — until then, anything outside this set in the wrapper is a typo
# or a forgotten unwrap.
KNOWN_EVENT_NAMES = frozenset(
    {
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "PreToolUse",
        "PostToolUse",
        "SubagentStop",
    }
)


def _hook_files() -> list[Path]:
    files = sorted(REPO_ROOT.glob(PLUGINS_GLOB))
    assert files, (
        f"no hooks.json files found under {PLUGINS_GLOB}; test fixture "
        f"is wrong or repo layout changed"
    )
    return files


@pytest.mark.parametrize("hooks_path", _hook_files(), ids=lambda p: p.parent.parent.name)
def test_hooks_json_has_top_level_hooks_wrapper(hooks_path: Path) -> None:
    """AC-1 (ADR-039): the file's top-level value MUST be an object with a
    single ``hooks`` key whose value is an object (not an array) keyed by
    Claude Code event names. Any other shape — including the legacy
    pre-2.1.132 shape with event names at the document root — is a
    plugin-load failure under Claude Code 2.1.132+.
    """
    raw = hooks_path.read_text(encoding="utf-8")
    config = json.loads(raw)

    rel = hooks_path.relative_to(REPO_ROOT)

    assert isinstance(config, dict), (
        f"{rel}: top-level value is {type(config).__name__}, expected dict"
    )

    assert "hooks" in config, (
        f"{rel}: missing top-level 'hooks' key. Claude Code 2.1.132+ "
        f"rejects this shape with 'expected record, received undefined "
        f"at path [\"hooks\"]'. Wrap the event-name dict under "
        f'`{{ "hooks": {{ ... }} }}`.'
    )

    inner = config["hooks"]
    assert isinstance(inner, dict), (
        f"{rel}: 'hooks' value is {type(inner).__name__}, expected dict "
        f"(event-name → event-config-list)"
    )
    assert not isinstance(inner, list), (
        f"{rel}: 'hooks' value is a list — must be a dict keyed by event names"
    )

    # Every key under .hooks must be a known Claude Code event name.
    # If a new event ships, add it to KNOWN_EVENT_NAMES above with a PR.
    unknown = sorted(set(inner.keys()) - KNOWN_EVENT_NAMES)
    assert not unknown, (
        f"{rel}: unknown event name(s) under 'hooks': {unknown}. "
        f"Either typo, or Claude Code introduced a new event — update "
        f"KNOWN_EVENT_NAMES in this test file."
    )


def test_no_hooks_json_uses_legacy_top_level_shape() -> None:
    """AC-1 negative form: explicitly catch the pre-2.1.132 shape where
    event names sit at the JSON document root with no wrapper. This is
    redundant with the parametrized check above but produces a single
    clear error message that names every offender at once."""
    offenders: list[str] = []
    for hooks_path in _hook_files():
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            continue
        # Legacy shape iff at least one event name is at the top level
        # AND there is no 'hooks' key at all.
        if "hooks" in config:
            continue
        if any(k in KNOWN_EVENT_NAMES for k in config.keys()):
            offenders.append(str(hooks_path.relative_to(REPO_ROOT)))

    assert not offenders, (
        "Legacy pre-2.1.132 hooks.json shape detected (event names at the "
        "document root with no top-level 'hooks' wrapper). Claude Code "
        "2.1.132+ rejects these on plugin load:\n"
        + "\n".join(f"    {p}" for p in offenders)
    )
