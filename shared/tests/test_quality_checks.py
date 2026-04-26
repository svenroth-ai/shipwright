"""Tests for the Phase-Quality quality category (PR 3 — Q1, Q2).

Covers positive + negative fixtures plus plan § 7 risks:

- R13 — Q1 thresholds must be forgiving enough that a real, terse ADR
  passes; must WARN (never FAIL) on thin content.
- R14 — Q2 must SKIP (not FAIL) when plan material isn't present yet
  (fresh project, pre-build-start).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import adr_parser  # noqa: E402
from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import quality_checks as qc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_decision_log(proj: Path, content: str) -> None:
    (proj / "agent_docs").mkdir(exist_ok=True)
    (proj / "agent_docs" / "decision_log.md").write_text(content, encoding="utf-8")


def _bullet_adr(adr_id: str, *, context: str, decision: str, consequences: str) -> str:
    return (
        f"### {adr_id}: Sample\n"
        f"- **Date:** 2026-04-18\n"
        f"- **Context:** {context}\n"
        f"- **Decision:** {decision}\n"
        f"- **Consequences:** {consequences}\n"
    )


def _section_adr(adr_id: str, *, context: str, decision: str, consequences: str) -> str:
    return (
        f"### {adr_id}: Sample\n\n"
        f"**Context**\n{context}\n\n"
        f"**Decision**\n{decision}\n\n"
        f"**Consequences**\n{consequences}\n"
    )


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "agent_docs").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# adr_parser — body extraction (sanity)
# ---------------------------------------------------------------------------


def test_adr_parser_handles_bullet_form():
    md = "# Decision Log\n\n" + _bullet_adr(
        "ADR-001",
        context="Some meaningful context describing the problem at hand",
        decision="We chose option A for these reasons",
        consequences="Tests stay green; doc debt low",
    )
    body = adr_parser.latest_adr_body(md)
    assert body is not None
    assert body.header.id == "ADR-001"
    assert "meaningful context" in body.get("context")
    assert body.get("decision").startswith("We chose option A")
    assert body.get("consequences")


def test_adr_parser_handles_section_form():
    md = "# Decision Log\n\n" + _section_adr(
        "ADR-002",
        context="Context as a paragraph block of reasonable length",
        decision="Section-form decision of reasonable length",
        consequences="Section-form consequences of reasonable length",
    )
    body = adr_parser.latest_adr_body(md)
    assert body is not None
    assert "paragraph block" in body.get("context")
    assert "Section-form decision" in body.get("decision")


def test_adr_parser_returns_latest_when_multiple_adrs():
    md = "\n".join([
        "# Decision Log",
        _bullet_adr("ADR-001", context="first ctx long enough for threshold",
                    decision="first decision", consequences="first consequences"),
        _bullet_adr("ADR-002", context="second ctx long enough for threshold",
                    decision="second decision", consequences="second consequences"),
    ])
    body = adr_parser.latest_adr_body(md)
    assert body is not None
    assert body.header.id == "ADR-002"


# ---------------------------------------------------------------------------
# Q1 — ADR substance (Tier-2, WARN-only)
# ---------------------------------------------------------------------------


def test_q1_skips_when_log_missing(proj: Path):
    f = qc.check_q1_adr_substance(proj)
    assert f["id"] == "Q1"
    assert f["status"] == pq.STATUS_SKIP


def test_q1_skips_when_no_adrs_parsed(proj: Path):
    _write_decision_log(proj, "# Decision Log\n\nNothing here.\n")
    f = qc.check_q1_adr_substance(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_q1_warns_on_thin_content(proj: Path):
    _write_decision_log(proj, _bullet_adr(
        "ADR-001", context="too short", decision="x", consequences="y",
    ))
    f = qc.check_q1_adr_substance(proj)
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2
    assert f["provenance"] == "unverified_marker"
    assert "Context" in f["evidence"]


def test_q1_passes_on_substantive_adr(proj: Path):
    _write_decision_log(proj, _bullet_adr(
        "ADR-007",
        context="This is a meaningful context string long enough to pass the threshold easily.",
        decision="We chose option Alpha because it keeps the invariant.",
        consequences="Tests stay green and downstream docs track the change.",
    ))
    f = qc.check_q1_adr_substance(proj)
    assert f["status"] == pq.STATUS_PASS
    assert "ADR-007" in f["evidence"]


def test_q1_never_fails_even_on_empty_sections(proj: Path):
    # R13 — Q1 is Tier-2 heuristic; no input combo may FAIL.
    for content in (
        _bullet_adr("ADR-001", context="", decision="", consequences=""),
        _section_adr("ADR-002", context="x", decision="y", consequences="z"),
    ):
        _write_decision_log(proj, content)
        f = qc.check_q1_adr_substance(proj)
        assert f["status"] != pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# Q2 — plan sections ⊆ build.sections (complete)
# ---------------------------------------------------------------------------


def _write_plan_snapshot(proj: Path, sections: list[str]) -> None:
    (proj / "shipwright_plan_snapshot.json").write_text(
        json.dumps({"sections": sections}), encoding="utf-8",
    )


def _write_build_config(proj: Path, sections: list[dict]) -> None:
    (proj / "shipwright_build_config.json").write_text(
        json.dumps({"sections": sections}), encoding="utf-8",
    )


def test_q2_skips_without_plan_material(proj: Path):
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["id"] == "Q2"
    assert f["status"] == pq.STATUS_SKIP


def test_q2_fails_when_build_config_missing(proj: Path):
    _write_plan_snapshot(proj, ["01-auth", "02-dashboard"])
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "shipwright_build_config.json" in f["evidence"]


def test_q2_fails_on_missing_section(proj: Path):
    _write_plan_snapshot(proj, ["01-auth", "02-dashboard"])
    _write_build_config(proj, [
        {"name": "01-auth", "status": "complete"},
    ])
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "02-dashboard" in f["evidence"]


def test_q2_fails_on_incomplete_section(proj: Path):
    _write_plan_snapshot(proj, ["01-auth"])
    _write_build_config(proj, [
        {"name": "01-auth", "status": "in_progress"},
    ])
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "in_progress" in f["evidence"]


def test_q2_passes_when_all_planned_sections_complete(proj: Path):
    _write_plan_snapshot(proj, ["01-auth", "02-dashboard"])
    _write_build_config(proj, [
        {"name": "01-auth", "status": "complete"},
        {"name": "02-dashboard", "status": "done"},
        {"name": "99-extra", "status": "complete"},  # extras are OK
    ])
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS


def test_q2_derives_plan_from_planning_tree_when_no_snapshot(proj: Path):
    (proj / ".shipwright" / "planning" / "sections").mkdir(parents=True)
    (proj / ".shipwright" / "planning" / "sections" / "01-auth.md").write_text("x", encoding="utf-8")
    (proj / ".shipwright" / "planning" / "sections" / "02-dashboard.md").write_text("x", encoding="utf-8")
    _write_build_config(proj, [
        {"name": "01-auth", "status": "complete"},
        {"name": "02-dashboard", "status": "complete"},
    ])
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS


def test_q2_handles_split_planning_layout(proj: Path):
    for split in ("01-core", "02-ui"):
        (proj / ".shipwright" / "planning" / split / "sections").mkdir(parents=True)
        (proj / ".shipwright" / "planning" / split / "sections" / f"{split}-a.md").write_text(
            "x", encoding="utf-8",
        )
    _write_build_config(proj, [
        {"name": "01-core-a", "status": "complete"},
        {"name": "02-ui-a", "status": "complete"},
    ])
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# Phase-gating dispatcher
# ---------------------------------------------------------------------------


def test_run_build_phase_returns_q1_and_q2(proj: Path):
    findings = qc.run("build", proj)
    assert {f["id"] for f in findings} == {"Q1", "Q2"}


def test_run_project_phase_returns_q1_only(proj: Path):
    assert [f["id"] for f in qc.run("project", proj)] == ["Q1"]


def test_run_plan_phase_returns_q1_only(proj: Path):
    assert [f["id"] for f in qc.run("plan", proj)] == ["Q1"]


def test_run_iterate_phase_returns_q1_only(proj: Path):
    assert [f["id"] for f in qc.run("iterate", proj)] == ["Q1"]


def test_run_unrelated_phase_returns_empty(proj: Path):
    assert qc.run("test", proj) == []
    assert qc.run("deploy", proj) == []


def test_phase_quality_dispatches_quality(proj: Path):
    findings = pq.run_quality_checks("build", proj)
    assert {f["id"] for f in findings} == {"Q1", "Q2"}


def test_phase_quality_quality_empty_for_uncovered(proj: Path):
    assert pq.run_quality_checks("security", proj) == []
