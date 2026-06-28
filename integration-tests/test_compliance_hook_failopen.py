"""Integration coverage (cross_component): compliance PreToolUse Bash gates
must fail OPEN and be invoked robustly.

This is the `category:"integration"` test the F11 `check_integration_coverage`
gate requires because the diff touches `hooks.json` + `hooks/*.py` (FRAMEWORK
hook machinery). It proves two pieces COMPOSE — the invocation contract declared
in `hooks.json` and the runtime fail-open behavior of the real hook scripts:

  * **Invocation contract** — both Bash PreToolUse hook commands carry
    `--no-project` (skips the per-Bash-call `uv` project sync whose intermittent
    failure was the reported "No stderr output" fail-close), and `hooks.json`
    round-trips as valid JSON (it is an io-boundary config Claude Code parses).
  * **Fail-open composition** — running each hook script END-TO-END as a
    subprocess on a payload that forces a genuine internal crash
    (`{"tool_input": "<str>"}` → `AttributeError` in the un-guarded body) exits 0
    (ALLOW) and records a diagnostic in the gitignored runtime hook-error log.
    A crashing gate must never hard-block an unrelated Bash call.

Background: the matcher is `Bash`, so a flaky/ crashing gate blocked ALL Bash
calls (git add, test runs, file reads), not just deploy/commit
(iterate-2026-06-27-codeql-security-hardening).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT

COMPLIANCE_PLUGIN = REPO_ROOT / "plugins" / "shipwright-compliance"
HOOKS_JSON = COMPLIANCE_PLUGIN / "hooks" / "hooks.json"
HOOKS_DIR = COMPLIANCE_PLUGIN / "scripts" / "hooks"
LOG_REL = Path(".shipwright") / "agent_docs" / "runtime" / "hook_errors.log"

# The two Bash PreToolUse gates whose every-Bash-call invocation must be robust.
BASH_GATES = ("check_rtm_coverage.py", "check_security_scan.py")


def _bash_pretooluse_commands() -> list[str]:
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))  # round-trip / valid JSON
    cmds: list[str] = []
    for entry in data["hooks"].get("PreToolUse", []):
        if entry.get("matcher") == "Bash":
            cmds.extend(h["command"] for h in entry.get("hooks", []))
    return cmds


def _run_hook_failing(hook_script: str, project_root: Path) -> int:
    """Run a hook with a payload that crashes the un-guarded body.

    `tool_input` is a *string*, so `payload.get("tool_input", {}).get(...)`
    raises `AttributeError` — a real, currently-reachable crash path. The env
    pins the diagnostic-log destination deterministically.
    """
    env = {**os.environ, "SHIPWRIGHT_PROJECT_ROOT": str(project_root)}
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook_script)],
        input=json.dumps({"tool_input": "this-is-not-a-dict"}),
        capture_output=True,
        text=True,
        cwd=str(project_root),
        env=env,
    )
    return result.returncode


class TestInvocationContract:
    """The `hooks.json` side of the composition (declared invocation)."""

    def test_hooks_json_is_valid_json(self):
        # io-boundary round-trip: Claude Code must be able to parse this config.
        assert isinstance(json.loads(HOOKS_JSON.read_text(encoding="utf-8")), dict)

    def test_both_bash_gates_use_no_project(self):
        cmds = _bash_pretooluse_commands()
        for gate in BASH_GATES:
            matching = [c for c in cmds if gate in c]
            assert matching, f"{gate} not registered as a Bash PreToolUse hook"
            for c in matching:
                assert "--no-project" in c, (
                    f"{gate} invocation must use `uv run --no-project` to avoid the "
                    f"per-Bash-call project sync whose flakiness fail-closed: {c!r}"
                )


class TestFailOpenComposition:
    """The runtime side: the real scripts named by the contract fail OPEN."""

    def test_security_scan_fails_open_on_internal_crash(self, tmp_path: Path):
        assert _run_hook_failing("check_security_scan.py", tmp_path) == 0
        assert (tmp_path / LOG_REL).exists(), "fail-open must leave a diagnostic"

    def test_rtm_coverage_fails_open_on_internal_crash(self, tmp_path: Path):
        assert _run_hook_failing("check_rtm_coverage.py", tmp_path) == 0
        assert (tmp_path / LOG_REL).exists(), "fail-open must leave a diagnostic"

    def test_diagnostic_names_the_failing_hook(self, tmp_path: Path):
        _run_hook_failing("check_security_scan.py", tmp_path)
        content = (tmp_path / LOG_REL).read_text(encoding="utf-8")
        assert "FAILOPEN" in content and "check_security_scan" in content
