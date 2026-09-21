"""Cross-plugin hook-ENTRY ordering (doubt-review round 2, 2026-09-20).

Split out of test_codex_hook_merge.py (at its 300-line cap) — that file
covers order-preservation WITHIN one dispatcher's trailing arguments
(`_merge_preserving_order` applied to `_HookGroupEntry.trailing_order`).
This file covers the same guarantee at the next level up: the ORDER of
distinct hook entries (different scripts) within one (event, matcher)
bucket, which `build_hook_inventory` previously did not order-preserve at
all — entries appeared in "whichever alphabetically-sorted plugin first
declared this script" order, unrelated to any one plugin's own intended
sequence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from build_codex_plugin import build_bundle  # noqa: E402

from _bundle_fixtures import write_plugin, write_shared  # noqa: E402

_SHARED = "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks"


def _cmd(script: str) -> dict:
    return {"type": "command", "command": f'uv run "{_SHARED}/{script}"'}


def test_hook_entries_preserve_a_fuller_origins_declared_order(tmp_path):
    """Real repo shape: audit_phase_quality_on_stop.py and
    audit_compliance_on_stop.py are registered as SEPARATE Stop hook entries
    in every plugin, but only shipwright-iterate also registers
    iterate_stop_finalize.py and aggregate_triage_on_stop.py, with a
    required order (finalize < phase_quality < compliance < aggregate,
    pinned by test_audit_compliance_on_stop_wiring.py). shipwright-adopt
    sorts alphabetically BEFORE shipwright-iterate; without order-preserving
    merge across entries (not just one dispatcher's trailing args), adopt's
    shorter declaration would insert first and silently invert iterate's
    required order in the merged bundle."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path, "shipwright-adopt",
        hooks={"Stop": [{"hooks": [
            _cmd("audit_phase_quality_on_stop.py"),
            _cmd("audit_compliance_on_stop.py"),
        ]}]},
    )
    write_plugin(
        tmp_path, "shipwright-iterate",
        hooks={"Stop": [{"hooks": [
            _cmd("iterate_stop_finalize.py"),
            _cmd("audit_phase_quality_on_stop.py"),
            _cmd("audit_compliance_on_stop.py"),
            _cmd("aggregate_triage_on_stop.py"),
        ]}]},
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    commands = [h["command"] for group in manifest["hooks"]["hooks"]["Stop"] for h in group["hooks"]]

    def idx(name: str) -> int:
        for i, c in enumerate(commands):
            if name in c:
                return i
        raise AssertionError(f"{name} not found in {commands}")

    assert (
        idx("iterate_stop_finalize.py")
        < idx("audit_phase_quality_on_stop.py")
        < idx("audit_compliance_on_stop.py")
        < idx("aggregate_triage_on_stop.py")
    )


def test_one_plugins_own_order_is_preserved_across_two_group_objects_in_one_bucket(tmp_path):
    """A single plugin can declare its Stop hooks as TWO separate hooks.json
    group objects that still share one (event, matcher) bucket. Its own
    cross-group order must be validated as one sequence — merging group by
    group would validate the second group only against itself and could
    silently head-insert it before the first (doubt-review round 3)."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path, "shipwright-solo",
        hooks={"Stop": [
            {"hooks": [_cmd("first_on_stop.py"), _cmd("second_on_stop.py")]},
            {"hooks": [_cmd("third_on_stop.py")]},
        ]},
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    commands = [h["command"] for group in manifest["hooks"]["hooks"]["Stop"] for h in group["hooks"]]

    def idx(name: str) -> int:
        for i, c in enumerate(commands):
            if name in c:
                return i
        raise AssertionError(f"{name} not found in {commands}")

    assert idx("first_on_stop.py") < idx("second_on_stop.py") < idx("third_on_stop.py")


def test_a_passthrough_only_bucket_does_not_raise(tmp_path):
    """A bucket whose only hooks are non-command (e.g. mcp_tool) never adds
    a rel_key to plugin_rel_keys, so it must still get a bucket_order entry
    at the point its group is first seen — otherwise the render loop's
    bucket_order[(event, matcher)] lookup raises KeyError (doubt-review
    round 4; every real Codex plugin observed in the field uses mcp_tool
    hooks, so this shape is expected in practice, not hypothetical)."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path, "shipwright-mcp-only",
        hooks={"Stop": [{"hooks": [{"type": "mcp_tool", "tool": "some_tool"}]}]},
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    hooks = [h for group in manifest["hooks"]["hooks"]["Stop"] for h in group["hooks"]]
    assert {"type": "mcp_tool", "tool": "some_tool"} in hooks
