"""Hook-merge-semantics tests for build_codex_plugin.py (M1).

Split out of test_build_codex_plugin.py (builder-level concerns: skill
discovery, shared bundling, byte-identical rebuild). These six tests
exercise `codex_hook_merge.build_hook_inventory` through the full
`build_bundle` entry point: exact-duplicate dedup, a genuine collision,
matcher-distinguished variants, and dispatcher-style trailing-argument
union (order-preservation + a genuine order conflict). Cross-plugin
ordering of DISTINCT hook entries within one bucket is covered separately
in test_codex_hook_merge_ordering.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from build_codex_plugin import BundleCollisionError, build_bundle  # noqa: E402

from _bundle_fixtures import _SHARED_HOOK_CMD, write_plugin, write_shared  # noqa: E402


def test_identical_shared_referencing_hook_dedupes_across_plugins(tmp_path):
    write_shared(tmp_path)
    hooks = {"Stop": [{"hooks": [{"type": "command", "command": _SHARED_HOOK_CMD}]}]}
    write_plugin(tmp_path, "shipwright-alpha", hooks=hooks)
    write_plugin(tmp_path, "shipwright-beta", hooks=hooks)

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    stop_commands = [
        h["command"]
        for group in manifest["hooks"]["hooks"]["Stop"]
        for h in group["hooks"]
    ]
    assert len(stop_commands) == 1
    assert stop_commands[0] == 'uv run "${CLAUDE_PLUGIN_ROOT}/shared/scripts/hooks/shared_hook.py"'


def test_conflicting_command_for_same_target_is_a_collision(tmp_path):
    """Two plugins both claim to register the *same* shared script on the
    same event, but with different flags — a real drift signal (M1: 'collision
    refusal when two definitions share a key but disagree'). Must not be
    silently resolved by picking one arbitrarily."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        hooks={"Stop": [{"hooks": [{"type": "command", "command": _SHARED_HOOK_CMD}]}]},
    )
    write_plugin(
        tmp_path,
        "shipwright-beta",
        hooks={
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'uv run --with pyyaml "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/shared_hook.py"',
                        }
                    ]
                }
            ]
        },
    )

    out_dir = tmp_path / "dist"
    try:
        build_bundle(project_root=tmp_path, out_dir=out_dir)
        raise AssertionError("expected BundleCollisionError")
    except BundleCollisionError as exc:
        assert "shared_hook.py" in str(exc)
        assert "Stop" in str(exc)


