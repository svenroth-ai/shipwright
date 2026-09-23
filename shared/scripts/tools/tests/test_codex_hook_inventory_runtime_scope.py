"""Tests for runtime-scoped hook registration (R2): a plugin's
``hooks-codex/hooks.json`` feeds the Codex bundle's merged inventory but is
never read by Claude Code's own hook loader (``hooks/hooks.json`` only).

Split from `test_codex_hook_merge.py` (already at the 300-line guideline) --
this file owns only the Codex-only-manifest merge behavior; dedup/collision/
matcher/dispatcher-union semantics stay in that file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from build_codex_plugin import build_bundle  # noqa: E402

from _bundle_fixtures import write_plugin, write_shared  # noqa: E402

_GATE_CMD = 'uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/codex_pretooluse_gate.py"'


def test_codex_only_hook_reaches_the_built_inventory(tmp_path):
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        codex_only_hooks={
            "PreToolUse": [{"hooks": [{"type": "command", "command": _GATE_CMD}]}]
        },
        own_script="codex_pretooluse_gate.py",
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    pre_tool_use = manifest["hooks"]["hooks"]["PreToolUse"]
    assert len(pre_tool_use) == 1
    command = pre_tool_use[0]["hooks"][0]["command"]
    assert "origin/shipwright-alpha/scripts/hooks/codex_pretooluse_gate.py" in command


def test_codex_only_hook_never_appears_in_the_claude_visible_file(tmp_path):
    """The whole point of the split: a Codex-only entry must not exist
    anywhere Claude Code's own loader reads, or the "zero cost under Claude"
    property this registration exists for is false."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        codex_only_hooks={
            "PreToolUse": [{"hooks": [{"type": "command", "command": _GATE_CMD}]}]
        },
        own_script="codex_pretooluse_gate.py",
    )

    claude_hooks_file = tmp_path / "plugins" / "shipwright-alpha" / "hooks" / "hooks.json"
    assert not claude_hooks_file.exists()

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)
    # And the source tree still has no Claude-visible copy after the build.
    assert not claude_hooks_file.exists()


def test_codex_only_and_shared_hooks_on_the_same_event_both_survive(tmp_path):
    """Codex-only groups are additive, not a replacement for the shared
    ``hooks/hooks.json`` registration on the same event."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        hooks={
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/shared_gate.py"'
                            ),
                        }
                    ],
                }
            ]
        },
        codex_only_hooks={
            "PreToolUse": [{"hooks": [{"type": "command", "command": _GATE_CMD}]}]
        },
        own_script="shared_gate.py",
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    groups = manifest["hooks"]["hooks"]["PreToolUse"]
    matchers = {g.get("matcher") for g in groups}
    assert matchers == {"Bash", None}


def test_no_codex_only_manifest_is_a_no_op(tmp_path):
    """A plugin with no ``hooks-codex/hooks.json`` at all builds exactly as
    before -- this is an additive convention, not a required file."""
    write_shared(tmp_path)
    write_plugin(tmp_path, "shipwright-alpha")

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["hooks"]["hooks"] == {}
