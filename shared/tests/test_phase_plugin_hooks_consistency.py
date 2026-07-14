"""Consistency + drift guards for the shipped hooks.json manifests.

Two jobs, both registry-driven (the SSoT is the manifests on disk):

1. **Phase-plugin hook chain.** All 8 phase plugins must wire the SAME chain, so a
   future iterate can't add/remove a hook in one plugin and forget the others.

2. **No dangling registration (forward drift).** EVERY script referenced by EVERY
   shipped hooks.json must exist on disk. A manifest entry pointing at a deleted
   script breaks hook loading for the whole plugin — this is the guard that would
   have caught the multi-session removal missing a plugin.

Post-`iterate-2026-07-14-remove-multi-session`: the phase-session trio
(`phase_session_start` / `phase_user_prompt_validate` / `phase_session_stop`) is
DELETED. The phase plugins therefore no longer register those hooks, and — because
the validator was its only entry — no longer register the `UserPromptSubmit` event
at all. Phases are advanced by the master's in-conversation loop, not by hooks.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PHASE_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan",
    "shipwright-build", "shipwright-test", "shipwright-security",
    "shipwright-changelog", "shipwright-deploy",
]

ALL_PLUGINS = sorted(
    p.parent.parent.name
    for p in REPO_ROOT.glob("plugins/*/hooks/hooks.json")
)

# The engine deleted by iterate-2026-07-14-remove-multi-session. No manifest may
# reference these again — re-registering one would load a script that isn't there.
REMOVED_HOOKS = (
    "phase_session_start.py",
    "phase_user_prompt_validate.py",
    "phase_session_stop.py",
)


def _hook_commands(hook_block: list[dict]) -> list[str]:
    """Flatten one event's hook chain into a list of script basenames.

    Uses ``shlex.split`` so quoted commands like
    ``uv run "${CLAUDE_PLUGIN_ROOT}/.../foo.py"`` (the post-ADR-019/020 quoted-path
    form for Windows path-with-spaces safety) parse the same as plain unquoted ones.
    Both Windows ``\\`` and POSIX ``/`` separators are accepted; the basename is the
    final segment.
    """
    out: list[str] = []
    for entry in hook_block:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            try:
                tokens = shlex.split(cmd, posix=True)
            except ValueError:
                tokens = cmd.split()
            for token in tokens:
                last = token.replace("\\", "/").rsplit("/", 1)[-1]
                if last.endswith(".py") or last.endswith(".sh"):
                    out.append(last)
                    break
    return out


def _hook_script_paths(hook_block: list[dict], plugin: str) -> list[Path]:
    """Resolve every script a hook chain references to a real filesystem path.

    ``${CLAUDE_PLUGIN_ROOT}`` expands to ``plugins/<plugin>``; the shared hooks are
    reached from there via ``../../shared/...``.
    """
    plugin_root = REPO_ROOT / "plugins" / plugin
    out: list[Path] = []
    for entry in hook_block:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            try:
                tokens = shlex.split(cmd, posix=True)
            except ValueError:
                tokens = cmd.split()
            for token in tokens:
                norm = token.replace("\\", "/")
                if not (norm.endswith(".py") or norm.endswith(".sh")):
                    continue
                norm = norm.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root).replace("\\", "/"))
                out.append(Path(norm).resolve())
                break
    return out


def _load_hooks(plugin: str) -> dict:
    """Return the event-name → event-config-list mapping for a plugin.

    Claude Code 2.1.132+ requires the top-level value to wrap the event-name dict
    under a ``"hooks"`` key (ADR-039). The wrapper itself is asserted by
    ``test_hooks_json_wrapper.py``; here we just unwrap it.
    """
    path = REPO_ROOT / "plugins" / plugin / "hooks" / "hooks.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    inner = raw.get("hooks")
    if isinstance(inner, dict):
        return inner
    return raw


# --------------------------------------------------------------------------- #
# 1. Phase-plugin hook chain (post-removal shape)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_session_start_chain(plugin):
    """ensure_shared_cache runs FIRST (it heals ../../shared), capture_session_id
    before the hooks that need SHIPWRIGHT_SESSION_ID."""
    cmds = _hook_commands(_load_hooks(plugin).get("SessionStart") or [])
    assert cmds, f"{plugin}: no SessionStart hooks"
    assert cmds[0] == "ensure_shared_cache.py", (
        f"{plugin}: ensure_shared_cache.py must run FIRST so every later "
        f"../../shared/* hook resolves; got {cmds}"
    )
    assert "capture_session_id.py" in cmds, f"{plugin}: missing capture_session_id.py"
    assert "check_artifact_drift.py" in cmds, f"{plugin}: missing check_artifact_drift.py"
    assert cmds.index("check_artifact_drift.py") > cmds.index("capture_session_id.py"), (
        f"{plugin}: check_artifact_drift.py must come after capture_session_id.py"
    )


@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_no_user_prompt_submit_event(plugin):
    """The phase-claim validator was UserPromptSubmit's ONLY entry in the phase
    plugins, so the whole event is gone with it. A re-appearing event here means
    someone re-added a phase-claim block."""
    hooks = _load_hooks(plugin)
    assert "UserPromptSubmit" not in hooks, (
        f"{plugin}: UserPromptSubmit was emptied by the multi-session removal; "
        f"got {_hook_commands(hooks['UserPromptSubmit'])}"
    )


@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_stop_chain_audit_before_handoff(plugin):
    """The handoff must be generated AFTER the phase-quality audit, so the handoff
    reflects the audited state."""
    cmds = _hook_commands(_load_hooks(plugin).get("Stop") or [])
    assert "audit_phase_quality_on_stop.py" in cmds, f"{plugin}: missing audit_phase_quality_on_stop.py"
    assert "generate_handoff_on_stop.py" in cmds, f"{plugin}: missing generate_handoff_on_stop.py"
    assert cmds.index("audit_phase_quality_on_stop.py") < cmds.index("generate_handoff_on_stop.py"), (
        f"{plugin}: audit_phase_quality_on_stop.py must precede generate_handoff_on_stop.py"
    )


@pytest.mark.parametrize("plugin", ALL_PLUGINS)
def test_no_plugin_registers_a_removed_phase_session_hook(plugin):
    """Residue guard: the deleted multi-session engine must stay deleted."""
    hooks = _load_hooks(plugin)
    registered = [c for block in hooks.values() for c in _hook_commands(block)]
    for removed in REMOVED_HOOKS:
        assert removed not in registered, (
            f"{plugin}: registers {removed}, which was deleted with the "
            f"multi-session engine — the script does not exist and the whole "
            f"plugin's hook load would fail"
        )


# --------------------------------------------------------------------------- #
# 2. No dangling registration (forward drift, ALL plugins)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("plugin", ALL_PLUGINS)
def test_every_registered_hook_script_exists(plugin):
    """Every script referenced by a shipped hooks.json must exist on disk.

    Claude Code skips a plugin's hooks entirely when one fails to load, so a single
    stale registration silently disables the rest. This is the guard that makes a
    hook DELETION safe: forget one manifest and this fails loudly.
    """
    hooks = _load_hooks(plugin)
    missing: list[str] = []
    for event, block in hooks.items():
        for path in _hook_script_paths(block, plugin):
            if not path.exists():
                missing.append(f"{event}: {path}")
    assert not missing, (
        f"{plugin}/hooks/hooks.json references script(s) that do not exist:\n  "
        + "\n  ".join(missing)
    )


def test_all_plugins_discovered():
    """Sanity: the ALL_PLUGINS glob actually found the shipped manifests, so the
    parametrized guards above aren't vacuously passing over an empty list."""
    assert len(ALL_PLUGINS) >= 12, f"expected >=12 plugin manifests, found {ALL_PLUGINS}"
    for p in PHASE_PLUGINS:
        assert p in ALL_PLUGINS, f"phase plugin {p} has no hooks.json"
