"""Cross-component integration test: hooks.json wiring -> the real hook
script, driven as a subprocess (iterate-2026-08-09-compaction-state-audit).

The F11 verifier's `check_integration_coverage` flags this iterate as
cross-component (it touches `hooks.json` + a script under `hooks/`) and
requires a real-scenario test proving the pieces actually compose, not just
that each piece works in isolation. `test_review_payload_on_stop.py` already
covers the script's own logic via direct module import; this file instead
starts from `hooks.json` itself — the wiring a session actually runs — and
proves that its three SubagentStop `command` strings, with
`${CLAUDE_PLUGIN_ROOT}` resolved exactly the way Claude Code resolves it,
launch the real script as a subprocess and produce the right salvage output
for the right review type.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

RUN_ID = "iterate-2026-08-09-compaction-state-audit"


def _subagent_stop_commands() -> dict[str, str]:
    """matcher (e.g. "shipwright-build:spec-reviewer") -> its command string."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    out = {}
    for entry in config["hooks"]["SubagentStop"]:
        out[entry["matcher"]] = entry["hooks"][0]["command"]
    return out


def test_hooks_json_wires_all_three_reviewers_to_the_salvage_hook():
    commands = _subagent_stop_commands()
    assert set(commands) == {
        "shipwright-build:spec-reviewer",
        "shipwright-build:code-reviewer",
        "shipwright-build:doubt-reviewer",
    }
    for matcher, command in commands.items():
        review_type = matcher.rsplit("-", 1)[0].rsplit(":", 1)[1]  # "spec-reviewer" -> "spec"
        assert "write-review-payload-on-stop.py" in command
        assert f"--review-type {review_type}" in command


def _run_wired_command(command: str, tmp_path: Path, run_id: str) -> subprocess.CompletedProcess:
    """Resolve ${CLAUDE_PLUGIN_ROOT} the way Claude Code does, strip the
    `uv run` launcher (the test drives the script directly with `sys.executable`
    for speed/determinism — this is still the real script, the real argv, and
    the real hooks.json string, just without uv's own venv-resolution step),
    and execute it as a real subprocess against a fixture transcript+project."""
    resolved = command.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN_ROOT))
    assert resolved.startswith("uv run ")
    parts = resolved[len("uv run ") :].split()
    script_path = parts[0].strip('"')
    extra_args = parts[1:]

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps(x)
            for x in [
                {"role": "user", "content": f"Review this diff for {run_id}."},
                {"role": "assistant", "content": '{"verdict": "pass"}'},
            ]
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, script_path, *extra_args],
        input=json.dumps({"transcript_path": str(transcript)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        env=env,
    )


def test_each_wired_command_salvages_into_the_correct_review_type(tmp_path):
    commands = _subagent_stop_commands()
    for matcher, command in commands.items():
        review_type = matcher.rsplit("-", 1)[0].rsplit(":", 1)[1]
        project_root = tmp_path / review_type
        project_root.mkdir()

        result = _run_wired_command(command, project_root, RUN_ID)

        assert result.returncode == 0, result.stderr
        salvage = (
            project_root / ".shipwright" / "planning" / "iterate" / RUN_ID
            / f"{review_type}_salvaged_raw.json"
        )
        assert salvage.exists(), f"{matcher}'s wired command did not salvage: {result.stderr}"
        assert json.loads(salvage.read_text(encoding="utf-8"))["verdict"] == "pass"
