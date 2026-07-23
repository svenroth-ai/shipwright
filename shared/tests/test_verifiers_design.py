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
        "| ID | Requirement | Priority |\n" "| FR-01.01 | User can log in | Must |\n"
    )
    (root / ".shipwright" / "planning" / "02-dashboard").mkdir()
    (root / ".shipwright" / "planning" / "02-dashboard" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n" "| FR-02.01 | Show metrics | Must |\n"
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
        "| ID | Requirement | Priority |\n" "| FR-02.01 | Show metrics | Must |\n"
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
# Scope-aware skip for library projects
# ---------------------------------------------------------------------------
#
# `scope=library` projects (Python plugin monorepo, CLI framework, etc.)
# have no UI surface — the FR→screen mapping is structurally meaningless.
# The audit must report SKIP (ok=None, severity=SKIPPED), not FAIL.
# A missing or unreadable run_config means "we don't know the scope" and
# the check still runs (fail-closed; no silent free pass on broken state).

def test_fr_coverage_skips_when_scope_library(tmp_path):
    # FRs exist but the project is scope=library — no UI to map to.
    (tmp_path / ".shipwright" / "planning" / "01-x").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-x" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n" "| FR-01.01 | A library API | Must |\n"
    )
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "library"})
    )
    # Note: no .shipwright/designs tree at all — library projects don't have one.
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is None
    assert r.is_skipped
    assert "library" in r.detail.lower()


def test_manifest_screens_exist_skips_when_scope_library(tmp_path):
    # Same scenario for the sister check: scope=library short-circuits before
    # the manifest-missing check would otherwise fail.
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "library"})
    )
    r = check_design_manifest_screens_exist(tmp_path)
    assert r.ok is None
    assert r.is_skipped
    assert "library" in r.detail.lower()


def test_fr_coverage_runs_when_scope_full_app(tmp_path):
    # scope=full_app must still run the check (drift protection — the skip
    # is library-specific, not a universal opt-out).
    seed_canon_design(tmp_path)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app", "phase_history": {}})
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is True  # passes — every FR mapped


def test_fr_coverage_runs_when_run_config_missing(tmp_path):
    # No shipwright_run_config.json → we don't know scope → check still runs.
    # Fail-closed: never silently skip on broken state.
    seed_canon_design(tmp_path, write_canon_artifacts=False)
    # No run_config at tmp_path/shipwright_run_config.json
    r = check_design_fr_coverage(tmp_path)
    # Real assertion: not skipped. The result will be ok=True here because
    # seed_canon_design wires up a green manifest.
    assert r.ok is True
    assert not r.is_skipped


def test_fr_coverage_runs_when_run_config_malformed(tmp_path):
    # Malformed JSON → treat as unknown scope → check still runs (fail-closed).
    seed_canon_design(tmp_path, write_canon_artifacts=False)
    (tmp_path / "shipwright_run_config.json").write_text("{not valid json")
    r = check_design_fr_coverage(tmp_path)
    assert not r.is_skipped


# ---------------------------------------------------------------------------
# Design-phase-lifecycle skip (trg-d26da6f4)
# ---------------------------------------------------------------------------
#
# An ADOPTED (brownfield) project has FRs but never ran /shipwright-design, so
# `.shipwright/designs/design-manifest.md` legitimately never exists and
# `completed_steps` has no "design". The detective-audit check C1
# (check_design_fr_coverage) must SKIP (structurally inapplicable), not FAIL —
# mirroring the scope=library escape hatch.
#
# The guard is SURGICAL and lives ONLY on check_design_fr_coverage: it fires
# only on the manifest-missing branch. A design phase that ran (manifest
# present, or "design" in completed_steps) is fully enforced — a project that
# ran design then lost its manifest is real drift and still FAILs, and the
# FR-orphan enforcement stays live for the between-phase validator flow (where
# completed_steps has no "design" yet but the manifest is present). The sister
# check check_design_manifest_screens_exist is deliberately NOT guarded (it is
# not in the detective audit and never runs on an adopted project), so it
# remains the strict manifest-presence sentinel.


def _write_run_config(root: Path, **fields) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps(fields))


def test_fr_coverage_skips_when_design_phase_never_ran(tmp_path):
    # Adopted project: FRs present, scope≠library, "design" not in
    # completed_steps, and no design-manifest.md → SKIP, not FAIL.
    (tmp_path / ".shipwright" / "planning" / "01-x").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-x" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-01.01 | Log in | Must |\n"
    )
    _write_run_config(
        tmp_path, scope="full_app",
        completed_steps=["project", "plan", "build", "test"],
    )
    # No .shipwright/designs tree at all — the design phase never ran.
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is None
    assert r.is_skipped
    assert "design phase" in r.detail.lower()


