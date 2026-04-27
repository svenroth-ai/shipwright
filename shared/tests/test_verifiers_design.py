"""Tests for shared/scripts/tools/verifiers/design_checks.py."""

from __future__ import annotations

import json
from pathlib import Path

from tools.verifiers.common import Severity
from tools.verifiers.design_checks import (
    _parse_screens_table,
    check_design_fr_coverage,
    check_design_manifest_screens_exist,
    run_design_checks,
)


def seed_canon_design(
    root: Path,
    *,
    screens: list[tuple[str, list[str]]] | None = None,
    run_id: str = "design-20260414-test",
    write_canon_artifacts: bool = True,
) -> None:
    """Seed a minimally-valid design project. ``screens`` entries are
    ``(filename, linked_fr_ids)`` tuples — the fixture creates each
    file so ``check_design_manifest_screens_exist`` passes."""
    screens = screens or [
        ("screens/01-login.html", ["FR-01.01"]),
        ("screens/02-dashboard.html", ["FR-02.01"]),
    ]

    # Planning FRs — spec.md tables the FR parser consumes
    (root / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (root / ".shipwright" / "planning" / "01-auth" / "spec.md").write_text(
        "| FR-01.01 | User can log in | Must |\n"
    )
    (root / ".shipwright" / "planning" / "02-dashboard").mkdir()
    (root / ".shipwright" / "planning" / "02-dashboard" / "spec.md").write_text(
        "| FR-02.01 | Show metrics | Must |\n"
    )

    # Design manifest with the Screens table
    (root / ".shipwright" / "designs").mkdir()
    (root / ".shipwright" / "designs" / "screens").mkdir()
    rows = []
    for idx, (fname, frs) in enumerate(screens, start=1):
        (root / ".shipwright" / "designs" / fname).parent.mkdir(parents=True, exist_ok=True)
        (root / ".shipwright" / "designs" / fname).write_text("<html>mock</html>")
        fr_cell = ", ".join(frs) if frs else "none"
        # filename stem becomes the display name
        rows.append(f"| {idx:02d} | {Path(fname).stem} | {fname} | complete | {fr_cell} |")
    manifest_body = (
        "# Design Manifest\n\n"
        "## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n"
        "|---|--------|------|--------|-----------|\n"
        + "\n".join(rows) + "\n"
    )
    (root / ".shipwright" / "designs" / "design-manifest.md").write_text(manifest_body)

    if not write_canon_artifacts:
        return

    # C1 event
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "phase_completed", "phase": "design",
                    "timestamp": "2026-04-14T10:00:00Z"}) + "\n"
    )
    # C2 dashboard
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("- design: complete\n")
    # C3 handoff
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")
    # C4 is skipped for design by policy
    # C5 changelog
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- Design: 2 screens + 0 flows added\n"
    )
    # phase_history + ADR baseline for F1/F2/F3
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"design": [{"run_id": run_id, "date": "2026-04-14"}]},
    }))
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: Anchor\n- **Status:** accepted\n"
    )


# ---------------------------------------------------------------------------
# _parse_screens_table
# ---------------------------------------------------------------------------

def test_parse_screens_table_extracts_file_and_frs():
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n"
        "|---|--------|------|--------|-----------|\n"
        "| 01 | Login | screens/01-login.html | complete | FR-01.01, FR-01.02 |\n"
        "| 02 | Dashboard | screens/02-dashboard.html | complete | FR-02.01 |\n"
        "\n## User Flows\n"
    )
    rows = _parse_screens_table(md)
    assert len(rows) == 2
    assert rows[0][0] == "screens/01-login.html"
    assert set(rows[0][1]) == {"FR-01.01", "FR-01.02"}
    assert rows[1][1] == ["FR-02.01"]


def test_parse_screens_table_treats_none_as_empty_fr_list():
    md = (
        "## Screens\n\n"
        "|---|---|---|---|---|\n"
        "| 01 | Logo | screens/logo.html | complete | none |\n"
    )
    rows = _parse_screens_table(md)
    assert rows == [("screens/logo.html", [])]


