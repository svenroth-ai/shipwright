"""Integration: aggregate_triage Stop hook fan-out regenerates once.

`cross_component` integration coverage (category:"integration") for
iterate-2026-06-20-aggregate-triage-stop-fanout-dedup. The hook is registered in
all 12 plugins, so one Stop fires it 12×; before the `claim_once_for_event`
guard each invocation regenerated the `triage_inbox.md` derived cache (a
non-atomic write_text). This drives the ACTUAL hook script across a simulated
12-plugin fan-out in a real git project and proves the register-everywhere hook
+ the once-per-(event, session) claim COMPOSE:

- exactly ONE invocation regenerates per Stop (sequential AND parallel);
- the claim is per (event, session): a second session regenerates once.

Own module (not test_hook_fanout_consolidation.py) so that file stays at its
bloat baseline. Lives in integration-tests/ (a CI-run root) per ADR-044.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = _REPO_ROOT / "shared" / "scripts" / "hooks" / "aggregate_triage_on_stop.py"

ALL_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan",
    "shipwright-build", "shipwright-test", "shipwright-security",
    "shipwright-deploy", "shipwright-changelog", "shipwright-compliance",
    "shipwright-iterate", "shipwright-adopt", "shipwright-run",
]
_REGEN = "[aggregate_triage_on_stop] regenerated"


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    project = tmp_path / "app"
    project.mkdir()
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "completed_steps": ["project", "build"]}),
        encoding="utf-8")
    sw = project / ".shipwright"
    sw.mkdir()
    (sw / "triage.jsonl").write_text("", encoding="utf-8")
    (project / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    for cmd in (["git", "init", "-b", "main"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "--allow-empty", "-m", "init"]):
        r = subprocess.run(cmd, cwd=str(project), capture_output=True, encoding="utf-8")
        assert r.returncode == 0, f"git setup failed ({cmd}): {r.stderr}"
    return project


def _fire(project: Path, *, plugin: str, session_id: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(project)
    env["CLAUDE_PLUGIN_ROOT"] = str(Path("/fake/plugins") / plugin)
    return subprocess.run(
        [sys.executable, str(HOOK)], input="{}", cwd=str(project), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _fanout(project, session_id, *, parallel=False):
    if not parallel:
        return [_fire(project, plugin=p, session_id=session_id) for p in ALL_PLUGINS]
    with ThreadPoolExecutor(max_workers=len(ALL_PLUGINS)) as ex:
        return list(ex.map(
            lambda p: _fire(project, plugin=p, session_id=session_id), ALL_PLUGINS))


def _regens(results) -> int:
    return sum(1 for r in results if _REGEN in r.stderr)


def _skips(results) -> int:
    return sum(1 for r in results if "fan-out dedup" in r.stderr)


def _inbox(project: Path) -> Path:
    return project / ".shipwright" / "agent_docs" / "runtime" / "triage_inbox.md"


def test_aggregate_triage_fanout_regenerates_once(git_project: Path):
    results = _fanout(git_project, "sess-agg")
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert _regens(results) == 1, [r.stderr for r in results]
    # The other 11 invocations must announce the dedup-skip (observability).
    assert _skips(results) == len(ALL_PLUGINS) - 1, [r.stderr for r in results]
    assert _inbox(git_project).is_file()


def test_aggregate_triage_fanout_concurrent_one_regen(git_project: Path):
    """Claim atomicity under PARALLEL fan-out — exactly one regenerator."""
    results = _fanout(git_project, "sess-agg-par", parallel=True)
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert _regens(results) == 1, [r.stderr for r in results]
    assert _skips(results) == len(ALL_PLUGINS) - 1, [r.stderr for r in results]


def test_aggregate_triage_fanout_per_session_independent(git_project: Path):
    """The claim is per (event, session): a second session regenerates once."""
    assert _regens(_fanout(git_project, "sess-one")) == 1
    assert _regens(_fanout(git_project, "sess-two")) == 1
