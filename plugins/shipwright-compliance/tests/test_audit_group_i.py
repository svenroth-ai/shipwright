"""Group I — Requirement Hygiene (FR-authoring drift detective).

Covers the header-driven row scanner across all three FR table shapes in the
wild (greenfield 4-column, adopt 6-column, brownfield Area variant) and the
findings emitted by ``run``. Pure detector tests live in
``test_audit_group_i_detectors.py``.

The status assertions are load-bearing, not cosmetic: `AuditReport.any_fail` is
driven by ``status == "fail"``, so a prose heuristic emitting "fail" would flip
the audit exit code and the dashboard verdict on every repo carrying legacy FR
text — the opposite of the advisory contract in `shared/fr-authoring.md` §7.
"""

from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_i  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GREENFIELD = """\
## 2. Functional Requirements

| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-02.01 | The system SHALL show every task on one board, newest first. | Must | unit |
| FR-02.02 | The system SHALL let a user start or resume a piece of work. | Must | unit |
"""

_ADOPT = """\
## 2. Functional Requirements

| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-01.01 | Task board | Must | Shows every task grouped by state. | `x.ts` | unit |
| FR-01.02 | Pending questions (GET) | Must | Walks unmatched tool_use ids in the log. | `y.ts` | unit |
"""

_WITH_AREA = """\
## 2. Functional Requirements

| ID | Area | Name | Priority | Description | Origin |
|----|------|------|----------|-------------|--------|
| FR-01.01 | BRD | Task board | Must | Shows every task grouped by state. | crawl |
"""

_WITH_REMOVED = """\
## 2. Functional Requirements

| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-02.01 | The system SHALL show every task on one board. | Must | unit |

### Removed Requirements

| ID | Requirement | Priority | Removed by | status |
|----|-------------|----------|------------|--------|
| FR-02.09 | The system SHALL export via POST /legacy_dump. | Must | iterate-x | status: deprecated |
"""


def _spec(tmp_path: Path, body: str, split: str = "02-board") -> Path:
    d = tmp_path / ".shipwright" / "planning" / split
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Row scanner — header-driven, across all table shapes
# ---------------------------------------------------------------------------


def test_scan_greenfield_uses_requirement_column_as_description(tmp_path):
    rows = group_i.scan_fr_rows(_spec(tmp_path, _GREENFIELD))
    assert [r.id for r in rows] == ["FR-02.01", "FR-02.02"]
    assert rows[0].name == ""  # greenfield has no separate Name column
    assert "one board" in rows[0].description


def test_scan_adopt_splits_name_and_description(tmp_path):
    rows = group_i.scan_fr_rows(_spec(tmp_path, _ADOPT, split="01-adopted"))
    assert rows[1].name == "Pending questions (GET)"
    assert "tool_use" in rows[1].description


def test_scan_tolerates_area_column(tmp_path):
    rows = group_i.scan_fr_rows(_spec(tmp_path, _WITH_AREA, split="01-adopted"))
    assert rows[0].name == "Task board"
    assert rows[0].description == "Shows every task grouped by state."


def test_scan_skips_removed_requirements(tmp_path):
    """A retired row must not be linted — it is history, not a live requirement."""
    rows = group_i.scan_fr_rows(_spec(tmp_path, _WITH_REMOVED))
    assert [r.id for r in rows] == ["FR-02.01"]


# ---------------------------------------------------------------------------
# run() — findings
# ---------------------------------------------------------------------------


def _run(project_root):
    return group_i.run(project_root, None, None)


def _by_id(findings):
    return {f.check_id: f for f in findings}


def test_clean_greenfield_spec_is_clean(tmp_path):
    findings = _by_id(_run(_spec(tmp_path, _GREENFIELD)))
    # I5 (Basis vocabulary) joined the group in campaign S5.
    assert set(findings) == {"I1", "I2", "I3", "I4", "I5"}
    # Greenfield has no Name column, so the §5 fence is inapplicable, NOT passing.
    assert findings["I1"].status == "skip"
    assert "not applicable" in findings["I1"].detail
    # Same shape of answer for I5: this fixture predates the Basis column, so the
    # vocabulary is inapplicable rather than satisfied.
    assert findings["I5"].status == "skip"
    assert "no Basis column" in findings["I5"].detail
    assert all(findings[c].status == "pass" for c in ("I2", "I3", "I4"))