def test_matcher_distinguishes_same_script_different_flags(tmp_path):
    """Real repo shape: write-review-payload-on-stop.py is registered 3x
    under SubagentStop, once per reviewer matcher, each with a different
    --review-type flag. Must NOT collide — the matcher makes them different
    hooks entirely."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        hooks={
            "SubagentStop": [
                {
                    "matcher": "alpha:spec-reviewer",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/wrp.py" --review-type spec',
                        }
                    ],
                },
                {
                    "matcher": "alpha:code-reviewer",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/wrp.py" --review-type code',
                        }
                    ],
                },
            ]
        },
        own_script="wrp.py",
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)  # must not raise

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    commands = {
        h["command"]
        for group in manifest["hooks"]["hooks"]["SubagentStop"]
        for h in group["hooks"]
    }
    assert commands == {
        'uv run "${CLAUDE_PLUGIN_ROOT}/origin/shipwright-alpha/scripts/hooks/wrp.py" --review-type spec',
        'uv run "${CLAUDE_PLUGIN_ROOT}/origin/shipwright-alpha/scripts/hooks/wrp.py" --review-type code',
    }


def test_dispatcher_style_hook_unions_differing_trailing_shared_args(tmp_path):
    """Real repo shape: run_if_cache_ready.py (identical own-plugin script in
    every plugin) is invoked with a DIFFERENT list of trailing shared-script
    arguments per plugin (e.g. shipwright-iterate additionally passes
    import_github_findings.py). In the current Claude world every plugin's
    copy of this hook fires independently, so a session already gets the
    UNION of all these sub-scripts across all installed plugins — merging to
    one Codex hook must preserve that union, not silently pick one plugin's
    (shorter) argument list and drop what the others would have run."""
    write_shared(tmp_path)
    write_plugin(
        tmp_path,
        "shipwright-alpha",
        hooks={
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/run_if_cache_ready.py" '
                                '"${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/shared_hook.py"'
                            ),
                        }
                    ]
                }
            ]
        },
        own_script="run_if_cache_ready.py",
    )
    write_plugin(
        tmp_path,
        "shipwright-beta",
        hooks={
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/run_if_cache_ready.py" '
                                '"${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/shared_hook.py" '
                                '"${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/extra_hook.py"'
                            ),
                        }
                    ]
                }
            ]
        },
        own_script="run_if_cache_ready.py",
    )
    (tmp_path / "shared" / "scripts" / "hooks" / "extra_hook.py").write_text(
        "print('extra')\n", encoding="utf-8"
    )
    # Make both plugins' own copy of run_if_cache_ready.py byte-identical,
    # matching the real repo's own convention for this script.
    (tmp_path / "plugins" / "shipwright-beta" / "scripts" / "hooks" / "run_if_cache_ready.py").write_text(
        (tmp_path / "plugins" / "shipwright-alpha" / "scripts" / "hooks" / "run_if_cache_ready.py").read_text(),
        encoding="utf-8",
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)  # must not raise

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    session_start_commands = [
        h["command"]
        for group in manifest["hooks"]["hooks"]["SessionStart"]
        for h in group["hooks"]
    ]
    assert len(session_start_commands) == 1
    merged = session_start_commands[0]
    assert "shared_hook.py" in merged
    assert "extra_hook.py" in merged
    # Order matters: run_if_cache_ready.py runs its trailing sub-scripts
    # sequentially, and beta's own declared order is shared_hook.py THEN
    # extra_hook.py — the merge must reproduce that, not just include both.
    assert merged.index("shared_hook.py") < merged.index("extra_hook.py")


def test_dispatcher_union_inserts_a_missing_middle_script_at_its_declared_position(tmp_path):
    """Real bug found reviewing the merge against the actual 14-plugin
    monorepo: shipwright-adopt (processed first, alphabetically) lacks
    check_drift.py, contributing [capture_session_id, check_artifact_drift,
    session_start_using_shipwright]; shipwright-build (processed later)
    declares the FULL order [capture_session_id, check_drift,
    check_artifact_drift, session_start_using_shipwright]. A naive
    append-if-unseen union puts check_drift at the TAIL, after two scripts
    it was declared to run BEFORE. The merge must instead insert it at the
    position the fuller declaration implies."""
    write_shared(tmp_path)
    for name in ("capture_session_id", "check_artifact_drift", "session_start_using_shipwright", "check_drift"):
        (tmp_path / "shared" / "scripts" / "hooks" / f"{name}.py").write_text("print()\n", encoding="utf-8")

    def _cmd(*names: str) -> str:
        args = " ".join(f'"${{CLAUDE_PLUGIN_ROOT}}/../../shared/scripts/hooks/{n}.py"' for n in names)
        return f'uv run "${{CLAUDE_PLUGIN_ROOT}}/scripts/hooks/run_if_cache_ready.py" {args}'

    write_plugin(
        tmp_path, "shipwright-adopt",
        hooks={"SessionStart": [{"hooks": [{
            "type": "command",
            "command": _cmd("capture_session_id", "check_artifact_drift", "session_start_using_shipwright"),
        }]}]},
        own_script="run_if_cache_ready.py",
    )
    write_plugin(
        tmp_path, "shipwright-build",
        hooks={"SessionStart": [{"hooks": [{
            "type": "command",
            "command": _cmd("capture_session_id", "check_drift", "check_artifact_drift", "session_start_using_shipwright"),
        }]}]},
        own_script="run_if_cache_ready.py",
    )
    (tmp_path / "plugins" / "shipwright-build" / "scripts" / "hooks" / "run_if_cache_ready.py").write_text(
        (tmp_path / "plugins" / "shipwright-adopt" / "scripts" / "hooks" / "run_if_cache_ready.py").read_text(),
        encoding="utf-8",
    )

    out_dir = tmp_path / "dist"
    build_bundle(project_root=tmp_path, out_dir=out_dir)  # must not raise

    manifest = json.loads((out_dir / ".codex-plugin" / "plugin.json").read_text())
    commands = [h["command"] for g in manifest["hooks"]["hooks"]["SessionStart"] for h in g["hooks"]]
    assert len(commands) == 1
    merged = commands[0]
    positions = {
        name: merged.index(f"{name}.py")
        for name in ("capture_session_id", "check_drift", "check_artifact_drift", "session_start_using_shipwright")
    }
    assert positions["capture_session_id"] < positions["check_drift"] < positions["check_artifact_drift"] < positions["session_start_using_shipwright"]


def test_dispatcher_union_conflicting_declared_order_is_a_collision(tmp_path):
    """Two plugins declaring genuinely conflicting relative order for the
    same pair of trailing arguments must be refused, not silently resolved
    by picking whichever origin sorts first."""
    write_shared(tmp_path)
    for name in ("first_hook", "second_hook"):
        (tmp_path / "shared" / "scripts" / "hooks" / f"{name}.py").write_text("print()\n", encoding="utf-8")

    def _cmd(*names: str) -> str:
        args = " ".join(f'"${{CLAUDE_PLUGIN_ROOT}}/../../shared/scripts/hooks/{n}.py"' for n in names)
        return f'uv run "${{CLAUDE_PLUGIN_ROOT}}/scripts/hooks/run_if_cache_ready.py" {args}'

    write_plugin(
        tmp_path, "shipwright-alpha",
        hooks={"SessionStart": [{"hooks": [{
            "type": "command", "command": _cmd("first_hook", "second_hook"),
        }]}]},
        own_script="run_if_cache_ready.py",
    )
    write_plugin(
        tmp_path, "shipwright-beta",
        hooks={"SessionStart": [{"hooks": [{
            "type": "command", "command": _cmd("second_hook", "first_hook"),
        }]}]},
        own_script="run_if_cache_ready.py",
    )
    (tmp_path / "plugins" / "shipwright-beta" / "scripts" / "hooks" / "run_if_cache_ready.py").write_text(
        (tmp_path / "plugins" / "shipwright-alpha" / "scripts" / "hooks" / "run_if_cache_ready.py").read_text(),
        encoding="utf-8",
    )

    out_dir = tmp_path / "dist"
    try:
        build_bundle(project_root=tmp_path, out_dir=out_dir)
        raise AssertionError("expected BundleCollisionError")
    except BundleCollisionError as exc:
        assert "order" in str(exc)
