"""Groups C + F preventive-rerun tests (plan v7, Step 6).

Both groups are pure import orchestration over iterate-12 check
functions. These tests cover the adapter layer: every check in the
group emits exactly one Finding with source='preventive-rerun', and
one imported check crashing does not drop the others.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_c, group_f  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_PREVENTIVE_RERUN  # noqa: E402


class _FakeCheck:
    def __init__(self, name, ok, severity="error", detail=""):
        self.name = name
        self.ok = ok
        self.severity = severity
        self.detail = detail


def _patch_iterate12(monkeypatch, module, mapping):
    """Swap ``import_iterate12_checks`` on the target module."""
    def _fake():
        return mapping
    monkeypatch.setattr(module, "import_iterate12_checks", _fake)


def _passing_checks(ids):
    return {cid: (lambda _r: _FakeCheck(cid, ok=True)) for cid in ids}


# ---------------------------------------------------------------------------
# Group C
# ---------------------------------------------------------------------------


_GROUP_C_IDS = [
    "check_design_fr_coverage",
    "check_fr_orphans_in_plan",
    "check_section_files_match_manifest",
    "check_section_id_validity",
]


def test_group_c_emits_finding_per_check(monkeypatch, tmp_path):
    _patch_iterate12(monkeypatch, group_c, _passing_checks(_GROUP_C_IDS))
    findings = group_c.run(tmp_path, None, None)
    assert len(findings) == 4
    assert {f.check_id for f in findings} == {"C1", "C2", "C3", "C4"}
    for f in findings:
        assert f.group == "C"
        assert f.source == SOURCE_PREVENTIVE_RERUN
        assert f.status == "pass"


def test_group_c_surfaces_check_failures(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_C_IDS)
    mapping["check_fr_orphans_in_plan"] = lambda _r: _FakeCheck(
        "check_fr_orphans_in_plan", ok=False, detail="orphan FR-05.02",
    )
    _patch_iterate12(monkeypatch, group_c, mapping)
    findings = group_c.run(tmp_path, None, None)
    c2 = next(f for f in findings if f.check_id == "C2")
    assert c2.status == "fail"
    assert "orphan FR-05.02" in c2.detail
    assert c2.suggested_iterate_cmd  # non-empty, contains copy-pasteable hint
    # Suggestion must reference the check_id and the audit report path so
    # /shipwright-iterate has a pointer back to the findings.
    assert "C2" in c2.suggested_iterate_cmd
    assert "compliance/audit-report.md" in c2.suggested_iterate_cmd


def test_group_c_isolates_check_crashes(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_C_IDS)

    def boom(_r):
        raise RuntimeError("verifier exploded")
    mapping["check_design_fr_coverage"] = boom
    _patch_iterate12(monkeypatch, group_c, mapping)

    findings = group_c.run(tmp_path, None, None)
    assert len(findings) == 4  # all 4 present
    c1 = next(f for f in findings if f.check_id == "C1")
    assert c1.status == "fail"
    assert "RuntimeError" in c1.detail
    # Remaining checks still pass
    assert all(f.status == "pass" for f in findings if f.check_id != "C1")


def test_group_c_maps_skipped_checks(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_C_IDS)
    mapping["check_section_id_validity"] = lambda _r: _FakeCheck(
        "check_section_id_validity", ok=None, severity="skipped",
        detail="no plan.md found",
    )
    _patch_iterate12(monkeypatch, group_c, mapping)
    findings = group_c.run(tmp_path, None, None)
    c4 = next(f for f in findings if f.check_id == "C4")
    assert c4.status == "skip"


# ---------------------------------------------------------------------------
# Group F
# ---------------------------------------------------------------------------


_GROUP_F_IDS = [
    "check_adr_ids_sequential",
    "check_adr_status_valid",
    "check_adr_supersession_exists",
]


def test_group_f_emits_finding_per_check(monkeypatch, tmp_path):
    _patch_iterate12(monkeypatch, group_f, _passing_checks(_GROUP_F_IDS))
    findings = group_f.run(tmp_path, None, None)
    assert len(findings) == 3
    assert {f.check_id for f in findings} == {"F1", "F2", "F3"}
    for f in findings:
        assert f.group == "F"
        assert f.source == SOURCE_PREVENTIVE_RERUN


def test_group_f_detects_gap_in_ids(monkeypatch, tmp_path):
    mapping = _passing_checks(_GROUP_F_IDS)
    mapping["check_adr_ids_sequential"] = lambda _r: _FakeCheck(
        "check_adr_ids_sequential", ok=False,
        detail="gap between ADR-003 and ADR-005",
    )
    _patch_iterate12(monkeypatch, group_f, mapping)
    findings = group_f.run(tmp_path, None, None)
    f1 = next(f for f in findings if f.check_id == "F1")
    assert f1.status == "fail"
    assert "gap" in f1.detail


# ---------------------------------------------------------------------------
# End-to-end through the detector + registry
# ---------------------------------------------------------------------------


def test_registry_wires_c_and_f(monkeypatch, tmp_path):
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    # Stub out both iterate-12 lookups so the test is hermetic.
    _patch_iterate12(monkeypatch, group_c, _passing_checks(_GROUP_C_IDS))
    _patch_iterate12(monkeypatch, group_f, _passing_checks(_GROUP_F_IDS))

    register_all()

    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    report = audit_detector.run_all(tmp_path, run_gate=False)

    ids = {f.check_id for f in report.findings}
    assert {"C1", "C2", "C3", "C4", "F1", "F2", "F3"}.issubset(ids)
    # Steps 5/7/8 groups (B, E, G) are still not-implemented. A and D
    # landed in Step 4.
    skipped_groups = {g for g, _r in report.groups_skipped}
    assert skipped_groups == {"B", "E", "G"}
