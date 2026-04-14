"""Tests for shared/scripts/tools/verifiers/plan_checks.py."""

from __future__ import annotations

import json
from pathlib import Path

from tools.verifiers.common import Severity
from tools.verifiers.plan_checks import (
    check_fr_orphans_in_plan,
    check_plan_config_status_complete,
    check_section_files_match_manifest,
    check_section_id_validity,
    run_plan_checks,
)


def seed_canon_plan(
    root: Path,
    *,
    split: str = "01-auth",
    sections: list[str] | None = None,
    frs: list[str] | None = None,
    run_id: str = "plan-20260414-test",
    write_canon_artifacts: bool = True,
) -> None:
    """Seed a minimally-valid plan project for a single split.

    Creates ``planning/<split>/``:
      - spec.md with the given FR rows
      - plan.md with a ``SECTION_MANIFEST`` listing the given sections
      - sections/*.md files whose bodies mention every declared FR
    """
    sections = sections or ["01-model", "02-routes", "03-ui"]
    frs = frs or ["FR-01.01", "FR-01.02"]

    split_dir = root / "planning" / split
    split_dir.mkdir(parents=True)

    spec_rows = "\n".join(f"| {fr} | {fr} description | Must |" for fr in frs)
    (split_dir / "spec.md").write_text(f"# Spec\n\n{spec_rows}\n")

    manifest_body = "\n".join(sections)
    plan_body = (
        "# Plan\n\n"
        f"Scope: {', '.join(frs)}\n\n"
        f"<!-- SECTION_MANIFEST\n{manifest_body}\nEND_MANIFEST -->\n"
    )
    (split_dir / "plan.md").write_text(plan_body)

    sections_dir = split_dir / "sections"
    sections_dir.mkdir()
    for idx, name in enumerate(sections):
        # First section mentions all FRs so coverage is trivially satisfied
        body_frs = ", ".join(frs) if idx == 0 else ""
        (sections_dir / f"{name}.md").write_text(
            f"# Section: {name}\n\n## Overview\nImplements: {body_frs}\n"
        )

    # plan_config.status=complete
    (root / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "complete", "split": split, "sections": len(sections)})
    )

    if not write_canon_artifacts:
        return

    # C1
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "phase_completed", "phase": "plan",
                    "timestamp": "2026-04-14T10:00:00Z"}) + "\n"
    )
    # C2
    (root / "agent_docs").mkdir()
    (root / "agent_docs" / "build_dashboard.md").write_text("- plan: complete\n")
    # C3
    (root / "agent_docs" / "session_handoff.md").write_text("fresh")
    # C4
    (root / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Plan decision for {split}\n- **Status:** accepted\n".replace("{split}", split)
    )
    # C5 is skipped by policy (plan)
    # phase_history
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"plan": [{"run_id": run_id, "date": "2026-04-14"}]},
    }))


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def test_plan_config_status_complete_passes(tmp_path):
    (tmp_path / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "complete"})
    )
    r = check_plan_config_status_complete(tmp_path)
    assert r.ok is True


def test_plan_config_status_in_progress_fails(tmp_path):
    (tmp_path / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "in_progress"})
    )
    r = check_plan_config_status_complete(tmp_path)
    assert r.ok is False


def test_plan_config_missing_fails(tmp_path):
    r = check_plan_config_status_complete(tmp_path)
    assert r.ok is False


# ---------------------------------------------------------------------------
# check_section_files_match_manifest
# ---------------------------------------------------------------------------

def test_section_files_match_manifest_passes_on_happy_path(tmp_path):
    seed_canon_plan(tmp_path)
    r = check_section_files_match_manifest(tmp_path)
    assert r.ok is True


def test_section_files_match_manifest_fails_on_missing_file(tmp_path):
    seed_canon_plan(tmp_path, sections=["01-model", "02-routes"])
    (tmp_path / "planning" / "01-auth" / "sections" / "02-routes.md").unlink()
    r = check_section_files_match_manifest(tmp_path)
    assert r.ok is False
    assert "02-routes" in r.detail


def test_section_files_match_manifest_fails_on_extra_file(tmp_path):
    seed_canon_plan(tmp_path, sections=["01-model"])
    (tmp_path / "planning" / "01-auth" / "sections" / "99-rogue.md").write_text("# rogue\n")
    r = check_section_files_match_manifest(tmp_path)
    assert r.ok is False
    assert "99-rogue" in r.detail


def test_section_files_match_manifest_passes_when_no_splits(tmp_path):
    r = check_section_files_match_manifest(tmp_path)
    assert r.ok is True


