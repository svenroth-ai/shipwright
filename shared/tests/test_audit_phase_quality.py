"""Tests for the Phase-Quality Stop hook and its library.

Covers (plan § 7 risk IDs in parens):

- Greenfield / non-Shipwright projects produce no output (R6)
- Canon-category C1-C5 ordering + skip criteria per phase
- Finding-JSON schema + atomic write
- Idempotency guard on (phase, run_id, session_id) (R5)
- Aggregate rewrites (report / summary / dashboard) regenerate
  deterministically and survive corrupt JSONs (R4, plan § 4.13)
- Hook never blocks — always exits 0, even on internal errors (R3)
- Env flag `SHIPWRIGHT_PHASE_QUALITY=0` fully disables the hook
- Per-check skip via `SHIPWRIGHT_SKIP_QUALITY_CHECK` emits SKIP status
- Subprocess E2E against the real hook script (R1, R22)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Re-use the shared/scripts sys.path bootstrap from conftest.py
from lib import phase_quality as pq  # noqa: E402


def _agent_docs_root(tmp: Path) -> Path:
    """Return canonical agent_docs subdir under tmp, creating parents."""
    p = tmp / ".shipwright" / "agent_docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "hooks" / "audit_phase_quality_on_stop.py"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shipwright_project(tmp_path: Path) -> Path:
    """A minimal Shipwright-managed project with events + dashboard."""
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({
            "run_id": "run-abc",
            "current_step": "build",
            "completed_steps": ["project", "design", "plan"],
        }),
        encoding="utf-8",
    )
    events = [
        {"type": "phase_completed", "phase": "build", "timestamp": "2026-04-18T12:00:00Z"},
    ]
    (tmp_path / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Dashboard\n\n## build\nsection complete\n",
        encoding="utf-8",
    )
    handoff = tmp_path / ".shipwright" / "agent_docs" / "session_handoff.md"
    handoff.write_text("# Session Handoff\n\nReason: build: finalize\n", encoding="utf-8")
    # Fresh mtime so C3 passes
    now = time.time()
    os.utime(handoff, (now, now))
    # Minimal CHANGELOG with [Unreleased]/Added
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- initial build bullet\n",
        encoding="utf-8",
    )
    # decision_log with a build ADR (covers C4)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "## ADR-001: build decision\n\n**Status:** Accepted\n\nBody.\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Unit: greenfield / non-Shipwright (R6)
# ---------------------------------------------------------------------------


def test_is_shipwright_project_requires_marker_or_agent_docs(tmp_path: Path):
    assert pq.is_shipwright_project(tmp_path) is False
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    assert pq.is_shipwright_project(tmp_path) is True


def test_is_shipwright_project_detects_run_config(tmp_path: Path):
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    assert pq.is_shipwright_project(tmp_path) is True


# ---------------------------------------------------------------------------
# Unit: plugin → phase mapping
# ---------------------------------------------------------------------------


def test_phase_from_plugin_root_maps_all_ten_plugins():
    mapped = {pq.phase_from_plugin_root(f"/x/y/{p}"): p for p in pq.PLUGIN_TO_PHASE}
    # Round-trip: every plugin resolves to a phase, no collisions
    assert len(mapped) == len(pq.PLUGIN_TO_PHASE)
    assert pq.phase_from_plugin_root("/x/y/shipwright-build") == "build"
    assert pq.phase_from_plugin_root("/x/y/shipwright-iterate") == "iterate"


def test_phase_from_plugin_root_returns_none_for_unknown():
    assert pq.phase_from_plugin_root("/x/y/not-shipwright") is None
    assert pq.phase_from_plugin_root("") is None
    assert pq.phase_from_plugin_root(None) is None


# ---------------------------------------------------------------------------
# Unit: run_id resolution (plan § 5.3)
# ---------------------------------------------------------------------------


def test_resolve_run_id_prefers_run_config(tmp_path: Path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"run_id": "run-from-config"}), encoding="utf-8",
    )
    assert pq.resolve_run_id(tmp_path, "sess-1") == "run-from-config"


def test_resolve_run_id_falls_back_to_session(tmp_path: Path):
    assert pq.resolve_run_id(tmp_path, "sess-1") == "sess-1"


def test_resolve_run_id_uses_loop_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-2")
    assert pq.resolve_run_id(tmp_path, "sess-1") == "loop-1-unit-2"


# ---------------------------------------------------------------------------
# Unit: Canon runner (C1-C5)
# ---------------------------------------------------------------------------


def test_canon_produces_five_findings_for_build(shipwright_project: Path):
    findings = pq.run_canon_checks("build", shipwright_project)
    ids = [f["id"] for f in findings]
    assert ids == ["C1", "C2", "C3", "C4", "C5"]


def test_canon_skips_c4_for_design(shipwright_project: Path):
    findings = pq.run_canon_checks("design", shipwright_project)
    c4 = next(f for f in findings if f["id"] == "C4")
    assert c4["status"] == pq.STATUS_SKIP
    assert "not applicable" in c4["evidence"]


def test_canon_skips_c5_for_plan(shipwright_project: Path):
    findings = pq.run_canon_checks("plan", shipwright_project)
    c5 = next(f for f in findings if f["id"] == "C5")
    assert c5["status"] == pq.STATUS_SKIP


def test_canon_passes_c1_when_event_present(shipwright_project: Path):
    findings = pq.run_canon_checks("build", shipwright_project)
    c1 = next(f for f in findings if f["id"] == "C1")
    assert c1["status"] == pq.STATUS_PASS


def test_canon_c1_fails_when_event_missing(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    findings = pq.run_canon_checks("build", tmp_path)
    c1 = next(f for f in findings if f["id"] == "C1")
    assert c1["status"] == pq.STATUS_FAIL
    assert c1.get("remediation")


def test_skip_env_var_overrides_canon_check(
    monkeypatch, shipwright_project: Path,
):
    monkeypatch.setenv("SHIPWRIGHT_SKIP_QUALITY_CHECK", "C1")
    monkeypatch.setenv("SHIPWRIGHT_AUDIT_OVERRIDE_REASON", "documented in ADR-042")
    findings = pq.run_canon_checks("build", shipwright_project)
    c1 = next(f for f in findings if f["id"] == "C1")
    assert c1["status"] == pq.STATUS_SKIP
    assert "ADR-042" in c1["evidence"]


# ---------------------------------------------------------------------------
# Unit: Finding-JSON schema + idempotency (R5)
# ---------------------------------------------------------------------------


def test_write_finding_json_produces_all_six_categories(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    findings = {
        "canon": [{"id": "C1", "status": "PASS", "evidence": "ok"}],
    }
    path = pq.write_finding_json(
        tmp_path, "build", "run-1", "sess-1", findings, source="standalone",
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["phase"] == "build"
    assert data["run_id"] == "run-1"
    assert data["session_id"] == "sess-1"
    assert data["source"] == "standalone"
    assert data["canon"] == [{"id": "C1", "status": "PASS", "evidence": "ok"}]
    # All categories present as empty lists when not supplied
    for category in pq.CATEGORIES:
        assert category in data


def test_already_audited_true_after_write(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    pq.write_finding_json(tmp_path, "build", "run-1", "sess-1", {"canon": []})
    assert pq.already_audited(tmp_path, "build", "run-1", "sess-1") is True


def test_already_audited_false_for_corrupt_json(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    path = pq.finding_path(tmp_path, "build", "run-1", "sess-1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert pq.already_audited(tmp_path, "build", "run-1", "sess-1") is False


# ---------------------------------------------------------------------------
# Unit: aggregate rewrites (R4 + plan § 4.13)
# ---------------------------------------------------------------------------


def test_aggregate_report_regenerates_from_findings(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    pq.write_finding_json(
        tmp_path, "build", "run-1", "sess-1",
        {"canon": [{"id": "C1", "status": "PASS", "evidence": "ok"}]},
        source="standalone",
    )
    path = pq.rewrite_aggregated_report(tmp_path)
    assert path is not None and path.exists()
    text = path.read_text(encoding="utf-8")
    assert "run-1" in text
    assert "C1" in text
    assert "build" in text


def test_dashboard_file_regenerates_with_one_row_per_phase(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    pq.write_finding_json(
        tmp_path, "build", "run-1", "sess-1",
        {"canon": [{"id": "C1", "status": "PASS", "evidence": "ok"}]},
    )
    pq.write_finding_json(
        tmp_path, "plan", "run-2", "sess-1",
        {"canon": [{"id": "C1", "status": "FAIL", "evidence": "no event"}]},
    )
    path = pq.write_quality_dashboard_file(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "build" in text
    assert "plan" in text
    # build row has 1 PASS / 0 FAIL
    assert "1P/0F" in text
    # plan row has 0 PASS / 1 FAIL
    assert "0P/1F" in text


def test_aggregate_report_skips_corrupt_json_with_warning(tmp_path: Path, capsys):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    good = pq.write_finding_json(
        tmp_path, "build", "run-1", "sess-1",
        {"canon": [{"id": "C1", "status": "PASS", "evidence": "ok"}]},
    )
    # Drop a corrupt sibling
    corrupt = good.with_name("build-run-2-sess-1.json")
    corrupt.write_text("not json", encoding="utf-8")
    path = pq.rewrite_aggregated_report(tmp_path)
    stderr = capsys.readouterr().err
    assert "corrupt" in stderr
    # Good finding still in the report
    assert "run-1" in path.read_text(encoding="utf-8")


def test_session_summary_highlights_open_fails(tmp_path: Path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    pq.write_finding_json(
        tmp_path, "build", "run-1", "sess-1",
        {"canon": [{"id": "C1", "status": "FAIL", "evidence": "no event"}]},
    )
    path = pq.rewrite_session_findings_summary(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "FAIL" in text
    assert "C1" in text


# ---------------------------------------------------------------------------
# E2E: hook subprocess
# ---------------------------------------------------------------------------


def _run_hook(
    cwd: Path,
    plugin_root: str | None = "plugins/shipwright-build",
    *,
    session_id: str = "sess-E2E",
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    # Strip any inherited loop/enforce env so tests are deterministic.
    for k in (
        "SHIPWRIGHT_LOOP_ID",
        "SHIPWRIGHT_LOOP_UNIT_ID",
        "SHIPWRIGHT_PHASE_QUALITY",
        "SHIPWRIGHT_SKIP_QUALITY_CHECK",
        "SHIPWRIGHT_AUDIT_OVERRIDE_REASON",
        "SHIPWRIGHT_PROJECT_ROOT",
    ):
        env.pop(k, None)
    if plugin_root is not None:
        # Simulate how Claude Code sets CLAUDE_PLUGIN_ROOT.
        env["CLAUDE_PLUGIN_ROOT"] = str(Path("/fake/plugins").joinpath(Path(plugin_root).name))
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="{}",
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _findings_by_phase(finding_dir: Path) -> dict[str, dict]:
    """Map ``phase`` → finding-JSON dict for every finding written this run.

    The Stop audit now resolves the audited phases from SESSION STATE and a
    single invocation covers every engaged phase, so tests assert on the SET of
    audited phases rather than "the one finding".
    """
    out: dict[str, dict] = {}
    if not finding_dir.is_dir():
        return out
    for p in finding_dir.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        out[data["phase"]] = data
    return out


def _age_claim(project: Path, *, session_id: str = "sess-E2E") -> None:
    """Age the once-per-(Stop, session) claim so the next invocation re-arms
    (reaches the per-phase already_audited dedup) instead of short-circuiting."""
    claim = (
        project / ".shipwright" / ".cache"
        / f"stop-phasequality-{session_id}.claim"
    )
    if claim.exists():
        old = time.time() - 120
        os.utime(claim, (old, old))


def test_hook_exits_zero_on_greenfield(tmp_path: Path):
    result = _run_hook(tmp_path)
    assert result.returncode == 0
    # No finding written
    assert not (tmp_path / pq.FINDING_DIR).exists()


def test_hook_exits_zero_when_plugin_root_unrecognized(shipwright_project: Path):
    result = _run_hook(shipwright_project, plugin_root="plugins/unrelated")
    assert result.returncode == 0
    assert not (shipwright_project / pq.FINDING_DIR).exists()


def test_hook_disabled_when_env_flag_zero(shipwright_project: Path):
    result = _run_hook(
        shipwright_project,
        extra_env={"SHIPWRIGHT_PHASE_QUALITY": "0"},
    )
    assert result.returncode == 0
    assert not (shipwright_project / pq.FINDING_DIR).exists()


def test_hook_writes_finding_and_aggregates(shipwright_project: Path):
    result = _run_hook(shipwright_project)
    assert result.returncode == 0, result.stderr
    finding_dir = shipwright_project / pq.FINDING_DIR
    assert finding_dir.is_dir()
    # One Stop now audits every ENGAGED phase resolved from session state
    # (project/design/plan via completed_steps + build via current_step/event),
    # not the single plugin-root phase. (Was: exactly one "build" finding.)
    fbp = _findings_by_phase(finding_dir)
    assert set(fbp) == {"project", "design", "plan", "build"}
    build = fbp["build"]
    assert build["run_id"] == "run-abc"  # from shipwright_run_config.json
    # Canon category populated with 5 checks
    assert [f["id"] for f in build["canon"]] == ["C1", "C2", "C3", "C4", "C5"]
    # Aggregates exist (regenerated once for the whole event)
    assert (shipwright_project / pq.REPORT_PATH).exists()
    assert (shipwright_project / pq.SUMMARY_PATH).exists()
    assert (shipwright_project / pq.DASHBOARD_PATH).exists()


def test_hook_claim_dedups_within_event(shipwright_project: Path):
    """Two Stop invocations in one session (the fan-out): the 2nd loses the
    once-per-event claim and skips entirely — no new findings, no rewrites."""
    r1 = _run_hook(shipwright_project)
    assert r1.returncode == 0
    finding_dir = shipwright_project / pq.FINDING_DIR
    mtimes1 = {p.name: p.stat().st_mtime for p in finding_dir.glob("*.json")}
    assert mtimes1  # first invocation wrote findings
    time.sleep(0.05)
    r2 = _run_hook(shipwright_project)  # claim still fresh → loses
    assert r2.returncode == 0
    mtimes2 = {p.name: p.stat().st_mtime for p in finding_dir.glob("*.json")}
    assert mtimes2 == mtimes1  # nothing added or rewritten


def test_hook_is_idempotent(shipwright_project: Path):
    r1 = _run_hook(shipwright_project)
    assert r1.returncode == 0
    finding_dir = shipwright_project / pq.FINDING_DIR
    mtimes1 = {p.name: p.stat().st_mtime for p in finding_dir.glob("*.json")}
    # Age the once-per-event claim so the 2nd call RE-ARMS (does not short-circuit
    # on the claim) and reaches the per-phase already_audited dedup instead.
    _age_claim(shipwright_project)
    time.sleep(0.05)
    r2 = _run_hook(shipwright_project)
    assert r2.returncode == 0
    # Post-ADR-042: idempotency diagnostic surfaces on stderr (Stop schema
    # rejects hookSpecificOutput.additionalContext on stdout).
    assert "already audited" in r2.stderr
    mtimes2 = {p.name: p.stat().st_mtime for p in finding_dir.glob("*.json")}
    assert mtimes2 == mtimes1  # no finding rewritten


def test_hook_is_non_blocking_on_error(monkeypatch, shipwright_project: Path):
    """R3 — a broken dependency must not break the Stop chain."""
    # Sabotage the CHANGELOG so C5 raises, but write_finding_json should
    # still land in the error branch gracefully.
    (shipwright_project / "CHANGELOG.md").unlink()
    # Also break the decision_log so C4 hits a fail path
    (shipwright_project / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "no adrs here\n", encoding="utf-8",
    )
    result = _run_hook(shipwright_project)
    assert result.returncode == 0
    # Build finding still written; C5 becomes a WARN/FAIL, not a crash.
    build = _findings_by_phase(shipwright_project / pq.FINDING_DIR)["build"]
    c5 = next(f for f in build["canon"] if f["id"] == "C5")
    assert c5["status"] in (pq.STATUS_FAIL, pq.STATUS_WARN)


def test_hook_phase_from_session_state_not_plugin_root(shipwright_project: Path):
    """AC-2 (negative): firing from the iterate plugin root must NOT audit the
    iterate phase when session state says iterate did not run — the plugin root
    is no longer the phase source."""
    result = _run_hook(shipwright_project, plugin_root="plugins/shipwright-iterate")
    assert result.returncode == 0, result.stderr
    fbp = _findings_by_phase(shipwright_project / pq.FINDING_DIR)
    assert "iterate" not in fbp  # plugin-root phase ignored
    assert set(fbp) == {"project", "design", "plan", "build"}  # session-state set


def test_hook_audits_iterate_when_engaged_regardless_of_plugin_root(tmp_path: Path):
    """AC-2 (positive): on a finished project (status=complete → iterate engaged),
    firing from a NON-iterate plugin root still audits iterate — proving the
    audited phase comes from session state, not CLAUDE_PLUGIN_ROOT."""
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"run_id": "run-it", "status": "complete"}), encoding="utf-8",
    )
    result = _run_hook(tmp_path, plugin_root="plugins/shipwright-build")
    assert result.returncode == 0, result.stderr
    fbp = _findings_by_phase(tmp_path / pq.FINDING_DIR)
    assert "iterate" in fbp
    assert fbp["iterate"]["source"] == "iterate"
    assert "build" not in fbp  # plugin-root phase did not run → not audited


def test_hook_output_contains_phase_quality_tag(shipwright_project: Path):
    """R22 — output is labeled so downstream filters can route it.

    Post ADR-042: Stop hooks must not emit hookSpecificOutput.additionalContext
    on stdout (schema-rejected by Claude Code). Diagnostic text is written
    to stderr instead — still surfaced to the user by the Claude Code
    harness, but no longer violating the Stop event schema.
    """
    result = _run_hook(shipwright_project)
    assert result.returncode == 0
    # stdout must NOT carry hookSpecificOutput for Stop (post-ADR-042).
    assert "hookSpecificOutput" not in result.stdout, (
        f"Stop hooks must not emit hookSpecificOutput on stdout. "
        f"stdout: {result.stdout!r}"
    )
    # stderr carries the routable diagnostic.
    assert "[phase-quality]" in result.stderr, (
        f"phase-quality tag missing from stderr: {result.stderr!r}"
    )
    assert "phase=build" in result.stderr


# ---------------------------------------------------------------------------
# Plugin registration (R1 — hook-reihenfolge)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_plugin_hooks(plugin: str) -> dict:
    """Read plugin hooks.json and unwrap the Claude Code 2.1.132+
    top-level ``hooks`` wrapper (ADR-039) so callers see the inner
    event-name dict regardless of which schema shape the file uses."""
    hooks_file = _REPO_ROOT / "plugins" / plugin / "hooks" / "hooks.json"
    raw = json.loads(hooks_file.read_text(encoding="utf-8"))
    inner = raw.get("hooks")
    return inner if isinstance(inner, dict) else raw


@pytest.mark.parametrize("plugin", sorted(pq.PLUGIN_TO_PHASE))
def test_plugin_hooks_json_registers_audit_hook(plugin: str):
    data = _load_plugin_hooks(plugin)
    stop = data.get("Stop") or []
    commands = [
        h["command"]
        for entry in stop
        for h in entry.get("hooks", [])
        if h.get("type") == "command"
    ]
    assert any("audit_phase_quality_on_stop.py" in c for c in commands), (
        f"{plugin} Stop chain missing audit hook: {commands}"
    )


def test_iterate_plugin_orders_audit_after_finalize():
    """Iterate Sonderfall (plan § 5.1): finalize → audit → terminal_marker."""
    data = _load_plugin_hooks("shipwright-iterate")
    stop_hooks = data["Stop"][0]["hooks"]
    commands = [h["command"] for h in stop_hooks]
    idx_finalize = next(i for i, c in enumerate(commands) if "iterate_stop_finalize" in c)
    idx_audit = next(i for i, c in enumerate(commands) if "audit_phase_quality_on_stop" in c)
    idx_terminal = next(i for i, c in enumerate(commands) if "write_terminal_marker" in c)
    assert idx_finalize < idx_audit < idx_terminal


def test_nine_plugins_order_audit_before_handoff():
    """Plan § 5.1: audit runs BEFORE generate_handoff_on_stop for 9 plugins."""
    for plugin in ("shipwright-project", "shipwright-design", "shipwright-plan",
                   "shipwright-build", "shipwright-test", "shipwright-security",
                   "shipwright-deploy", "shipwright-changelog", "shipwright-compliance"):
        data = _load_plugin_hooks(plugin)
        commands = [
            h["command"]
            for entry in data.get("Stop", [])
            for h in entry.get("hooks", [])
        ]
        idx_audit = next(
            (i for i, c in enumerate(commands) if "audit_phase_quality_on_stop" in c),
            None,
        )
        idx_handoff = next(
            (i for i, c in enumerate(commands) if "generate_handoff_on_stop" in c),
            None,
        )
        assert idx_audit is not None, f"{plugin}: audit hook missing"
        assert idx_handoff is not None, f"{plugin}: handoff hook missing"
        assert idx_audit < idx_handoff, (
            f"{plugin}: audit at {idx_audit} must precede handoff at {idx_handoff}"
        )


# ---------------------------------------------------------------------------
# Monorepo Auto-Descent Guard — pure helpers (plan v2)
# ---------------------------------------------------------------------------


# --- cwd_is_strict_ancestor_of ---

def test_strict_ancestor_true_for_parent(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    assert pq.cwd_is_strict_ancestor_of(tmp_path, sub) is True


def test_strict_ancestor_false_when_equal(tmp_path: Path):
    assert pq.cwd_is_strict_ancestor_of(tmp_path, tmp_path) is False


def test_strict_ancestor_false_when_descendant(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    # cwd is descendant, project_root is parent → False (we're inside the managed folder)
    assert pq.cwd_is_strict_ancestor_of(sub, tmp_path) is False


def test_strict_ancestor_false_when_unrelated(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert pq.cwd_is_strict_ancestor_of(a, b) is False


def test_strict_ancestor_follows_symlinks(tmp_path: Path):
    """Path.resolve() should dereference the symlink before ancestry check."""
    actual = tmp_path / "actual"
    actual_sub = actual / "sub"
    actual_sub.mkdir(parents=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/privileges")
    # link/sub should be recognized as descendant of actual → not a strict ancestor
    assert pq.cwd_is_strict_ancestor_of(link / "sub", actual) is False
    # actual should be ancestor of link/sub (since link resolves to actual)
    assert pq.cwd_is_strict_ancestor_of(actual, link / "sub") is True


def test_strict_ancestor_handles_nonexistent_paths(tmp_path: Path):
    """resolve(strict=False) tolerates missing paths; must not raise."""
    ghost_cwd = tmp_path / "ghost-cwd"
    ghost_sub = ghost_cwd / "sub"
    # Neither exists — resolve still returns a path, ancestry check works
    assert pq.cwd_is_strict_ancestor_of(ghost_cwd, ghost_sub) is True
    assert pq.cwd_is_strict_ancestor_of(ghost_sub, ghost_cwd) is False


def test_strict_ancestor_logs_and_returns_false_on_oserror(monkeypatch, capsys, tmp_path: Path):
    """R5 (plan v2) — fail-open + stderr warning when resolve raises."""
    from pathlib import Path as _Path

    def fake_resolve(self, strict=False):
        raise OSError("simulated failure")

    monkeypatch.setattr(_Path, "resolve", fake_resolve)
    assert pq.cwd_is_strict_ancestor_of(tmp_path, tmp_path / "sub") is False
    stderr = capsys.readouterr().err
    assert "cwd_is_strict_ancestor_of" in stderr
    assert "resolve failed" in stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows case-insensitive paths")
def test_strict_ancestor_windows_case_insensitive(tmp_path: Path):
    """On Windows, C:\\Foo\\Bar and C:\\FOO\\bar resolve to the same path."""
    sub = tmp_path / "SubDir"
    sub.mkdir()
    upper_parent = Path(str(tmp_path).upper())
    lower_sub = Path(str(sub).lower())
    assert pq.cwd_is_strict_ancestor_of(upper_parent, lower_sub) is True


# --- project_root_was_explicitly_selected ---

def test_explicit_opt_in_false_when_env_unset(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    assert pq.project_root_was_explicitly_selected(tmp_path) is False


def test_explicit_opt_in_false_on_whitespace_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", "   ")
    assert pq.project_root_was_explicitly_selected(tmp_path) is False


def test_explicit_opt_in_true_on_exact_match(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    assert pq.project_root_was_explicitly_selected(tmp_path) is True


def test_explicit_opt_in_false_on_different_path(monkeypatch, tmp_path: Path):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(other))
    assert pq.project_root_was_explicitly_selected(tmp_path) is False


def test_explicit_opt_in_accepts_relative_env_path(monkeypatch, tmp_path: Path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", "subdir")
    assert pq.project_root_was_explicitly_selected(sub) is True


def test_explicit_opt_in_false_on_invalid_env_path(monkeypatch, tmp_path: Path):
    """Non-existent env paths resolve to an abs path that won't match project_root."""
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", "/definitely-does-not-exist-12345")
    assert pq.project_root_was_explicitly_selected(tmp_path) is False


