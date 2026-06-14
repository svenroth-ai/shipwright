"""Layer 1 (phase-applicability) + collect_in_scope_fails unit tests.

Covers iterate spec AC-1, AC-1b, AC-2, AC-3 (engagement predicate) and the
latest-finding-per-phase / multi-code / Tier-2 / filter behavior of
``collect_in_scope_fails``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


# --- phase_is_engaged ---------------------------------------------------

def test_engaged_via_phase_completed_event() -> None:
    events = [{"type": "phase_completed", "source": "design"}]
    assert pq.phase_is_engaged("design", {"status": "complete"}, events) is True


def test_engaged_via_phase_field_on_event() -> None:
    events = [{"type": "phase_completed", "phase": "build"}]
    assert pq.phase_is_engaged("build", {"status": "complete"}, events) is True


def test_engaged_via_work_completed_source() -> None:
    events = [{"type": "work_completed", "source": "iterate"}]
    assert pq.phase_is_engaged("iterate", {"status": "in_progress"}, events) is True


def test_iterate_engaged_when_complete() -> None:
    assert pq.phase_is_engaged("iterate", {"status": "complete"}, []) is True


def test_in_progress_completed_step_engaged() -> None:
    cfg = {"status": "in_progress", "completed_steps": ["project", "plan"]}
    assert pq.phase_is_engaged("plan", cfg, []) is True


def test_in_progress_current_step_engaged() -> None:
    cfg = {"status": "in_progress", "current_step": "build", "completed_steps": []}
    assert pq.phase_is_engaged("build", cfg, []) is True


def test_complete_completed_step_without_event_not_engaged() -> None:
    # AC-2: completed_steps grants engagement only while in progress.
    cfg = {"status": "complete", "completed_steps": ["build"]}
    assert pq.phase_is_engaged("build", cfg, []) is False


def test_complete_stale_current_step_not_engaged() -> None:
    # AC-2: a stale current_step on a finished run must NOT re-admit a phase.
    cfg = {"status": "complete", "current_step": "design", "completed_steps": []}
    assert pq.phase_is_engaged("design", cfg, []) is False


def test_status_casing_normalized() -> None:
    assert pq.phase_is_engaged("iterate", {"status": "Complete"}, []) is True


def test_unengaged_phase_with_unrelated_event() -> None:
    events = [{"type": "phase_completed", "source": "changelog"}]
    cfg = {"status": "complete"}
    assert pq.phase_is_engaged("deploy", cfg, events) is False


def test_fail_open_when_cfg_none() -> None:
    # AC-1b: unreadable run_config → engaged (never swallow alerts).
    assert pq.phase_is_engaged("deploy", None, []) is True


# --- resolve_engaged_phases (session-state phase resolver) ----------------

def _write_cfg(project: Path, cfg: dict) -> None:
    (project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8")


def test_resolve_engaged_returns_engaged_only(project: Path) -> None:
    # in_progress, current_step=build, project+plan done → exactly those three.
    _write_cfg(project, {
        "status": "in_progress", "current_step": "build",
        "completed_steps": ["project", "plan"],
    })
    engaged = pq.resolve_engaged_phases(project)
    assert set(engaged) == {"project", "plan", "build"}
    # phases that did not run are excluded (this is the whole point — no longer
    # auditing all 11 plugins' phases from the fan-out).
    assert "deploy" not in engaged and "security" not in engaged


def test_resolve_engaged_complete_project_is_iterate_only(project: Path) -> None:
    # A finished project's only always-on phase is iterate (matches what runs).
    _write_cfg(project, {"status": "complete"})
    assert pq.resolve_engaged_phases(project) == ["iterate"]


def test_resolve_engaged_via_event_source(project: Path) -> None:
    # Standalone phase run whose only evidence is a work_completed event.
    _write_cfg(project, {"status": "complete"})
    (project / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "source": "build"}) + "\n",
        encoding="utf-8")
    engaged = pq.resolve_engaged_phases(project)
    assert "build" in engaged and "iterate" in engaged


def test_resolve_engaged_fail_open_when_cfg_missing(project: Path) -> None:
    # No run config → cannot determine → ALL canonical phases (never fewer).
    engaged = pq.resolve_engaged_phases(project)
    assert set(engaged) == set(pq.PLUGIN_TO_PHASE.values())


def test_resolve_engaged_fail_open_when_cfg_malformed(project: Path) -> None:
    (project / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    engaged = pq.resolve_engaged_phases(project)
    assert set(engaged) == set(pq.PLUGIN_TO_PHASE.values())


def test_resolve_engaged_fail_open_when_events_unreadable(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # cfg valid, but the event log EXISTS and raises on read (partial flush /
    # OSError) → insufficient evidence → ALL phases. "Never fewer" under stale
    # end-of-session state (external-review gpt#5 / gem#1).
    _write_cfg(project, {
        "status": "in_progress", "current_step": "build", "completed_steps": [],
    })
    (project / "shipwright_events.jsonl").write_text("{}", encoding="utf-8")
    orig_read = Path.read_text

    def boom(self: Path, *a: object, **k: object) -> str:
        if self.name == "shipwright_events.jsonl":
            raise OSError("simulated partial flush")
        return orig_read(self, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", boom)
    engaged = pq.resolve_engaged_phases(project)
    assert set(engaged) == set(pq.PLUGIN_TO_PHASE.values())


def test_resolve_engaged_absent_events_not_failopen(project: Path) -> None:
    # A genuinely ABSENT event log is NOT "unreadable": cfg-based engagement
    # still applies, so we get the engaged set, not the full fail-open set.
    _write_cfg(project, {
        "status": "in_progress", "current_step": "test", "completed_steps": [],
    })
    engaged = pq.resolve_engaged_phases(project)
    assert engaged == ["test"]


# --- load_engagement_inputs fail-open -----------------------------------

def test_load_inputs_missing_config_returns_none(project: Path) -> None:
    cfg, events = pq.load_engagement_inputs(project)
    assert cfg is None and events == []


def test_load_inputs_malformed_config_returns_none(project: Path) -> None:
    (project / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    cfg, _ = pq.load_engagement_inputs(project)
    assert cfg is None  # malformed → None → fail-open downstream


# --- collect_in_scope_fails ---------------------------------------------

def _write_run_config(project: Path, **kw: object) -> None:
    import json
    (project / "shipwright_run_config.json").write_text(
        json.dumps(kw), encoding="utf-8")


def _write_events(project: Path, events: list[dict]) -> None:
    import json
    (project / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8")


def _finding(code: str, status: str = "FAIL", *, tier: int | None = None,
             remediation: str = "") -> dict:
    f = {"id": code, "name": f"{code} check", "status": status,
         "evidence": "e", "remediation": remediation}
    if tier is not None:
        f["tier"] = tier
    return f


def test_collect_multi_code_per_phase_engaged(project: Path) -> None:
    """A phase's latest finding holds all its codes (C1 AND D1) — both surface."""
    _write_events(project, [{"type": "phase_completed", "source": "design"}])
    _write_run_config(project, status="complete")
    pq.write_finding_json(
        project, "design", "r1", "s1",
        {"canon": [_finding("C1"), _finding("D1")]},
    )
    fails = pq.collect_in_scope_fails(project)
    keys = {f"{d['phase']}:{d['code']}" for d in fails}
    assert keys == {"design:C1", "design:D1"}


