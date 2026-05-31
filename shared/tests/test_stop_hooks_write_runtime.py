"""Empirical: every Stop-hook writer targets ``runtime/``, not tracked.

iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
moved the 3 agent-doc MD producers from the tracked path to a gitignored
runtime/ subdir. Drift protection: spawn each Stop hook in a tmp_path
project, assert no writes land directly at
``.shipwright/agent_docs/<name>.md`` (only at the runtime/ counterpart).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_HOOK = REPO_ROOT / "shared" / "scripts" / "hooks" / "generate_handoff_on_stop.py"
TRIAGE_HOOK = REPO_ROOT / "shared" / "scripts" / "hooks" / "aggregate_triage_on_stop.py"


def _seed_project(project_root: Path) -> None:
    """Minimal Shipwright-managed project shape."""
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "current_step": "design",
            "completed_steps": ["project", "plan", "build", "test", "changelog"],
        }),
        encoding="utf-8",
    )
    sw = project_root / ".shipwright"
    sw.mkdir(parents=True, exist_ok=True)
    (sw / "triage.jsonl").write_text("", encoding="utf-8")
    (project_root / "shipwright_events.jsonl").write_text("", encoding="utf-8")


def _run_hook(hook_path: Path, project_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(project_root)
    env["SHIPWRIGHT_SESSION_ID"] = "test-stop-hook-runtime"
    return subprocess.run(
        ["uv", "run", "--no-project", "--project", str(REPO_ROOT), str(hook_path)],
        input="{}",
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(
    "hook_path,expected_runtime_files",
    [
        (HANDOFF_HOOK, ["session_handoff.md", "build_dashboard.md"]),
        (TRIAGE_HOOK, ["triage_inbox.md"]),
    ],
    ids=["handoff_on_stop", "aggregate_triage_on_stop"],
)
def test_stop_hook_writes_runtime_only(
    tmp_path: Path,
    hook_path: Path,
    expected_runtime_files: list[str],
) -> None:
    _seed_project(tmp_path)
    proc = _run_hook(hook_path, tmp_path)
    # Stop hooks always exit 0 (never block); diagnostic to stderr.
    assert proc.returncode == 0, (
        f"hook exited non-zero: rc={proc.returncode}\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )

    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    runtime = agent_docs / "runtime"

    # Each expected runtime file must exist.
    for name in expected_runtime_files:
        runtime_file = runtime / name
        assert runtime_file.is_file(), (
            f"expected runtime/{name} after hook, got listing: "
            f"{list(runtime.glob('*')) if runtime.exists() else 'no runtime dir'}\n"
            f"stderr={proc.stderr!r}"
        )

    # None of the same names may appear directly under agent_docs/ (the
    # tracked location) — finalize is the sole producer of those.
    for name in expected_runtime_files:
        tracked_file = agent_docs / name
        assert not tracked_file.exists(), (
            f"Stop hook wrote tracked path agent_docs/{name} (must go to runtime/)\n"
            f"This is the recurring dirty-main regression this iterate closes."
        )