def test_explicit_opt_in_symlink_resolution(monkeypatch, tmp_path: Path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/privileges")
    # Env points to symlink, project_root is the real path → resolves to same
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(link))
    assert pq.project_root_was_explicitly_selected(actual) is True


# ---------------------------------------------------------------------------
# Monorepo Auto-Descent Guard — E2E (subprocess hook)
# ---------------------------------------------------------------------------


@pytest.fixture
def monorepo_with_managed_subdir(tmp_path: Path) -> tuple[Path, Path]:
    """Create (monorepo_root, managed_subdir) where only the subdir has markers.

    monorepo_root has no agent_docs/ and no config markers → triggers
    auto-descent in resolve_project_root().
    """
    subdir = tmp_path / "managed"
    (subdir / ".shipwright" / "agent_docs").mkdir(parents=True)
    (subdir / "shipwright_run_config.json").write_text(
        json.dumps({
            "run_id": "run-monorepo",
            "current_step": "build",
            "completed_steps": ["project", "design", "plan"],
        }),
        encoding="utf-8",
    )
    events = [
        {"type": "phase_completed", "phase": "build", "timestamp": "2026-04-19T12:00:00Z"},
    ]
    (subdir / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    (subdir / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Dashboard\n\n## build\nsection complete\n",
        encoding="utf-8",
    )
    handoff = subdir / ".shipwright" / "agent_docs" / "session_handoff.md"
    handoff.write_text("# Session Handoff\n\nReason: build: finalize\n", encoding="utf-8")
    now = time.time()
    os.utime(handoff, (now, now))
    (subdir / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- build bullet\n",
        encoding="utf-8",
    )
    (subdir / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "## ADR-001: build decision\n\n**Status:** Accepted\n\nBody.\n",
        encoding="utf-8",
    )
    return tmp_path, subdir


def test_audit_hook_silent_noop_from_monorepo_root(monorepo_with_managed_subdir):
    """Running the hook from monorepo root (auto-descent case) must skip audit."""
    monorepo_root, managed = monorepo_with_managed_subdir
    result = _run_hook(monorepo_root)
    assert result.returncode == 0, result.stderr
    # No finding JSON anywhere (not in monorepo_root, not in managed subdir)
    assert not (monorepo_root / pq.FINDING_DIR).exists()
    assert not (managed / pq.FINDING_DIR).exists()


def test_audit_hook_fires_when_cwd_is_managed_subdir(monorepo_with_managed_subdir):
    """Running from inside managed subdir → audit fires normally."""
    _monorepo_root, managed = monorepo_with_managed_subdir
    result = _run_hook(managed)
    assert result.returncode == 0, result.stderr
    finding_dir = managed / pq.FINDING_DIR
    assert finding_dir.is_dir()
    assert list(finding_dir.glob("*.json"))


def test_audit_hook_fires_when_env_var_points_to_project_root(monorepo_with_managed_subdir):
    """Explicit opt-in via SHIPWRIGHT_PROJECT_ROOT resolving to the managed subdir."""
    monorepo_root, managed = monorepo_with_managed_subdir
    result = _run_hook(
        monorepo_root,
        extra_env={"SHIPWRIGHT_PROJECT_ROOT": str(managed)},
    )
    assert result.returncode == 0, result.stderr
    # Finding written despite cwd != project_root
    finding_dir = managed / pq.FINDING_DIR
    assert finding_dir.is_dir()
    assert list(finding_dir.glob("*.json"))


def test_audit_hook_silent_noop_when_env_var_ambient_unrelated(
    monorepo_with_managed_subdir, tmp_path: Path
):
    """Ambient env (points elsewhere) must NOT bypass the auto-descent guard."""
    monorepo_root, managed = monorepo_with_managed_subdir
    unrelated = tmp_path / "unrelated-no-markers"
    unrelated.mkdir()
    result = _run_hook(
        monorepo_root,
        extra_env={"SHIPWRIGHT_PROJECT_ROOT": str(unrelated)},
    )
    assert result.returncode == 0, result.stderr
    # No finding (resolver fell through to auto-descent, opt-in didn't match)
    assert not (managed / pq.FINDING_DIR).exists()


def test_audit_hook_silent_noop_when_env_var_whitespace(monorepo_with_managed_subdir):
    """Whitespace-only env is treated as unset → guard fires."""
    monorepo_root, managed = monorepo_with_managed_subdir
    result = _run_hook(
        monorepo_root,
        extra_env={"SHIPWRIGHT_PROJECT_ROOT": "   "},
    )
    assert result.returncode == 0, result.stderr
    assert not (managed / pq.FINDING_DIR).exists()
