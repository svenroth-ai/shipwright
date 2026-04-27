"""Tests for the Phase-Quality traceability category (PR 3 — T1, T2).

Covers positive + negative fixtures plus plan § 7 R12 — T2 must WARN,
not FAIL, when RTM references FR ids not backed by a spec (renames and
partial checkouts produce legitimate orphans).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import traceability_checks as tc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_spec(proj: Path, split: str, rows: list[tuple[str, str, str]]) -> None:
    split_dir = proj / ".shipwright" / "planning" / split
    split_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {split} spec",
        "",
        "| ID | Description | Priority |",
        "|----|-------------|----------|",
    ]
    for fr_id, desc, prio in rows:
        lines.append(f"| {fr_id} | {desc} | {prio} |")
    (split_dir / "spec.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_rtm(proj: Path, fr_ids: list[str]) -> None:
    compliance = proj / "compliance"
    compliance.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Requirements Traceability Matrix",
        "",
        "| Requirement | Title | Status |",
        "|---|---|---|",
    ]
    for fr_id in fr_ids:
        lines.append(f"| {fr_id} | something | COVERED |")
    (compliance / "traceability-matrix.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# T1 — every spec FR mapped in RTM
# ---------------------------------------------------------------------------


def test_t1_skips_without_planning_tree(proj: Path):
    f = tc.check_t1_all_spec_frs_mapped(proj)
    assert f["id"] == "T1"
    assert f["status"] == pq.STATUS_SKIP


def test_t1_skips_when_spec_has_no_frs(proj: Path):
    (proj / ".shipwright" / "planning" / "01-core").mkdir(parents=True)
    (proj / ".shipwright" / "planning" / "01-core" / "spec.md").write_text(
        "# spec\n\nNo FRs here.\n", encoding="utf-8",
    )
    f = tc.check_t1_all_spec_frs_mapped(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_t1_fails_when_rtm_missing(proj: Path):
    _write_spec(proj, "01-core", [("FR-01.01", "x", "Must")])
    f = tc.check_t1_all_spec_frs_mapped(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "missing" in f["evidence"].lower()


def test_t1_fails_on_unmapped_frs(proj: Path):
    _write_spec(proj, "01-core", [
        ("FR-01.01", "a", "Must"),
        ("FR-01.02", "b", "Must"),
        ("FR-01.03", "c", "Must"),
    ])
    _write_rtm(proj, ["FR-01.01"])
    f = tc.check_t1_all_spec_frs_mapped(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "FR-01.02" in f["evidence"]
    assert "FR-01.03" in f["evidence"]
    assert f.get("remediation")


def test_t1_passes_when_all_frs_mapped(proj: Path):
    _write_spec(proj, "01-core", [
        ("FR-01.01", "a", "Must"),
        ("FR-01.02", "b", "Should"),
    ])
    _write_rtm(proj, ["FR-01.01", "FR-01.02"])
    f = tc.check_t1_all_spec_frs_mapped(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# T2 — no orphan RTM rows (Tier-2, WARN-only per R12)
# ---------------------------------------------------------------------------


def test_t2_skips_without_planning(proj: Path):
    f = tc.check_t2_no_orphan_rtm_rows(proj)
    assert f["status"] == pq.STATUS_SKIP
    assert f.get("tier") == 2


def test_t2_skips_without_rtm(proj: Path):
    _write_spec(proj, "01-core", [("FR-01.01", "a", "Must")])
    f = tc.check_t2_no_orphan_rtm_rows(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_t2_warns_on_orphans_never_fails(proj: Path):
    _write_spec(proj, "01-core", [("FR-01.01", "a", "Must")])
    _write_rtm(proj, ["FR-01.01", "FR-99.99"])
    f = tc.check_t2_no_orphan_rtm_rows(proj)
    # R12 — Tier-2, never FAIL.
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2
    assert "FR-99.99" in f["evidence"]
    assert f["provenance"] == "unverified_marker"


def test_t2_passes_when_rtm_is_subset_of_spec(proj: Path):
    _write_spec(proj, "01-core", [
        ("FR-01.01", "a", "Must"),
        ("FR-01.02", "b", "Must"),
    ])
    _write_rtm(proj, ["FR-01.01"])
    f = tc.check_t2_no_orphan_rtm_rows(proj)
    assert f["status"] == pq.STATUS_PASS


def test_t2_never_fails_under_any_adverse_input(proj: Path):
    # R12 — no input permutation produces FAIL.
    cases = [
        lambda: None,
        lambda: _write_spec(proj, "01-core", [("FR-01.01", "a", "Must")]),
        lambda: _write_rtm(proj, ["FR-99.99"]),
    ]
    for setup in cases:
        setup()
        f = tc.check_t2_no_orphan_rtm_rows(proj)
        assert f["status"] != pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# Phase-gating dispatcher
# ---------------------------------------------------------------------------


def test_run_dispatch_project(proj: Path):
    assert {f["id"] for f in tc.run("project", proj)} == {"T1", "T2"}


def test_run_dispatch_iterate(proj: Path):
    assert {f["id"] for f in tc.run("iterate", proj)} == {"T1", "T2"}


def test_run_dispatch_unrelated_phase_returns_empty(proj: Path):
    assert tc.run("build", proj) == []
    assert tc.run("design", proj) == []


def test_phase_quality_dispatches_traceability(proj: Path):
    findings = pq.run_traceability_checks("iterate", proj)
    assert {f["id"] for f in findings} == {"T1", "T2"}


def test_phase_quality_traceability_empty_for_uncovered(proj: Path):
    assert pq.run_traceability_checks("build", proj) == []
