"""Tests for the Phase-Quality infrastructure category (PR 3 — I1-I4).

Covers each check with positive and negative fixtures plus the plan § 7
risk relevant to this PR:

- R11 — Infrastructure checks must SKIP (not FAIL) when the anchor
  ``phase_started`` / ``phase_completed`` event is missing, so mid-flow
  audits don't spike the dashboard with spurious FAILs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import infrastructure_checks as ic  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_events(proj: Path, events: list[dict[str, Any]]) -> None:
    (proj / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _write_doc(proj: Path, relpath: str, *, mtime_offset_seconds: float = 0.0) -> Path:
    path = proj / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# doc\n", encoding="utf-8")
    if mtime_offset_seconds:
        future = time.time() + mtime_offset_seconds
        os.utime(path, (future, future))
    return path


def _past_iso(seconds_ago: int) -> str:
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat(
        timespec="seconds",
    )


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "agent_docs").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# latest_phase_event_epoch (helper used by I1-I4)
# ---------------------------------------------------------------------------


def test_latest_phase_event_epoch_returns_none_without_events(proj: Path):
    assert ic.latest_phase_event_epoch(proj, "build", "phase_started") is None


def test_latest_phase_event_epoch_picks_max_ts(proj: Path):
    _write_events(proj, [
        {"type": "phase_started", "phase": "build", "ts": _past_iso(300)},
        {"type": "phase_started", "phase": "build", "ts": _past_iso(60)},
        {"type": "phase_started", "phase": "test",  "ts": _past_iso(10)},
    ])
    epoch = ic.latest_phase_event_epoch(proj, "build", "phase_started")
    assert epoch is not None


def test_latest_phase_event_epoch_accepts_source_field(proj: Path):
    _write_events(proj, [
        {"type": "phase_started", "source": "build", "ts": _past_iso(60)},
    ])
    assert ic.latest_phase_event_epoch(proj, "build", "phase_started") is not None


# ---------------------------------------------------------------------------
# I1 — RTM freshness vs phase_completed
# ---------------------------------------------------------------------------


def test_i1_fails_without_rtm_file(proj: Path):
    f = ic.check_i1_rtm_fresh(proj, "build")
    assert f["id"] == "I1"
    assert f["status"] == pq.STATUS_FAIL
    assert f.get("remediation")


def test_i1_skips_when_no_phase_completed_event(proj: Path):
    # R11 — mid-flow audit with doc but no event yet must SKIP, not FAIL.
    _write_doc(proj, "compliance/traceability-matrix.md")
    f = ic.check_i1_rtm_fresh(proj, "build")
    assert f["status"] == pq.STATUS_SKIP
    assert f["provenance"] == "unverified_marker"


def test_i1_fails_when_rtm_stale(proj: Path):
    _write_doc(proj, "compliance/traceability-matrix.md")
    _write_events(proj, [
        {"type": "phase_completed", "phase": "build", "ts": _past_iso(-3600)},
    ])
    f = ic.check_i1_rtm_fresh(proj, "build")
    assert f["status"] == pq.STATUS_FAIL
    assert "stale" not in f["evidence"].lower() or "older" in f["evidence"].lower()


def test_i1_passes_when_rtm_newer_than_event(proj: Path):
    _write_events(proj, [
        {"type": "phase_completed", "phase": "build", "ts": _past_iso(600)},
    ])
    _write_doc(proj, "compliance/traceability-matrix.md")
    f = ic.check_i1_rtm_fresh(proj, "build")
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# I2 — test-evidence freshness vs phase_started
# ---------------------------------------------------------------------------


def test_i2_fails_without_evidence_file(proj: Path):
    f = ic.check_i2_test_evidence_fresh(proj, "test")
    assert f["status"] == pq.STATUS_FAIL


def test_i2_skips_without_phase_started_event(proj: Path):
    _write_doc(proj, "compliance/test-evidence.md")
    f = ic.check_i2_test_evidence_fresh(proj, "test")
    assert f["status"] == pq.STATUS_SKIP


def test_i2_passes_with_fresh_doc(proj: Path):
    _write_events(proj, [
        {"type": "phase_started", "phase": "test", "ts": _past_iso(600)},
    ])
    _write_doc(proj, "compliance/test-evidence.md")
    f = ic.check_i2_test_evidence_fresh(proj, "test")
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# I3 — change-history freshness vs phase_started
# ---------------------------------------------------------------------------


def test_i3_fails_without_doc(proj: Path):
    f = ic.check_i3_change_history_fresh(proj, "changelog")
    assert f["status"] == pq.STATUS_FAIL


def test_i3_skips_without_event(proj: Path):
    _write_doc(proj, "compliance/change-history.md")
    f = ic.check_i3_change_history_fresh(proj, "changelog")
    assert f["status"] == pq.STATUS_SKIP


def test_i3_fails_when_stale(proj: Path):
    _write_doc(proj, "compliance/change-history.md")
    _write_events(proj, [
        {"type": "phase_started", "phase": "changelog", "ts": _past_iso(-3600)},
    ])
    f = ic.check_i3_change_history_fresh(proj, "changelog")
    assert f["status"] == pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# I4 — SBOM freshness on dependency change (Tier-2)
# ---------------------------------------------------------------------------


def test_i4_skips_when_no_dep_manifest(proj: Path):
    f = ic.check_i4_sbom_fresh_on_dep_change(proj, "build")
    assert f["status"] == pq.STATUS_SKIP
    assert f.get("tier") == 2


def test_i4_warns_when_sbom_missing_but_deps_present(proj: Path):
    (proj / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    f = ic.check_i4_sbom_fresh_on_dep_change(proj, "build")
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2


def test_i4_skips_when_sbom_newer_than_all_deps(proj: Path):
    (proj / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    _write_doc(proj, "compliance/sbom.md", mtime_offset_seconds=120)
    f = ic.check_i4_sbom_fresh_on_dep_change(proj, "build")
    assert f["status"] == pq.STATUS_SKIP


def test_i4_warns_when_deps_newer_than_sbom(proj: Path):
    _write_doc(proj, "compliance/sbom.md")
    sbom_mtime = (proj / "compliance" / "sbom.md").stat().st_mtime
    pyproject = proj / "pyproject.toml"
    pyproject.write_text("[project]\n", encoding="utf-8")
    future = sbom_mtime + 120
    os.utime(pyproject, (future, future))
    f = ic.check_i4_sbom_fresh_on_dep_change(proj, "build")
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2
    assert "pyproject.toml" in f["evidence"]


def test_i4_never_fails(proj: Path):
    """Plan § 3 — I4 is Tier-2 and must never FAIL under any input."""
    for setup in (
        lambda: None,
        lambda: (proj / "pyproject.toml").write_text("x", encoding="utf-8"),
        lambda: _write_doc(proj, "compliance/sbom.md"),
    ):
        setup()
        f = ic.check_i4_sbom_fresh_on_dep_change(proj, "build")
        assert f["status"] != pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# Phase-gating dispatcher
# ---------------------------------------------------------------------------


def test_run_dispatch_build_returns_all_four_checks(proj: Path):
    findings = ic.run("build", proj)
    ids = {f["id"] for f in findings}
    assert ids == {"I1", "I2", "I3", "I4"}


def test_run_dispatch_test_only_returns_i2(proj: Path):
    findings = ic.run("test", proj)
    assert [f["id"] for f in findings] == ["I2"]


def test_run_dispatch_changelog_only_returns_i3(proj: Path):
    findings = ic.run("changelog", proj)
    assert [f["id"] for f in findings] == ["I3"]


def test_run_dispatch_unrelated_phase_returns_empty(proj: Path):
    assert ic.run("deploy", proj) == []
    assert ic.run("design", proj) == []


# ---------------------------------------------------------------------------
# phase_quality.run_infrastructure_checks (phase-gated dispatcher)
# ---------------------------------------------------------------------------


def test_phase_quality_dispatches_infrastructure(proj: Path):
    # Empty project — wrapper should surface SKIPs/FAILs without crashing.
    findings = pq.run_infrastructure_checks("build", proj)
    assert {f["id"] for f in findings} == {"I1", "I2", "I3", "I4"}


def test_phase_quality_returns_empty_for_uncovered_phase(proj: Path):
    assert pq.run_infrastructure_checks("project", proj) == []