def test_clean_adopt_spec_passes_the_name_fence(tmp_path):
    """With a Name column present, a clean spec genuinely PASSES I1."""
    body = _ADOPT.replace(
        "| FR-01.02 | Pending questions (GET) | Must | Walks unmatched tool_use ids in the log. | `y.ts` | unit |",
        "| FR-01.02 | Pending questions | Must | Shows every question awaiting an answer. | `y.ts` | unit |",
    )
    findings = _by_id(_run(_spec(tmp_path, body, split="01-adopted")))
    assert findings["I1"].status == "pass"


def test_adopt_spec_flags_name_and_description(tmp_path):
    findings = _by_id(_run(_spec(tmp_path, _ADOPT, split="01-adopted")))
    assert "FR-01.02" in findings["I1"].detail
    assert "advisory" in findings["I1"].detail
    assert "advisory" in findings["I2"].detail


def test_fold_candidate_is_reported(tmp_path):
    body = _GREENFIELD.replace(
        "The system SHALL let a user start or resume a piece of work.",
        "Polish that completes FR-02.01.",
    )
    findings = _by_id(_run(_spec(tmp_path, body)))
    assert "FR-02.02" in findings["I3"].detail
    assert "advisory" in findings["I3"].detail


def test_duplicate_fr_id_is_reported(tmp_path):
    body = _GREENFIELD.replace("| FR-02.02 |", "| FR-02.01 |")
    findings = _by_id(_run(_spec(tmp_path, body)))
    assert findings["I4"].status == "fail"
    assert "FR-02.01" in findings["I4"].detail


def test_no_spec_skips_rather_than_fails(tmp_path):
    findings = _by_id(_run(tmp_path))
    assert all(f.status == "skip" for f in findings.values())


def test_every_finding_is_detective_only_and_advisory(tmp_path):
    """Group I must never emit HIGH — it is advisory by contract (§7)."""
    findings = _run(_spec(tmp_path, _ADOPT, split="01-adopted"))
    assert findings
    for f in findings:
        assert f.group == "I"
        assert f.source == SOURCE_DETECTIVE_ONLY
        assert f.severity in {"LOW", "MEDIUM"}


def test_prose_checks_never_flip_the_audit_verdict(tmp_path):
    """The load-bearing advisory guarantee.

    `AuditReport.any_fail` is `any(status == "fail")`, and it drives run_audit's
    exit code and the dashboard verdict. The requirement is that existing prose
    violations must NOT redden CI, so I1/I2/I3 must never emit "fail" no matter
    how dirty the spec is. I4 (a duplicate ID) is an objective defect and does.
    """
    findings = _by_id(_run(_spec(tmp_path, _ADOPT, split="01-adopted")))
    for check in ("I1", "I2", "I3"):
        assert findings[check].status != "fail", check


def test_retired_fr_number_must_not_be_reused(tmp_path):
    """§4: a removed FR's number is retired for good — I4 must see it."""
    body = _WITH_REMOVED.replace(
        "| FR-02.01 | The system SHALL show every task on one board. | Must | unit |",
        "| FR-02.01 | The system SHALL show every task on one board. | Must | unit |\n"
        "| FR-02.09 | The system SHALL export a monthly report. | Must | unit |",
    )
    findings = _by_id(_run(_spec(tmp_path, body)))
    assert findings["I4"].status == "fail"
    assert "FR-02.09" in findings["I4"].detail


def test_retired_rows_are_not_linted_for_prose(tmp_path):
    """The retired row carries `POST /legacy_dump` — history, not a finding."""
    findings = _by_id(_run(_spec(tmp_path, _WITH_REMOVED)))
    assert "FR-02.09" not in findings["I2"].detail


def test_findings_cap_the_preview_but_report_the_true_count(tmp_path):
    """A legacy spec must not dump 60 IDs into the report."""
    header = _ADOPT.split("| FR-01.01")[0]
    rows = "\n".join(
        f"| FR-01.{n:02d} | Route handler (GET) | Must | Serves thing {n}. | `x.ts` | unit |"
        for n in range(1, 13)
    )
    findings = _by_id(_run(_spec(tmp_path, header + rows + "\n", split="01-adopted")))
    assert "12" in findings["I1"].detail
    assert findings["I1"].detail.count("FR-01.") <= 5