def test_section_files_match_manifest_ignores_iterate_dir(tmp_path):
    """planning/iterate/ is not a plan split."""
    seed_canon_plan(tmp_path)
    (tmp_path / "planning" / "iterate").mkdir()
    (tmp_path / "planning" / "iterate" / "plan.md").write_text("# iterate plan\n")
    r = check_section_files_match_manifest(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# check_fr_orphans_in_plan
# ---------------------------------------------------------------------------

def test_fr_orphans_passes_when_all_frs_declared(tmp_path):
    seed_canon_plan(tmp_path)
    r = check_fr_orphans_in_plan(tmp_path)
    assert r.ok is True


def test_fr_orphans_detects_mentioned_but_undeclared_fr(tmp_path):
    seed_canon_plan(tmp_path)
    # Add a bogus FR reference in a section body
    section = tmp_path / "planning" / "01-auth" / "sections" / "01-model.md"
    section.write_text(section.read_text() + "\nImplements: FR-99.99\n")
    r = check_fr_orphans_in_plan(tmp_path)
    assert r.ok is False
    assert "FR-99.99" in r.detail


def test_fr_orphans_detects_bogus_fr_in_plan_body(tmp_path):
    seed_canon_plan(tmp_path)
    plan_file = tmp_path / "planning" / "01-auth" / "plan.md"
    plan_file.write_text(plan_file.read_text() + "\nReferences FR-42.42\n")
    r = check_fr_orphans_in_plan(tmp_path)
    assert r.ok is False


def test_fr_orphans_passes_when_no_plan(tmp_path):
    r = check_fr_orphans_in_plan(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# check_section_id_validity
# ---------------------------------------------------------------------------

def test_section_id_validity_passes_on_sequential(tmp_path):
    seed_canon_plan(tmp_path, sections=["01-a", "02-b", "03-c"])
    r = check_section_id_validity(tmp_path)
    assert r.ok is True


def test_section_id_validity_detects_gap(tmp_path):
    seed_canon_plan(tmp_path, sections=["01-a", "03-c"])
    r = check_section_id_validity(tmp_path)
    assert r.ok is False
    assert "gaps" in r.detail.lower()


def test_section_id_validity_detects_bad_format(tmp_path):
    # Valid SECTION_MANIFEST-style names — seed manually because
    # seed_canon_plan's file creation would blow up on "foo" missing a prefix.
    split_dir = tmp_path / "planning" / "01-auth"
    split_dir.mkdir(parents=True)
    (split_dir / "spec.md").write_text("| FR-01.01 | x | Must |\n")
    (split_dir / "plan.md").write_text(
        "<!-- SECTION_MANIFEST\n01-a\nfoo-bar\nEND_MANIFEST -->\n"
    )
    (split_dir / "sections").mkdir()
    (split_dir / "sections" / "01-a.md").write_text("# a\n")
    (split_dir / "sections" / "foo-bar.md").write_text("# foo\n")

    r = check_section_id_validity(tmp_path)
    assert r.ok is False
    assert "foo-bar" in r.detail


def test_section_id_validity_detects_duplicates(tmp_path):
    split_dir = tmp_path / "planning" / "01-auth"
    split_dir.mkdir(parents=True)
    (split_dir / "spec.md").write_text("| FR-01.01 | x | Must |\n")
    (split_dir / "plan.md").write_text(
        "<!-- SECTION_MANIFEST\n01-a\n01-a\n02-b\nEND_MANIFEST -->\n"
    )
    (split_dir / "sections").mkdir()
    (split_dir / "sections" / "01-a.md").write_text("# a\n")
    (split_dir / "sections" / "02-b.md").write_text("# b\n")

    r = check_section_id_validity(tmp_path)
    assert r.ok is False
    assert "duplicate" in r.detail.lower()


def test_section_id_validity_passes_when_no_plan(tmp_path):
    r = check_section_id_validity(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# run_plan_checks orchestrator
# ---------------------------------------------------------------------------

def test_run_plan_checks_green_on_happy_path(tmp_path):
    seed_canon_plan(tmp_path, run_id="plan-happy")
    results = run_plan_checks(tmp_path, run_id="plan-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_plan_checks_detects_missing_c1(tmp_path):
    seed_canon_plan(tmp_path, run_id="plan-happy")
    (tmp_path / "shipwright_events.jsonl").unlink()
    results = run_plan_checks(tmp_path, run_id="plan-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C1" in r.name for r in red)


def test_run_plan_checks_does_not_require_c5(tmp_path):
    """Plan skips C5 — no CHANGELOG entry required."""
    seed_canon_plan(tmp_path, run_id="plan-happy")
    results = run_plan_checks(tmp_path, run_id="plan-happy")
    assert not any("C5" in r.name for r in results)


def test_run_plan_checks_requires_c4_project_adr(tmp_path):
    """Plan keeps C4 — it's a decision-taking phase."""
    seed_canon_plan(tmp_path, run_id="plan-happy")
    (tmp_path / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: Unrelated thing\n- **Status:** accepted\n"
    )
    results = run_plan_checks(tmp_path, run_id="plan-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C4" in r.name for r in red)