def test_collect_filters_unengaged_phase(project: Path) -> None:
    _write_run_config(project, status="complete")  # deploy not engaged
    pq.write_finding_json(project, "deploy", "r1", "s1", {"canon": [_finding("C1")]})
    assert pq.collect_in_scope_fails(project) == []


def test_collect_excludes_tier2(project: Path) -> None:
    _write_run_config(project, status="complete")
    pq.write_finding_json(
        project, "iterate", "r1", "s1",
        {"workflow": [_finding("C1"), _finding("W1", tier=2)]},
    )
    keys = {d["code"] for d in pq.collect_in_scope_fails(project)}
    assert keys == {"C1"}


def test_collect_excludes_pass_and_skip(project: Path) -> None:
    _write_run_config(project, status="complete")
    pq.write_finding_json(
        project, "iterate", "r1", "s1",
        {"canon": [_finding("C1", status="PASS"), _finding("C2", status="SKIP")]},
    )
    assert pq.collect_in_scope_fails(project) == []


def test_collect_latest_finding_per_phase_wins(project: Path) -> None:
    _write_run_config(project, status="complete")
    pq.write_finding_json(project, "iterate", "old", "s1",
                          {"canon": [_finding("C1")]}, audited_at="2026-01-01T00:00:00+00:00")
    pq.write_finding_json(project, "iterate", "new", "s1",
                          {"canon": [_finding("C5")]}, audited_at="2026-05-31T00:00:00+00:00")
    keys = {d["code"] for d in pq.collect_in_scope_fails(project)}
    assert keys == {"C5"}  # newest finding only


def test_collect_fail_open_without_run_config(project: Path) -> None:
    # No run_config → cfg None → every phase engaged → FAILs surface.
    pq.write_finding_json(project, "deploy", "r1", "s1", {"canon": [_finding("C1")]})
    keys = {f"{d['phase']}:{d['code']}" for d in pq.collect_in_scope_fails(project)}
    assert keys == {"deploy:C1"}


def test_collect_excludes_provenance_error(project: Path) -> None:
    # review MEDIUM: a synthetic category-runner-crash FAIL (provenance=error)
    # must not enter the in-scope set (would pollute the signature + churn).
    _write_run_config(project, status="complete")
    crash = {"id": "WF-iterate", "name": "workflow runner", "status": "FAIL",
             "evidence": "wrapper crashed", "provenance": "error"}
    pq.write_finding_json(project, "iterate", "r1", "s1",
                          {"workflow": [crash, _finding("C1")]})
    keys = {d["code"] for d in pq.collect_in_scope_fails(project)}
    assert keys == {"C1"}  # WF-iterate excluded


def test_collect_error_source_finding_does_not_mask_real_fail(project: Path) -> None:
    # review LOW-1: a crashed hook-level audit (source=error, empty categories)
    # is the newest finding for the phase, but must NOT mask the prior real FAIL.
    _write_run_config(project, status="complete")
    pq.write_finding_json(project, "iterate", "old", "s1", {"canon": [_finding("C1")]},
                          audited_at="2026-01-01T00:00:00+00:00")
    pq.write_finding_json(project, "iterate", "err", "s1", {}, source="error",
                          audited_at="2026-05-31T00:00:00+00:00")
    keys = {d["code"] for d in pq.collect_in_scope_fails(project)}
    assert keys == {"C1"}  # older real FAIL still surfaces
