"""Detector skeleton tests (plan v7, Step 3).

Individual group check tests arrive with Steps 4-8. This file covers:

- Group registry (``register_group`` / ``registered_groups``).
- ``run_all`` behavior when groups are absent (``groups_skipped``).
- Crash isolation — one misbehaving group must not blow up the rest.
- Audit config defaults + override merge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit.audit_adapters import (  # noqa: E402
    SOURCE_DETECTIVE_ONLY,
    Finding,
)
from scripts.audit import audit_detector  # noqa: E402
from scripts.audit.audit_detector import (  # noqa: E402
    AuditReport,
    load_audit_config,
    register_group,
    run_all,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Each test gets a clean group registry."""
    snapshot = dict(audit_detector._GROUPS)
    audit_detector._GROUPS.clear()
    try:
        yield
    finally:
        audit_detector._GROUPS.clear()
        audit_detector._GROUPS.update(snapshot)


def _make_finding(group: str = "A", check_id: str = "A2",
                  status: str = "pass") -> Finding:
    return Finding(
        group=group, check_id=check_id, name=check_id,
        severity="LOW", source=SOURCE_DETECTIVE_ONLY, status=status,
    )


def test_register_group_rejects_unknown_letter():
    with pytest.raises(ValueError):
        register_group("Z", lambda *a: [])


def test_run_all_skips_unregistered_groups(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8"
    )
    report = run_all(tmp_path, run_gate=False)
    assert report.findings == []
    # F20: the default group set is {A..I} — Group H (bloat-policy
    # detective audit) MUST be in the default ``wanted`` set, else the
    # post-merge bloat net runs zero checks.
    assert len(report.groups_skipped) == 9
    assert {g for g, _r in report.groups_skipped} == {
        "A", "B", "C", "D", "E", "F", "G", "H", "I"
    }


def test_run_all_default_set_includes_group_h(tmp_path):
    """F20 — with H registered and no ``only`` filter, H must run.

    Regression for the deep-audit F20: ``run_all``'s default ``wanted``
    set omitted "H", so a registered Group H never executed and the
    bloat detective audit was structurally inert.
    """
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    for letter in ("A", "B", "C", "D", "E", "F", "G", "H", "I"):
        register_group(letter, lambda *a, _g=letter: [_make_finding(group=_g)])

    report = run_all(tmp_path, run_gate=False, emit_to_triage=False)
    assert "H" in report.groups_run
    assert set(report.groups_run) == {"A", "B", "C", "D", "E", "F", "G", "H", "I"}


def test_run_all_executes_registered_group(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8"
    )
    register_group("A", lambda _r, _c, _d: [_make_finding()])
    report = run_all(tmp_path, run_gate=False)
    assert len(report.findings) == 1
    assert report.groups_run == ["A"]


