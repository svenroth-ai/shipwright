"""Drift protection for the vendored ``ensure_shared_cache`` SessionStart hook.

The self-heal bootstrap cannot live in ``shared/`` and be imported at runtime —
it exists precisely to repair a missing ``shared/``. So the canonical source at
``shared/templates/hooks/ensure_shared_cache.py`` is **vendored byte-identically**
into every hook-bearing plugin's ``scripts/hooks/``. This is the only delivery a
plain ``claude plugin install`` guarantees (a plugin-local file), so it is load-
bearing that the copies never drift and are actually wired into SessionStart.

Bidirectional drift protection (the Registry-driven-SSoT rule):
  - forward  — every hook-bearing plugin (any ``hooks.json`` referencing
    ``../../shared``) carries a copy identical to the canonical AND registers it
    as the sole SessionStart command wrapping every cache-dependent target;
  - reverse  — every ``plugins/*/scripts/hooks/ensure_shared_cache.py`` on disk
    belongs to a hook-bearing plugin (no orphan copy) and matches the canonical.

Comparison is EOL-normalised: the gate is on content, not on a platform's / git
config's line-ending convention.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_VENDOR_REL = ("scripts", "hooks", "ensure_shared_cache.py")
_LOCK_CANONICAL = _CANONICAL.with_name("cache_repair_lock.py")
_LOCK_VENDOR_REL = ("scripts", "hooks", "cache_repair_lock.py")
_GUARD_CANONICAL = _CANONICAL.with_name("run_if_cache_ready.py")
_GUARD_VENDOR_REL = ("scripts", "hooks", "run_if_cache_ready.py")
_COMMON_TARGETS = (
    "capture_session_id.py",
    "check_artifact_drift.py",
    "session_start_using_shipwright.py",
)
_EXPECTED_TARGETS = {
    "shipwright-adopt": _COMMON_TARGETS,
    "shipwright-build": (
        "capture_session_id.py", "check_drift.py",
        "check_artifact_drift.py", "session_start_using_shipwright.py",
    ),
    "shipwright-changelog": _COMMON_TARGETS,
    "shipwright-compliance": _COMMON_TARGETS,
    "shipwright-deploy": _COMMON_TARGETS,
    "shipwright-design": _COMMON_TARGETS,
    "shipwright-iterate": (
        "capture_session_id.py", "check_drift.py", "check_artifact_drift.py",
        "import_github_findings.py", "session_start_using_shipwright.py",
    ),
    "shipwright-plan": _COMMON_TARGETS,
    "shipwright-project": _COMMON_TARGETS,
    "shipwright-run": _COMMON_TARGETS,
    "shipwright-security": (
        "capture_session_id.py", "check_drift.py",
        "check_artifact_drift.py", "session_start_using_shipwright.py",
    ),
    "shipwright-test": _COMMON_TARGETS,
}


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def _command_tokens(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []
    return [token.replace("\\", "/") for token in tokens]


def _script_tokens(command: str) -> list[str]:
    return [token for token in _command_tokens(command)
            if token.replace("\\", "/").endswith((".py", ".sh"))]


def _script_names(command: str) -> list[str]:
    return [token.rsplit("/", 1)[-1] for token in _script_tokens(command)]


def _is_cache_guarded(command: str) -> bool:
    tokens = _command_tokens(command)
    scripts = _script_names(command)
    return (
        len(tokens) >= 4
        and tokens[:3] == [
            "uv",
            "run",
            "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/run_if_cache_ready.py",
        ]
        and len(scripts) == len(tokens) - 2
        and all(name not in {"run_if_cache_ready.py", "ensure_shared_cache.py"}
                for name in scripts[1:])
    )


def _has_exact_targets(plugin_name: str, command: str) -> bool:
    prefix = "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/"
    expected = [prefix + name for name in _EXPECTED_TARGETS.get(plugin_name, ())]
    return _script_tokens(command)[1:] == expected


def _session_start_commands(data: dict) -> list[str] | None:
    groups = data.get("hooks", {}).get("SessionStart")
    if not isinstance(groups, list) or len(groups) != 1:
        return None
    hooks = groups[0].get("hooks")
    if not isinstance(hooks, list):
        return None
    return [hook.get("command", "") for hook in hooks]


def _hook_bearing_plugins() -> list[Path]:
    """Every plugin whose hooks.json references the ``../../shared`` delivery."""
    out = []
    for hj in sorted((_REPO / "plugins").glob("*/hooks/hooks.json")):
        if "../../shared" in hj.read_text(encoding="utf-8"):
            out.append(hj.parent.parent)  # .../plugins/<plugin>
    return out


def test_canonical_source_exists():
    assert _CANONICAL.is_file(), f"canonical bootstrap missing at {_CANONICAL}"
    text = _CANONICAL.read_text(encoding="utf-8")
    assert "self-heal" in text.lower()
    assert len(text.splitlines()) > 20


def test_hook_bearing_set_is_discovered():
    # Sanity: the discovery must actually find plugins, else the gate no-ops.
    assert len(_hook_bearing_plugins()) >= 10


def test_forward_every_hook_bearing_plugin_has_identical_copy():
    canon = _norm(_CANONICAL.read_bytes())
    missing, drifted = [], []
    for plugin in _hook_bearing_plugins():
        copy = plugin.joinpath(*_VENDOR_REL)
        if not copy.is_file():
            missing.append(plugin.name)
        elif _norm(copy.read_bytes()) != canon:
            drifted.append(plugin.name)
    assert not missing, (
        "hook-bearing plugins missing the vendored ensure_shared_cache bootstrap: "
        f"{missing} — copy shared/templates/hooks/ensure_shared_cache.py into each "
        "plugin's scripts/hooks/"
    )
    assert not drifted, (
        f"vendored ensure_shared_cache drifted from the canonical: {drifted} — "
        "re-vendor shared/templates/hooks/ensure_shared_cache.py to all copies"
    )


def test_forward_every_hook_bearing_plugin_has_identical_lock_helper():
    canon = _norm(_LOCK_CANONICAL.read_bytes())
    offenders = []
    for plugin in _hook_bearing_plugins():
        copy = plugin.joinpath(*_LOCK_VENDOR_REL)
        if not copy.is_file() or _norm(copy.read_bytes()) != canon:
            offenders.append(plugin.name)
    assert not offenders, f"missing or drifted cache_repair_lock helper: {offenders}"


def test_forward_every_hook_bearing_plugin_has_identical_ready_guard():
    canon = _norm(_GUARD_CANONICAL.read_bytes())
    offenders = []
    for plugin in _hook_bearing_plugins():
        copy = plugin.joinpath(*_GUARD_VENDOR_REL)
        if not copy.is_file() or _norm(copy.read_bytes()) != canon:
            offenders.append(plugin.name)
    assert not offenders, f"missing or drifted run_if_cache_ready guard: {offenders}"


def test_forward_registered_as_one_consolidated_session_start_command():
    offenders = []
    for plugin in _hook_bearing_plugins():
        data = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = _session_start_commands(data)
        if not (commands is not None and len(commands) == 1
                and _is_cache_guarded(commands[0])):
            offenders.append(plugin.name)
    assert not offenders, (
        "these hook-bearing plugins do not use one consolidated cache-ready "
        f"SessionStart command: {offenders}"
    )


def test_consolidated_command_preserves_exact_ordered_targets():
    plugins = _hook_bearing_plugins()
    assert {plugin.name for plugin in plugins} == set(_EXPECTED_TARGETS)
    offenders = []
    for plugin in plugins:
        data = json.loads((plugin / "hooks" / "hooks.json").read_text(
            encoding="utf-8",
        ))
        commands = _session_start_commands(data)
        if commands is None or len(commands) != 1 or not _has_exact_targets(
            plugin.name, commands[0],
        ):
            offenders.append(plugin.name)
    assert not offenders, f"changed SessionStart target set/order: {offenders}"


def test_exact_target_gate_rejects_omission_reorder_and_substitution():
    guard = 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/run_if_cache_ready.py"'
    prefix = "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/"
    expected = [prefix + name for name in _EXPECTED_TARGETS["shipwright-run"]]

    def command(targets: list[str]) -> str:
        return guard + " " + " ".join(f'"{target}"' for target in targets)

    assert _has_exact_targets("shipwright-run", command(expected))
    assert not _has_exact_targets("shipwright-run", command(expected[:-1]))
    assert not _has_exact_targets("shipwright-run", command(expected[::-1]))
    assert not _has_exact_targets(
        "shipwright-run", command([*expected[:-1], prefix + "other.py"]),
    )


def test_consolidated_command_has_no_unwrapped_siblings():
    offenders = []
    for plugin in _hook_bearing_plugins():
        data = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = _session_start_commands(data)
        if commands is None:
            offenders.append(f"{plugin.name}: SessionStart must have exactly one group")
            continue
        if commands is not None and len(commands) != 1:
            offenders.append(f"{plugin.name}: {commands}")
    assert not offenders, f"unguarded cache-dependent SessionStart hooks: {offenders}"


def test_cache_guard_shape_rejects_reversed_or_targetless_commands():
    guard = "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/run_if_cache_ready.py"
    target = "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/session_start_using_shipwright.py"

    assert _is_cache_guarded(f'uv run "{guard}" "{target}"')
    assert _is_cache_guarded(f'uv run "{guard}" "{target}" "{target}"')
    assert not _is_cache_guarded(f'uv run "{target}" "{guard}"')
    assert not _is_cache_guarded(f'uv run "{guard}"')
    assert not _is_cache_guarded(f'uv run echo "{guard}" "{target}"')
    assert not _is_cache_guarded(
        f'uv run "${{CLAUDE_PLUGIN_ROOT}}/other/run_if_cache_ready.py" "{target}"',
    )


def test_guard_shape_rejects_the_healer_as_a_target():
    guard = "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/run_if_cache_ready.py"
    healer = "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/ensure_shared_cache.py"
    target = "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/session_start_using_shipwright.py"

    assert _is_cache_guarded(f'uv run "{guard}" "{target}"')
    assert not _is_cache_guarded(f'uv run "{guard}" "{healer}"')


def test_session_start_shape_rejects_an_unguarded_second_group():
    healer = "uv run ensure_shared_cache.py"
    bypass = "uv run session_start_using_shipwright.py"
    data = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"command": healer}]},
                {"hooks": [{"command": bypass}]},
            ],
        },
    }

    assert _session_start_commands(data) is None


def test_reverse_no_orphan_vendored_copies():
    hb = {p.name for p in _hook_bearing_plugins()}
    canon = _norm(_CANONICAL.read_bytes())
    for copy in sorted((_REPO / "plugins").glob("*/scripts/hooks/ensure_shared_cache.py")):
        plugin_name = copy.parents[2].name  # scripts/hooks/<f> -> plugin dir
        assert plugin_name in hb, (
            f"orphan ensure_shared_cache copy in non-hook-bearing plugin "
            f"{plugin_name!r} — either wire that plugin's ../../shared hooks or "
            "remove the stray copy"
        )
        assert _norm(copy.read_bytes()) == canon, f"{plugin_name} copy drifted"

    lock_canon = _norm(_LOCK_CANONICAL.read_bytes())
    for copy in sorted((_REPO / "plugins").glob("*/scripts/hooks/cache_repair_lock.py")):
        plugin_name = copy.parents[2].name
        assert plugin_name in hb, f"orphan cache_repair_lock copy in {plugin_name}"
        assert _norm(copy.read_bytes()) == lock_canon, (
            f"{plugin_name} cache_repair_lock copy drifted"
        )


    guard_canon = _norm(_GUARD_CANONICAL.read_bytes())
    for copy in sorted((_REPO / "plugins").glob("*/scripts/hooks/run_if_cache_ready.py")):
        plugin_name = copy.parents[2].name
        assert plugin_name in hb, f"orphan run_if_cache_ready copy in {plugin_name}"
        assert _norm(copy.read_bytes()) == guard_canon, (
            f"{plugin_name} run_if_cache_ready copy drifted"
        )