def test_fr_coverage_fails_when_manifest_missing_but_design_ran(tmp_path):
    # Real drift: the design phase DID run ("design" in completed_steps) but the
    # manifest is gone. That is a genuine regression, not a structural skip.
    (tmp_path / ".shipwright" / "planning" / "01-x").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-x" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-01.01 | Log in | Must |\n"
    )
    _write_run_config(
        tmp_path, scope="full_app",
        completed_steps=["project", "design", "plan", "build", "test"],
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is False
    assert not r.is_skipped
    assert "missing" in r.detail.lower()


def test_fr_coverage_still_enforces_orphans_when_manifest_present_and_design_pending(tmp_path):
    # Regression guard for the between-phase validator flow: the manifest is
    # PRESENT (design phase produced it) but "design" is not yet in
    # completed_steps (validate_phase runs before completed_steps is appended).
    # The orphan-FR enforcement MUST still fire — the guard is manifest-gated,
    # not a top-level skip.
    seed_canon_design(tmp_path)
    (tmp_path / ".shipwright" / "planning" / "02-dashboard" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-02.01 | Show metrics | Must |\n"
        "| FR-02.02 | Export PDF | Should |\n"
    )
    _write_run_config(tmp_path, scope="full_app", completed_steps=["project"])
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is False
    assert "FR-02.02" in r.detail


def test_manifest_screens_exist_unguarded_still_fails_on_missing_manifest(tmp_path):
    # Sister check stays STRICT even for a no-design project: it is never run on
    # an adopted project, so it keeps failing loud on an absent manifest and
    # remains the manifest-presence sentinel (mitigates the mockups-present /
    # manifest-absent window for the FR-coverage check).
    _write_run_config(
        tmp_path, scope="full_app",
        completed_steps=["project", "plan", "build", "test"],
    )
    r = check_design_manifest_screens_exist(tmp_path)
    assert r.ok is False
    assert not r.is_skipped


# ---------------------------------------------------------------------------
# Config-reader robustness (WP8/F24 convention — external review OpenAI)
# ---------------------------------------------------------------------------
#
# The lifecycle skip decision reads shipwright_run_config.json. That reader
# must follow the repo config-reader convention: BOM-tolerant (utf-8-sig) and
# fail-loud (never crash) on an undecodable payload.


def test_scope_library_skip_tolerates_utf8_bom_run_config(tmp_path):
    # _is_no_ui_scope must parse a hand-edited UTF-8-BOM config: a BOM'd
    # scope=library project still SKIPs (a BOM that broke parsing would drop to
    # the manifest-missing FAIL — the exact false-C1 this iterate removes).
    (tmp_path / ".shipwright" / "planning" / "01-x").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-x" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-01.01 | A library API | Must |\n"
    )
    (tmp_path / "shipwright_run_config.json").write_bytes(
        "﻿".encode("utf-8") + json.dumps({"scope": "library"}).encode("utf-8")
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is None
    assert r.is_skipped
    assert "library" in r.detail.lower()


def test_lifecycle_skip_tolerates_utf8_bom_run_config(tmp_path):
    # A hand-edited UTF-8-BOM run_config must still be parsed: completed_steps
    # is read correctly, so a no-design project SKIPs (a BOM that broke parsing
    # would fail-loud to FAIL instead).
    (tmp_path / ".shipwright" / "planning" / "01-x").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-x" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-01.01 | Log in | Must |\n"
    )
    (tmp_path / "shipwright_run_config.json").write_bytes(
        "﻿".encode("utf-8")
        + json.dumps({
            "scope": "full_app",
            "completed_steps": ["project", "plan", "build", "test"],
        }).encode("utf-8")
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is None
    assert r.is_skipped


def test_lifecycle_skip_fails_loud_on_undecodable_run_config(tmp_path):
    # Invalid (non-UTF-8) bytes must not crash the verifier — fail-loud to a
    # normal FAIL on the missing manifest.
    (tmp_path / ".shipwright" / "planning" / "01-x").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-x" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-01.01 | Log in | Must |\n"
    )
    (tmp_path / "shipwright_run_config.json").write_bytes(b"\xff\xfe not utf-8 \x9d")
    r = check_design_fr_coverage(tmp_path)  # must return, not raise
    assert r.ok is False
    assert not r.is_skipped


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
