"""Tests for new PHASE_REPORTS entries (iterate-2026-05-23-security-adopt-…).

Adds two new phase keys:
  * ``adopt`` — full doc set (rtm, test_evidence, change_history, sbom,
    dashboard) since adopt establishes the initial baseline. Traceability TT7
    adds ``test_links`` here too: adopt's Step E.17 backfills existing tests, so
    this collector emits the baseline requirement→test manifest at onboarding.
  * ``security`` — 4 docs (dashboard, test_evidence, change_history,
    sbom). RTM excluded because security work doesn't change FR coverage.

Both phases route through the existing ``update_compliance.py`` CLI; this
file pins the routing contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.tools.update_compliance import PHASE_REPORTS  # noqa: E402


UPDATE_SCRIPT = PLUGIN_ROOT / "scripts" / "tools" / "update_compliance.py"


def test_phase_reports_adopt_has_full_doc_set():
    """Adopt seeds the initial baseline → all 5 compliance docs regen, plus the
    TT7 requirement→test manifest (``test_links``) from Step E.17's backfill."""
    assert "adopt" in PHASE_REPORTS, "PHASE_REPORTS missing 'adopt' key"
    assert sorted(PHASE_REPORTS["adopt"]) == sorted([
        "rtm", "test_evidence", "test_links", "change_history", "sbom", "dashboard",
    ])


def test_phase_reports_security_excludes_rtm():
    """Security pipeline finalize regenerates 4 docs; RTM untouched."""
    assert "security" in PHASE_REPORTS, "PHASE_REPORTS missing 'security' key"
    assert sorted(PHASE_REPORTS["security"]) == sorted([
        "dashboard", "test_evidence", "change_history", "sbom",
    ])
    # Explicit: no rtm in security set.
    assert "rtm" not in PHASE_REPORTS["security"]


@pytest.fixture
def synthetic_project(tmp_path):
    """Minimal project layout that update_compliance.py can run against."""
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "pipeline": []}), encoding="utf-8",
    )
    return tmp_path


def test_cli_phase_adopt_exits_zero(synthetic_project):
    """`update_compliance.py --phase adopt` runs end-to-end."""
    result = subprocess.run(
        [sys.executable, str(UPDATE_SCRIPT),
         "--project-root", str(synthetic_project), "--phase", "adopt"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["phase"] == "adopt"
    # All 5 reports should be in the updated list.
    rels = payload.get("updated_reports", [])
    names = {Path(r).name for r in rels}
    expected = {
        "traceability-matrix.md", "test-evidence.md",
        "change-history.md", "sbom.md", "dashboard.md",
    }
    assert expected.issubset(names), (
        f"adopt phase missing files. Got: {names}"
    )


def test_cli_phase_security_excludes_rtm(synthetic_project):
    """`update_compliance.py --phase security` regenerates 4 docs, not RTM."""
    result = subprocess.run(
        [sys.executable, str(UPDATE_SCRIPT),
         "--project-root", str(synthetic_project), "--phase", "security"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["phase"] == "security"
    rels = payload.get("updated_reports", [])
    names = {Path(r).name for r in rels}
    # Should regen dashboard/test-evidence/change-history/sbom.
    expected = {
        "test-evidence.md", "change-history.md", "sbom.md", "dashboard.md",
    }
    assert expected.issubset(names), f"missing security docs. Got: {names}"
    # Should NOT regen RTM.
    assert "traceability-matrix.md" not in names


_MARKER = "<!-- shipwright:audit-staleness:start -->"


def _seed_audit_report(project_root: Path) -> Path:
    """Write a minimal on-disk audit-report.md (run_audit's artifact)."""
    path = project_root / ".shipwright" / "compliance" / "audit-report.md"
    path.write_text(
        "# Shipwright Detective Audit\n\nGenerated: 2026-05-01 00:00:00 UTC\n\n"
        "## Findings\n\n- demo\n",
        encoding="utf-8",
    )
    return path


def test_cli_phase_iterate_stamps_audit_staleness(synthetic_project):
    """A routine `--phase iterate` regen (which does NOT re-run the audit) stamps
    the on-disk audit-report.md with a staleness banner (F4)."""
    audit_md = _seed_audit_report(synthetic_project)
    result = subprocess.run(
        [sys.executable, str(UPDATE_SCRIPT),
         "--project-root", str(synthetic_project), "--phase", "iterate"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["audit_staleness"]["stamped"] is True
    assert _MARKER in audit_md.read_text(encoding="utf-8")


def test_cli_phase_compliance_does_not_stamp(synthetic_project):
    """The `/shipwright-compliance` flow (phase=='compliance') re-runs the audit
    itself, so update_compliance must NOT mark a fresh audit stale."""
    audit_md = _seed_audit_report(synthetic_project)
    result = subprocess.run(
        [sys.executable, str(UPDATE_SCRIPT),
         "--project-root", str(synthetic_project), "--phase", "compliance"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert "audit_staleness" not in payload
    assert _MARKER not in audit_md.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# One collector's authoring defect must not dark the whole dashboard (S3)
# ---------------------------------------------------------------------------


def test_a_duplicate_fr_id_does_not_abort_the_other_reports(synthetic_project):
    """`test_links` is 3rd in PHASE_REPORTS['iterate'], and the generators run in list
    order inside one loop. Before the guard, a raise from it aborted the loop before
    change_history, sbom and dashboard were written: an adopter with one duplicated FR
    id in one spec got a bare traceback, exit 1, no JSON, and NO compliance artifacts
    at all. The refusal to publish an incomplete manifest is correct; taking every other
    report down with it is not."""
    planning = synthetic_project / ".shipwright" / "planning"
    table = ("# S\n\n| ID | Requirement | Priority | Layers |\n| --- | --- | --- | --- |\n"
             "| FR-03.01 | Live | Must | unit |\n")
    for split in ("01-a", "02-b"):                     # same ACTIVE id in two splits
        (planning / split).mkdir(parents=True, exist_ok=True)
        (planning / split / "spec.md").write_text(table, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(UPDATE_SCRIPT),
         "--project-root", str(synthetic_project), "--phase", "iterate"],
        capture_output=True, text=True, encoding="utf-8",
    )

    # Loud: non-zero exit and a machine-readable reason naming the collector...
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    errors = payload["generator_errors"]
    assert [e["report"] for e in errors] == ["test_links"]
    assert errors[0]["error"] == "DuplicateRequirementId"
    assert "FR-03.01" in errors[0]["detail"]
    # ...but NOT fatal: every other report in the phase still wrote.
    written = " ".join(payload["updated_reports"])
    for still_expected in ("change-history", "sbom", "dashboard"):
        assert still_expected in written, f"{still_expected} was darked by one collector"
