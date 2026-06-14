"""Integration: hook fan-out consolidation (once-per-event guard + resolver).

Claude Code fires every enabled plugin's hooks with no active-plugin filter, so a
shared hook registered in N plugins runs N× per event. This suite drives the
ACTUAL hook scripts as subprocesses across a simulated multi-plugin fan-out in a
real git project, proving the once-per-(event, session) guard + the session-state
phase resolver + register-everywhere COMPOSE:

- AC-1  exactly-once: one Stop event audits the engaged phase(s) once, not 11×.
- AC-2  phase from SESSION STATE, not CLAUDE_PLUGIN_ROOT.
- AC-4  generate_handoff regenerates once across the fan-out.
- AC-5  robust when the first-firing plugin is "disabled" — no single owner.
- AC-6  mark_plugin_edit / check_file_size markers CONVERGE (already idempotent).
- concurrency: exactly one winner under PARALLEL fan-out (claim atomicity) —
  external-review (gpt#8 / gemini).

This is the cross_component integration-coverage row for
iterate-2026-06-14-hook-fanout-dedup. Lives in integration-tests/ (a CI-run
root) rather than shared/tests/ (not CI-run), per ADR-044.
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
_HOOKS = _REPO_ROOT / "shared" / "scripts" / "hooks"
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402

AUDIT_HOOK = _HOOKS / "audit_phase_quality_on_stop.py"
HANDOFF_HOOK = _HOOKS / "generate_handoff_on_stop.py"
DRIFT_HOOK = _HOOKS / "check_artifact_drift.py"
CHECK_FILE_SIZE_HOOK = _HOOKS / "check_file_size.py"
MARK_PLUGIN_EDIT_HOOK = _HOOKS / "mark_plugin_edit.py"

# All 12 hooks-bearing plugins (SessionStart/PostToolUse fan-out width).
ALL_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan",
    "shipwright-build", "shipwright-test", "shipwright-security",
    "shipwright-deploy", "shipwright-changelog", "shipwright-compliance",
    "shipwright-iterate", "shipwright-adopt", "shipwright-run",
]

# The 11 plugins that register the Stop audit hook (every plugin except run).
AUDIT_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan",
    "shipwright-build", "shipwright-test", "shipwright-security",
    "shipwright-deploy", "shipwright-changelog", "shipwright-compliance",
    "shipwright-iterate", "shipwright-adopt",
]
# The expected engaged phase set for the fixture below (session state, NOT the
# plugin roots): project + plan via completed_steps, build via current_step/event.
ENGAGED = {"project", "plan", "build"}


@pytest.fixture
def hooks_project(tmp_path: Path) -> Path:
    """A real git-backed, Shipwright-managed project with engaged phases."""
    project = tmp_path / "app"
    (project / ".shipwright" / "agent_docs").mkdir(parents=True)
    (project / "shipwright_run_config.json").write_text(
        json.dumps({
            "run_id": "run-int",
            "status": "in_progress",
            "current_step": "build",
            "completed_steps": ["project", "plan"],
        }),
        encoding="utf-8",
    )
    (project / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "phase_completed", "phase": "build"}) + "\n",
        encoding="utf-8",
    )
    for cmd in (["git", "init", "-b", "main"], ["git", "add", "."],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "-m", "init"]):
        subprocess.run(cmd, cwd=str(project), capture_output=True, encoding="utf-8")
    return project


def _fire(
    hook: Path,
    project: Path,
    *,
    plugin: str,
    session_id: str,
    stdin: str = "{}",
) -> subprocess.CompletedProcess:
    """Invoke a hook script as Claude Code would (one plugin's invocation)."""
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    env["CLAUDE_PLUGIN_ROOT"] = str(Path("/fake/plugins") / plugin)
    for k in ("SHIPWRIGHT_PROJECT_ROOT", "SHIPWRIGHT_LOOP_ID",
              "SHIPWRIGHT_LOOP_UNIT_ID", "SHIPWRIGHT_RUN_ID"):
        env.pop(k, None)
    return subprocess.run(
        [sys.executable, str(hook)],
        input=stdin, capture_output=True, text=True,
        cwd=str(project), env=env,
    )


def _fanout(hook, project, plugins, session_id, *, stdin="{}", parallel=False):
    """Fire ``hook`` once per plugin in one session; return the CompletedProcesses."""
    if not parallel:
        return [_fire(hook, project, plugin=p, session_id=session_id, stdin=stdin)
                for p in plugins]
    with ThreadPoolExecutor(max_workers=len(plugins)) as ex:
        return list(ex.map(
            lambda p: _fire(hook, project, plugin=p, session_id=session_id, stdin=stdin),
            plugins,
        ))


def _findings_by_phase(project: Path) -> dict[str, dict]:
    finding_dir = project / pq.FINDING_DIR
    out: dict[str, dict] = {}
    if finding_dir.is_dir():
        for p in finding_dir.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            out[d["phase"]] = d
    return out


# --------------------------------------------------------------------------
# AC-1 / AC-2 — Stop audit: once across the fan-out, phase from session state
# --------------------------------------------------------------------------

def test_stop_audit_fanout_runs_once(hooks_project: Path):
    results = _fanout(AUDIT_HOOK, hooks_project, AUDIT_PLUGINS, "sess-seq")
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    # Exactly ONE of the 11 invocations did the audit (claim winner); the rest
    # returned before emitting.
    did_audit = [r for r in results if "audited" in r.stderr]
    assert len(did_audit) == 1, [r.stderr for r in results]
    # AC-2: the audited phases come from SESSION STATE, not the 11 plugin roots.
    assert set(_findings_by_phase(hooks_project)) == ENGAGED
    # Aggregates regenerated once.
    assert (hooks_project / pq.REPORT_PATH).exists()
    assert (hooks_project / pq.DASHBOARD_PATH).exists()


def test_stop_audit_fanout_concurrent_one_winner(hooks_project: Path):
    """Claim atomicity under PARALLEL fan-out — exactly one winner (gpt#8/gem)."""
    results = _fanout(AUDIT_HOOK, hooks_project, AUDIT_PLUGINS, "sess-par",
                      parallel=True)
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    did_audit = [r for r in results if "audited" in r.stderr]
    assert len(did_audit) == 1, [r.stderr for r in results]
    assert set(_findings_by_phase(hooks_project)) == ENGAGED


def test_audit_phase_from_session_state_not_plugin_root(hooks_project: Path):
    """A single invocation from a NON-engaged plugin root (deploy) still audits
    the engaged phases — proving phase comes from session state, not the root."""
    r = _fire(AUDIT_HOOK, hooks_project, plugin="shipwright-deploy",
              session_id="sess-deploy")
    assert r.returncode == 0, r.stderr
    audited = set(_findings_by_phase(hooks_project))
    assert audited == ENGAGED
    assert "deploy" not in audited  # plugin-root phase ignored


# --------------------------------------------------------------------------
# AC-5 — robust when the first-firing plugin is "disabled" (no single owner)
# --------------------------------------------------------------------------

def test_robust_when_first_plugin_disabled(hooks_project: Path):
    # Drop the first plugin from the fan-out — a later plugin must still do the
    # work exactly once (the guard has no single controlling plugin).
    results = _fanout(AUDIT_HOOK, hooks_project, AUDIT_PLUGINS[1:], "sess-nofirst")
    assert all(r.returncode == 0 for r in results)
    did_audit = [r for r in results if "audited" in r.stderr]
    assert len(did_audit) == 1
    assert set(_findings_by_phase(hooks_project)) == ENGAGED


def test_foreign_first_invocation_does_not_block(hooks_project: Path):
    """Guard-before-claim (gpt#2 / code gpt#4): a FOREIGN plugin firing first
    must no-op WITHOUT consuming the claim, so a later recognized plugin still
    audits exactly once."""
    r_foreign = _fire(AUDIT_HOOK, hooks_project, plugin="not-a-shipwright-plugin",
                      session_id="sess-foreign")
    assert r_foreign.returncode == 0
    assert "audited" not in r_foreign.stderr  # foreign no-ops
    claim = (hooks_project / ".shipwright" / ".cache"
             / "stop-phasequality-sess-foreign.claim")
    assert not claim.exists(), "foreign invocation must not consume the claim"
    # A recognized plugin firing afterwards still does the work once.
    r_real = _fire(AUDIT_HOOK, hooks_project, plugin="shipwright-build",
                   session_id="sess-foreign")
    assert r_real.returncode == 0, r_real.stderr
    assert "audited" in r_real.stderr
    assert set(_findings_by_phase(hooks_project)) == ENGAGED


# --------------------------------------------------------------------------
# AC-4 — generate_handoff regenerates once across the fan-out;
#        check_artifact_drift scans/emits once per SessionStart
# --------------------------------------------------------------------------

def test_drift_fanout_emits_once(hooks_project: Path):
    """check_artifact_drift fires ~12× per SessionStart; the drift report +
    its `additionalContext` remediation must emit exactly ONCE (gpt#2). A
    top-level legacy artifact-migration dir makes the real detector flag drift
    (no monkeypatch needed)."""
    legacy = hooks_project / "designs"  # artifact-path-canon: legacy
    legacy.mkdir()
    (legacy / "old.html").write_text("<html></html>", encoding="utf-8")
    payload = json.dumps({"session_id": "sess-drift"})
    results = _fanout(DRIFT_HOOK, hooks_project, ALL_PLUGINS, "sess-drift",
                      stdin=payload)
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    emitted = [r for r in results if "hookSpecificOutput" in r.stdout]
    assert len(emitted) == 1, [r.stdout for r in results]  # migrated drift once
    assert (hooks_project / ".shipwright" / "stale-folders.md").exists()

def test_handoff_fanout_runs_once(hooks_project: Path):
    results = _fanout(HANDOFF_HOOK, hooks_project, AUDIT_PLUGINS, "sess-handoff",
                      parallel=True)
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    # The hook writes "[shipwright:handoff] generated at ..." only when it does
    # the work; claim-losers return before that.
    did_generate = [r for r in results if "generated" in r.stderr]
    assert len(did_generate) == 1, [r.stderr for r in results]


# --------------------------------------------------------------------------
# AC-6 — PostToolUse markers already CONVERGE (one net entry, not N)
# --------------------------------------------------------------------------

def test_check_file_size_marker_converges(hooks_project: Path):
    # An oversize source file edited 12× across the fan-out must leave exactly
    # ONE marker entry (upsert-by-path), not 12.
    big = hooks_project / "huge.py"
    big.write_text("x = 1\n" * 350, encoding="utf-8")  # > 300-line source limit
    payload = json.dumps({
        "session_id": "sess-cfs", "tool_name": "Write",
        "tool_input": {"file_path": str(big)},
    })
    results = _fanout(CHECK_FILE_SIZE_HOOK, hooks_project, AUDIT_PLUGINS + ["shipwright-run"],
                      "sess-cfs", stdin=payload)
    assert all(r.returncode == 0 for r in results)
    marker = hooks_project / ".shipwright" / "locks" / "bloat_pending.sess-cfs.json"
    assert marker.is_file(), "check_file_size wrote no marker for an oversize file"
    entries = json.loads(marker.read_text(encoding="utf-8")).get("entries", [])
    huge_entries = [e for e in entries if Path(e["path"]).name == "huge.py"]
    assert len(huge_entries) == 1, entries  # converged, not 12×


def test_mark_plugin_edit_marker_converges(hooks_project: Path):
    # mark_plugin_edit only acts in the plugin-dev monorepo and on plugin-side
    # files — seed both, then fire 12× for one edit → exactly one recorded path.
    (hooks_project / "scripts").mkdir(exist_ok=True)
    (hooks_project / "scripts" / "update-marketplace.sh").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8")
    plugin_file = hooks_project / "plugins" / "shipwright-x" / "foo.py"
    plugin_file.parent.mkdir(parents=True)
    plugin_file.write_text("y = 2\n", encoding="utf-8")
    payload = json.dumps({
        "session_id": "sess-mpe", "tool_name": "Edit",
        "tool_input": {"file_path": str(plugin_file)},
    })
    results = _fanout(MARK_PLUGIN_EDIT_HOOK, hooks_project,
                      AUDIT_PLUGINS + ["shipwright-run"], "sess-mpe", stdin=payload)
    assert all(r.returncode == 0 for r in results)
    marker = hooks_project / ".shipwright" / "locks" / "plugin_edit_pending.sess-mpe.json"
    assert marker.is_file(), "mark_plugin_edit wrote no marker for a plugin-side edit"
    paths = json.loads(marker.read_text(encoding="utf-8")).get("paths", [])
    foo_paths = [p for p in paths if p.endswith("foo.py")]
    assert len(foo_paths) == 1, paths  # set-idempotent → one entry, not 12