def test_run_all_only_filter(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    register_group("A", lambda *a: [_make_finding(group="A")])
    register_group("B", lambda *a: [_make_finding(group="B")])

    report = run_all(tmp_path, only=["B"], run_gate=False)
    assert [f.group for f in report.findings] == ["B"]
    assert report.groups_run == ["B"]


def test_run_all_isolates_group_crashes(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")

    def boom(*_a):
        raise RuntimeError("group exploded")

    register_group("A", boom)
    register_group("B", lambda *a: [_make_finding(group="B")])

    report = run_all(tmp_path, run_gate=False)
    # B still ran
    assert [f.group for f in report.findings] == ["B"]
    # A shows up as skipped with a crashed-reason
    assert any(g == "A" and "RuntimeError" in r for g, r in report.groups_skipped)


def test_run_all_any_fail_flag(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    register_group("A", lambda *a: [_make_finding(status="pass")])
    register_group("B", lambda *a: [_make_finding(group="B", status="fail")])

    report = run_all(tmp_path, run_gate=False)
    assert report.any_fail is True


def test_run_all_any_fail_false_on_all_pass(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    register_group("A", lambda *a: [_make_finding(status="pass")])
    report = run_all(tmp_path, run_gate=False)
    assert report.any_fail is False


def test_audit_report_to_dict_roundtrip():
    report = AuditReport(findings=[_make_finding(status="fail")])
    d = report.to_dict()
    assert d["any_fail"] is True
    assert d["findings"][0]["group"] == "A"
    # Survives JSON round-trip
    assert json.loads(json.dumps(d))["findings"][0]["check_id"] == "A2"


def test_load_audit_config_defaults(tmp_path):
    cfg = load_audit_config(tmp_path)
    assert "g2_stoplist" in cfg
    assert "webui" in cfg["g2_stoplist"]
    assert "g2_alias_map" in cfg
    assert "b7_exclusions" in cfg


def test_load_audit_config_merges_project_override(tmp_path):
    (tmp_path / "audit_config.json").write_text(
        json.dumps({"g2_stoplist": ["onlyone"], "custom_field": 42}),
        encoding="utf-8",
    )
    cfg = load_audit_config(tmp_path)
    # Override wins
    assert cfg["g2_stoplist"] == ["onlyone"]
    # Defaults still present for non-overridden keys
    assert "g2_alias_map" in cfg
    # Extra user keys pass through
    assert cfg["custom_field"] == 42


def test_load_audit_config_tolerates_corrupt_json(tmp_path):
    (tmp_path / "audit_config.json").write_text("not { json", encoding="utf-8")
    cfg = load_audit_config(tmp_path)
    # Falls back to defaults silently
    assert "g2_stoplist" in cfg


def test_run_all_reports_import_gate_error(tmp_path, monkeypatch):

    def _boom(_=None):
        from scripts.audit.audit_adapters import ImportGateError
        raise ImportGateError("mocked iterate-12 drift")

    monkeypatch.setattr(audit_detector, "verify_imports", _boom)

    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")
    report = run_all(tmp_path, run_gate=True)
    assert report.import_gate_error is not None
    assert "mocked iterate-12 drift" in report.import_gate_error
    # No groups run when the gate fails
    assert report.groups_run == []


# ---------------------------------------------------------------------------
# disabled_checks applicability gate
# (iterate-2026-05-31-compliance-check-context-gate)
# ---------------------------------------------------------------------------


def test_disabled_check_rewritten_to_skip(tmp_path):
    register_group("A", lambda *a: [_make_finding(check_id="B7", status="fail")])
    report = run_all(
        tmp_path, only=["A"], run_gate=False, emit_to_triage=False,
        config={"disabled_checks": ["B7"]},
    )
    [f] = report.findings
    assert f.status == "skip"
    assert f.severity == "LOW"
    assert f.detail == "disabled via audit_config.disabled_checks"
    assert report.any_fail is False


def test_disabled_checks_default_is_noop(tmp_path):
    register_group("A", lambda *a: [_make_finding(check_id="B7", status="fail")])
    report = run_all(tmp_path, only=["A"], run_gate=False, emit_to_triage=False)
    [f] = report.findings
    assert f.status == "fail"  # unchanged when disabled_checks absent


def test_disabled_checks_only_affects_listed_ids(tmp_path):
    register_group("A", lambda *a: [
        _make_finding(check_id="B7", status="fail"),
        _make_finding(check_id="D1", status="fail"),
    ])
    report = run_all(
        tmp_path, only=["A"], run_gate=False, emit_to_triage=False,
        config={"disabled_checks": ["B7"]},
    )
    by_id = {f.check_id: f.status for f in report.findings}
    assert by_id == {"B7": "skip", "D1": "fail"}


def test_disabled_check_pass_is_not_rewritten(tmp_path):
    # A disabled check that PASSES keeps its pass signal — only FAILs suppressed.
    register_group("A", lambda *a: [_make_finding(check_id="B7", status="pass")])
    report = run_all(
        tmp_path, only=["A"], run_gate=False, emit_to_triage=False,
        config={"disabled_checks": ["B7"]},
    )
    [f] = report.findings
    assert f.status == "pass"


def test_disabled_checks_in_default_config_empty(tmp_path):
    cfg = load_audit_config(tmp_path)
    assert cfg.get("disabled_checks") == []


def test_framework_audit_config_disables_expected_checks():
    """The repo-root audit_config.json declares the framework repo's N/A checks."""
    repo_root = PLUGIN_ROOT.parent.parent
    cfg_path = repo_root / "audit_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    # BP-1 re-enabled D1 (all-time coverage + FR backfill make it pass honestly).
    # iterate-2026-07-23-tests-skipped-tracking re-enabled D4: its stale-snapshot
    # reason was rooted in D4 reading a passed/total gap (host-gated skips) as a
    # failing build; D4 now keys on genuine failures, so it passes honestly and no
    # longer needs suppression.
    assert set(cfg["disabled_checks"]) == {"A5.6", "B7", "G2"}
    assert "D1" not in cfg["disabled_checks"]
    assert "D4" not in cfg["disabled_checks"]
    assert "_d4_reenabled" in cfg  # the reversal is documented
    # Every disabled check carries a documented reason.
    assert set(cfg["disabled_checks"]) <= set(cfg["_disabled_checks_reasons"])