def test_parse_screens_table_stops_at_next_section():
    md = (
        "## Screens\n\n"
        "| 01 | A | screens/a.html | complete | FR-01.01 |\n"
        "\n## User Flows\n\n"
        "| Flow | File | Screens | Status |\n"
        "| Auth | flows/auth.html | 01 → 02 | complete |\n"
    )
    rows = _parse_screens_table(md)
    # Only the Screens row is returned — User Flows rows are ignored
    assert len(rows) == 1
    assert rows[0][0] == "screens/a.html"


# ---------------------------------------------------------------------------
# check_design_manifest_screens_exist
# ---------------------------------------------------------------------------

def test_manifest_screens_exist_passes_on_happy_path(tmp_path):
    seed_canon_design(tmp_path)
    r = check_design_manifest_screens_exist(tmp_path)
    assert r.ok is True


def test_manifest_screens_exist_fails_on_missing_html(tmp_path):
    seed_canon_design(tmp_path)
    (tmp_path / ".shipwright" / "designs" / "screens" / "01-login.html").unlink()
    r = check_design_manifest_screens_exist(tmp_path)
    assert r.ok is False


def test_manifest_screens_exist_fails_when_manifest_missing(tmp_path):
    r = check_design_manifest_screens_exist(tmp_path)
    assert r.ok is False


# ---------------------------------------------------------------------------
# check_design_fr_coverage
# ---------------------------------------------------------------------------

def test_fr_coverage_passes_when_every_fr_linked(tmp_path):
    seed_canon_design(tmp_path)
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is True


def test_fr_coverage_fails_on_orphan_fr(tmp_path):
    seed_canon_design(tmp_path)
    # Add a new FR to the spec but don't link it to any screen
    (tmp_path / ".shipwright" / "planning" / "02-dashboard" / "spec.md").write_text(
        "| FR-02.01 | Show metrics | Must |\n"
        "| FR-02.02 | Export PDF | Should |\n"
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is False
    assert "FR-02.02" in r.detail


def test_fr_coverage_skips_when_no_planning_frs(tmp_path):
    # No .shipwright/planning/ dir → no FRs → trivially satisfied
    (tmp_path / ".shipwright" / "designs").mkdir(parents=True)
    (tmp_path / ".shipwright" / "designs" / "design-manifest.md").write_text("## Screens\n")
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# run_design_checks orchestrator
# ---------------------------------------------------------------------------

def test_run_design_checks_green_on_happy_path(tmp_path):
    seed_canon_design(tmp_path, run_id="design-happy")
    results = run_design_checks(tmp_path, run_id="design-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_design_checks_detects_missing_c1(tmp_path):
    seed_canon_design(tmp_path, run_id="design-happy")
    (tmp_path / "shipwright_events.jsonl").unlink()
    results = run_design_checks(tmp_path, run_id="design-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C1" in r.name for r in red)


def test_run_design_checks_detects_missing_c5(tmp_path):
    seed_canon_design(tmp_path, run_id="design-happy")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- bug\n"
    )
    results = run_design_checks(tmp_path, run_id="design-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C5" in r.name for r in red)


def test_run_design_checks_does_not_require_c4(tmp_path):
    """Design skips C4 — no ADR-with-phase-name needed."""
    seed_canon_design(tmp_path, run_id="design-happy")
    # Replace decision_log with an ADR that doesn't mention "design"
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: Unrelated thing\n- **Status:** accepted\n"
    )
    results = run_design_checks(tmp_path, run_id="design-happy")
    # No C4 check in the design module
    assert not any("C4" in r.name for r in results)


def test_run_design_checks_phase_history_skips_when_run_id_blank(tmp_path):
    seed_canon_design(tmp_path, run_id="design-x")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    results = run_design_checks(tmp_path, run_id="")
    phase_hits = [r for r in results if "phase_history" in r.name]
    assert len(phase_hits) == 1 and phase_hits[0].ok is True
