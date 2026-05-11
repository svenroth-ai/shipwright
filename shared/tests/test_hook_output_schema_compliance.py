"""Hook-output schema compliance regression test.

Walks every ``plugins/*/hooks/hooks.json`` and asserts that the stdout
produced by each registered hook command conforms to the per-event JSON
shape documented at https://code.claude.com/docs/en/hooks.

Drift-protection for the Stop / SubagentStop schema fix landed
2026-05-10. Adding a new hook script with an invalid ``hookSpecificOutput``
shape will fail this test before reaching production.

Per-event allowed shapes (source: official docs, fetched 2026-05-10):

| Event             | hookSpecificOutput permitted? | Allowed fields inside                                          |
|-------------------|-------------------------------|----------------------------------------------------------------|
| Stop              | yes                           | hookEventName ONLY                                             |
| SubagentStop      | yes                           | hookEventName ONLY                                             |
| PreToolUse        | yes                           | hookEventName, permissionDecision, permissionDecisionReason,   |
|                   |                               | updatedInput, additionalContext                                |
| PostToolUse       | yes                           | hookEventName, additionalContext                               |
| UserPromptSubmit  | yes                           | hookEventName, additionalContext, sessionTitle                 |
| SessionStart      | yes                           | hookEventName, additionalContext                               |
| SessionEnd        | NO                            | (no decision control at all)                                   |

Top-level ``decision``/``reason`` is permitted for events that support
decision control (Stop, SubagentStop, PreToolUse, PostToolUse,
UserPromptSubmit) but NOT for SessionEnd.

Test strategy:

1. Enumerate every (plugin, event_name, command) triple across the repo.
2. Substitute ``${CLAUDE_PLUGIN_ROOT}`` into the plugin's absolute path.
3. Run the command with ``"{}"`` on stdin and a minimal env. Exit code
   is NOT asserted — scripts may legitimately bail out on missing
   project state; we only care that whatever they DO emit on stdout is
   schema-compliant.
4. Capture stdout, allow whitespace-only output as a pass. For each
   JSON line on stdout, validate against the per-event schema.

Tolerated: non-JSON whitespace, scripts that exit non-zero, scripts
that print to stderr. Rejected: any JSON on stdout that fails the
per-event schema.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


def _ci_truthy() -> bool:
    """Canonical CI-truthy check — see test_silent_skip_ci_discipline.py."""
    return os.environ.get("CI", "").lower() in ("true", "1")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Fields allowed inside hookSpecificOutput, per event.
# None  -> hookSpecificOutput is not permitted at all (SessionEnd).
HOOK_SPECIFIC_OUTPUT_FIELDS: dict[str, set[str] | None] = {
    "Stop": {"hookEventName"},
    "SubagentStop": {"hookEventName"},
    "PreToolUse": {
        "hookEventName",
        "permissionDecision",
        "permissionDecisionReason",
        "updatedInput",
        "additionalContext",
    },
    "PostToolUse": {"hookEventName", "additionalContext"},
    "UserPromptSubmit": {
        "hookEventName",
        "additionalContext",
        "sessionTitle",
    },
    "SessionStart": {"hookEventName", "additionalContext"},
    "SessionEnd": None,
}

# Events that support top-level decision control (`decision` / `reason`).
DECISION_CONTROL_EVENTS = frozenset({
    "Stop",
    "SubagentStop",
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
})

# Top-level fields the harness accepts for any event with decision control.
# `suppressOutput`, `continue`, `stopReason`, `systemMessage` are documented
# behaviour controls; we admit them but don't otherwise care.
ALLOWED_TOP_LEVEL = frozenset({
    "hookSpecificOutput",
    "decision",
    "reason",
    "suppressOutput",
    "continue",
    "stopReason",
    "systemMessage",
})


# ---------------------------------------------------------------------------
# Hook discovery
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGINS_ROOT = _REPO_ROOT / "plugins"


def _load_plugin_hooks(plugin_dir: Path) -> dict[str, Any]:
    """Read hooks.json, unwrap top-level ``hooks`` key (Claude Code 2.1.132+
    schema, ADR-039), return inner event-name dict."""
    hooks_file = plugin_dir / "hooks" / "hooks.json"
    if not hooks_file.exists():
        return {}
    raw = json.loads(hooks_file.read_text(encoding="utf-8"))
    inner = raw.get("hooks", raw)
    return inner if isinstance(inner, dict) else {}


def _enumerate_hook_commands() -> list[tuple[str, str, str]]:
    """Yield (plugin_name, event_name, command_string) for every command
    registered across every plugin's hooks.json.

    Skips non-``command`` types and shell-wrapper noise. The command string
    is returned verbatim — ``${CLAUDE_PLUGIN_ROOT}`` is substituted at run
    time so the test can resolve it against the real plugin directory.
    """
    rows: list[tuple[str, str, str]] = []
    for plugin_dir in sorted(_PLUGINS_ROOT.iterdir()):
        if not plugin_dir.is_dir():
            continue
        events = _load_plugin_hooks(plugin_dir)
        for event_name, matcher_groups in events.items():
            if event_name not in HOOK_SPECIFIC_OUTPUT_FIELDS:
                # Event not covered by the schema map — skip to keep test
                # deterministic. New events should be added explicitly.
                continue
            if not isinstance(matcher_groups, list):
                continue
            for group in matcher_groups:
                for hook in group.get("hooks", []) or []:
                    if hook.get("type") != "command":
                        continue
                    cmd = hook.get("command")
                    if not isinstance(cmd, str) or not cmd.strip():
                        continue
                    rows.append((plugin_dir.name, event_name, cmd))
    return rows


_HOOK_COMMANDS = _enumerate_hook_commands()


def _idfn(triple: tuple[str, str, str]) -> str:
    plugin, event, cmd = triple
    # Pick a short readable id: plugin/event/script-tail
    tail = cmd.split("/")[-1].rsplit('"', 1)[0]
    return f"{plugin}::{event}::{tail}"


# ---------------------------------------------------------------------------
# Minimal stdin per event (best-effort skeletons — scripts must degrade
# gracefully when fields are missing)
# ---------------------------------------------------------------------------

def _stdin_for_event(event_name: str, project_root: Path) -> str:
    common = {
        "session_id": "test-session-schema",
        "transcript_path": str(project_root / "_transcript.jsonl"),
        "cwd": str(project_root),
        "hook_event_name": event_name,
    }
    extras: dict[str, Any] = {}
    if event_name == "PreToolUse":
        extras = {"tool_name": "Edit", "tool_input": {"file_path": str(project_root / "noop.txt")}}
    elif event_name == "PostToolUse":
        extras = {"tool_name": "Edit", "tool_input": {"file_path": str(project_root / "noop.txt")}, "tool_response": {}}
    elif event_name == "UserPromptSubmit":
        extras = {"prompt": "schema audit probe"}
    return json.dumps({**common, **extras})


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

def _resolve_command(plugin_name: str, raw_cmd: str) -> list[str]:
    """Substitute ${CLAUDE_PLUGIN_ROOT} and split into argv."""
    plugin_root = (_PLUGINS_ROOT / plugin_name).resolve()
    expanded = raw_cmd.replace("${CLAUDE_PLUGIN_ROOT}", plugin_root.as_posix())
    # On Windows, paths with backslashes confuse shlex. POSIX-mode parse.
    return shlex.split(expanded, posix=True)


def _seed_shipwright_cwd(cwd: Path) -> None:
    """Materialise a minimal-but-real Shipwright project in ``cwd`` so the
    hook scripts take their production code paths instead of bailing out
    on the "not a Shipwright project" guards.

    Without this, every script hits an early-return and the test silently
    passes for scripts whose violation is on the active path. The seed
    is intentionally minimal (only what the guards check) so unrelated
    side effects stay quiet.
    """
    agent_docs = cwd / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    (cwd / "shipwright_run_config.json").write_text(
        json.dumps({
            "run_id": "run-schema-test",
            "current_step": "iterate",
            "completed_steps": [],
            "status": "complete",
            "profile": "test",
        }),
        encoding="utf-8",
    )
    (cwd / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    # check_documentation needs agent_docs/ to exist; absence of
    # decision_log.md and session_handoff.md then triggers its emission.


def _run(cmd_argv: list[str], stdin_data: str, cwd: Path, plugin_root: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = "test-session-schema"
    # Force write_terminal_marker to emit (production path).
    env["SHIPWRIGHT_LOOP_ID"] = "test-loop-schema"
    env["SHIPWRIGHT_LOOP_UNIT_ID"] = "test-unit-schema"
    # Force audit_phase_quality_on_stop into its emission path. The script
    # uses CLAUDE_PLUGIN_ROOT to map the registering plugin back to a phase.
    # Without it, every audit hook silently no-ops.
    env["SHIPWRIGHT_PHASE_QUALITY"] = "1"
    env["CLAUDE_PLUGIN_ROOT"] = plugin_root.as_posix()
    env.pop("SHIPWRIGHT_SKIP_QUALITY_CHECK", None)
    return subprocess.run(
        cmd_argv,
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Schema validators
# ---------------------------------------------------------------------------

def _validate_payload(event_name: str, payload: dict[str, Any]) -> list[str]:
    """Return a list of human-readable violations (empty list = compliant)."""
    violations: list[str] = []

    # 1. Top-level keys
    extras = set(payload) - ALLOWED_TOP_LEVEL
    if extras:
        violations.append(
            f"unrecognised top-level key(s) for {event_name}: {sorted(extras)}"
        )

    # 2. decision/reason are only allowed for decision-control events
    if "decision" in payload and event_name not in DECISION_CONTROL_EVENTS:
        violations.append(
            f"top-level 'decision' not permitted for {event_name} "
            f"(event lacks decision control)"
        )

    # 3. hookSpecificOutput
    if "hookSpecificOutput" in payload:
        allowed = HOOK_SPECIFIC_OUTPUT_FIELDS.get(event_name)
        if allowed is None:
            violations.append(
                f"hookSpecificOutput not permitted for {event_name}"
            )
        else:
            hso = payload["hookSpecificOutput"]
            if not isinstance(hso, dict):
                violations.append(
                    f"hookSpecificOutput must be an object for {event_name}, "
                    f"got {type(hso).__name__}"
                )
            else:
                bad = set(hso) - allowed
                if bad:
                    violations.append(
                        f"hookSpecificOutput contains field(s) not permitted "
                        f"for {event_name}: {sorted(bad)} "
                        f"(allowed: {sorted(allowed)})"
                    )
                hen = hso.get("hookEventName")
                if hen is not None and hen != event_name:
                    violations.append(
                        f"hookSpecificOutput.hookEventName={hen!r} but event "
                        f"is {event_name!r}"
                    )

    return violations


def _validate_stdout(event_name: str, stdout: str) -> list[str]:
    """Stdout may be empty or contain JSON line(s).

    The Claude Code harness actually silently ignores non-JSON stdout
    rather than rejecting it — but for Shipwright hook scripts we choose
    a stricter contract: stdout is either empty or schema-valid JSON,
    never raw text. Plain-text on stdout indicates a hook that should
    have routed its diagnostic to stderr (the Stop/SubagentStop schema
    contract). Catching it here at the regression-test layer prevents
    drift back to the bad pattern this iterate fixed.
    """
    if not stdout or not stdout.strip():
        return []

    violations: list[str] = []
    # Each line that looks like JSON is validated independently. Non-JSON
    # text on stdout is itself a violation — the harness expects JSON.
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not (stripped.startswith("{") and stripped.endswith("}")):
            violations.append(
                f"non-JSON text on stdout: {stripped[:120]!r} "
                f"(harness expects JSON or empty stdout)"
            )
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            violations.append(
                f"stdout line is not valid JSON: {exc} ({stripped[:120]!r})"
            )
            continue
        if not isinstance(payload, dict):
            violations.append(
                f"stdout JSON must be an object, got {type(payload).__name__}"
            )
            continue
        violations.extend(_validate_payload(event_name, payload))
    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _HOOK_COMMANDS,
    reason="no hook commands discovered — check plugins/*/hooks/hooks.json",
)
@pytest.mark.parametrize("triple", _HOOK_COMMANDS, ids=_idfn)
def test_hook_stdout_matches_event_schema(triple: tuple[str, str, str], tmp_path: Path) -> None:
    plugin_name, event_name, raw_cmd = triple
    cmd_argv = _resolve_command(plugin_name, raw_cmd)
    if not cmd_argv:
        pytest.skip(f"empty command for {plugin_name}/{event_name}")

    # Treat 'uv run --no-project' the same as 'uv run' — both must resolve.
    # The first arg must exist as an executable on PATH for the test to run.
    if cmd_argv[0] == "uv":
        # 'uv' must be on PATH for the test to be meaningful.
        # AC-3: local-skip / CI-fail per the canonical convention.
        import shutil as _shutil
        if _shutil.which("uv") is None:
            _msg = (
                "uv not on PATH; cannot exercise hook commands. "
                "Install via astral-sh/setup-uv@v3 in CI; locally see "
                "https://docs.astral.sh/uv/getting-started/installation/."
            )
            if _ci_truthy():
                pytest.fail(_msg, pytrace=False)
            pytest.skip(_msg)

    _seed_shipwright_cwd(tmp_path)
    stdin = _stdin_for_event(event_name, tmp_path)
    plugin_root = (_PLUGINS_ROOT / plugin_name).resolve()
    try:
        result = _run(cmd_argv, stdin, tmp_path, plugin_root)
    except subprocess.TimeoutExpired:
        pytest.fail(f"{plugin_name}/{event_name} timed out — likely hanging on stdin")
    except FileNotFoundError as exc:
        pytest.skip(f"command not executable: {exc}")

    violations = _validate_stdout(event_name, result.stdout)
    if violations:
        msg = (
            f"\n[SCHEMA VIOLATION] {plugin_name} :: {event_name}\n"
            f"command: {' '.join(cmd_argv)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr[:500]}\n"
            "violations:\n  - " + "\n  - ".join(violations)
        )
        pytest.fail(msg)


def test_at_least_one_hook_discovered() -> None:
    """Guardrail: if discovery silently breaks (rename, glob, schema change),
    the parametrized test would collect zero cases and falsely report green.
    """
    assert _HOOK_COMMANDS, (
        "discovered zero hooks — plugins/*/hooks/hooks.json layout may have "
        "changed; update _enumerate_hook_commands()"
    )
    # Belt + suspenders: at least a Stop hook in shipwright-build (we know
    # this plugin's Stop chain has 5 entries).
    build_stops = [t for t in _HOOK_COMMANDS if t[0] == "shipwright-build" and t[1] == "Stop"]
    assert build_stops, "shipwright-build has no Stop hook discovered"
