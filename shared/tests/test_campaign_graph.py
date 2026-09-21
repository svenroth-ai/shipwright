"""Unit tests for ``lib.campaign_graph`` (campaign-dag-scheduler R1):
``id_charset_ok``, ``validate_dependency_graph``, ``check_frozen_contracts``,
and the ``safe_project_campaign_status`` resume-safe wrapper.
"""

from __future__ import annotations

import json

from lib.campaign_graph import (
    check_frozen_contracts,
    id_charset_ok,
    safe_project_campaign_status,
    validate_dependency_graph,
)

CAMPAIGN_MD = """---
campaign: demo
status: active
branch_strategy: serial
created: 2026-09-21T00:00:00+00:00
---

## Sub-Iterates

| ID | Slug | Title | Status | Depends On |
|---|---|---|---|---|
| A | alpha | First | pending |  |
| B | bravo | Second | pending | A |
| C | charlie | Third | pending |  |
"""


def _committed(**overrides):
    subs = [
        {"id": "A", "slug": "alpha", "spec_path": "x/A.md", "status": "pending",
         "commit": None, "branch": None, "tests_passed": None, "tests_total": None},
        {"id": "B", "slug": "bravo", "spec_path": "x/B.md", "status": "pending",
         "commit": None, "branch": None, "tests_passed": None, "tests_total": None},
        {"id": "C", "slug": "charlie", "spec_path": "x/C.md", "status": "pending",
         "commit": None, "branch": None, "tests_passed": None, "tests_total": None},
    ]
    for s in subs:
        s.update(overrides.get(s["id"], {}))
    return {"campaign": "demo", "status": "active", "branch_strategy": "serial", "sub_iterates": subs}


class TestIdCharsetOk:
    def test_real_ids_pass(self):
        for value in ("R0", "15.0", "14.2", "p3.8"):
            assert id_charset_ok(value), value

    def test_leading_trailing_separator_rejected(self):
        assert not id_charset_ok(".R0")
        assert not id_charset_ok("R0.")
        assert not id_charset_ok("-R0")
        assert not id_charset_ok("_R0")

    def test_double_dot_rejected(self):
        assert not id_charset_ok("R0..1")

    def test_literal_double_dash_rejected(self):
        assert not id_charset_ok("campaign--unit")

    def test_disallowed_chars_rejected(self):
        assert not id_charset_ok("R0 1")
        assert not id_charset_ok("R0/1")
        assert not id_charset_ok("R0\\1")

    def test_length_bound(self):
        assert id_charset_ok("a" * 64)
        assert not id_charset_ok("a" * 65)

    def test_non_string_and_empty_rejected(self):
        assert not id_charset_ok("")
        assert not id_charset_ok(None)  # type: ignore[arg-type]


class TestValidateDependencyGraph:
    def test_clean_graph_no_findings(self):
        rows = [{"id": "A", "depends_on": []}, {"id": "B", "depends_on": ["A"]}]
        assert validate_dependency_graph(rows) == []

    def test_duplicate_ids(self):
        rows = [{"id": "A", "depends_on": []}, {"id": "A", "depends_on": []}]
        findings = validate_dependency_graph(rows)
        assert any(f.startswith("structural:") and "duplicate" in f for f in findings)

    def test_unknown_dependency(self):
        rows = [{"id": "A", "depends_on": ["ZZZ"]}]
        findings = validate_dependency_graph(rows)
        assert any("unknown id" in f for f in findings)

    def test_non_str_dependency_does_not_crash_charset_sort(self):
        # Doubt review (low): `id_charset_ok` correctly flags a non-str dep,
        # but `sorted()` over a mixed str/non-str set previously raised
        # TypeError before this function could report the finding.
        rows = [{"id": "A", "depends_on": [5]}]
        findings = validate_dependency_graph(rows)
        assert any(f.startswith("charset:") for f in findings)

    def test_self_dependency(self):
        rows = [{"id": "A", "depends_on": ["A"]}]
        findings = validate_dependency_graph(rows)
        assert any("depends on itself" in f for f in findings)
        assert not any("cycle" in f for f in findings)  # not double-reported as a cycle

    def test_two_node_cycle(self):
        rows = [{"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["A"]}]
        findings = validate_dependency_graph(rows)
        assert any("cycle" in f for f in findings)

    def test_longer_cycle_any_length(self):
        rows = [{"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["C"]},
                {"id": "C", "depends_on": ["A"]}]
        findings = validate_dependency_graph(rows)
        assert any("cycle" in f for f in findings)

    def test_charset_finding_is_separately_typed(self):
        rows = [{"id": "bad--id", "depends_on": []}]
        findings = validate_dependency_graph(rows)
        assert findings == ["charset: invalid id(s) (charset/length/segment rule): ['bad--id']"]
        assert findings[0].startswith("charset:")

    def test_structural_and_charset_both_reported(self):
        rows = [{"id": "bad--id", "depends_on": ["bad--id"]}]
        findings = validate_dependency_graph(rows)
        structural = [f for f in findings if f.startswith("structural:")]
        charset = [f for f in findings if f.startswith("charset:")]
        assert structural and charset

    def test_case_fold_collision_is_structural(self):
        # Windows worktree directories case-fold — R0/r0 would collide on
        # disk (R2) despite each independently passing the charset check.
        rows = [{"id": "R0", "depends_on": []}, {"id": "r0", "depends_on": []}]
        findings = validate_dependency_graph(rows)
        assert any("case-fold" in f for f in findings)

    def test_case_mismatched_dependency_reference_resolves(self):
        # depends_on: ["r0"] referencing unit "R0" must NOT be flagged
        # "unknown id" — existence resolution is case-insensitive.
        rows = [{"id": "R0", "depends_on": []}, {"id": "B", "depends_on": ["r0"]}]
        findings = validate_dependency_graph(rows)
        assert not any("unknown id" in f for f in findings)

    def test_case_fold_self_dependency_detected(self):
        rows = [{"id": "R0", "depends_on": ["r0"]}]
        findings = validate_dependency_graph(rows)
        assert any("depends on itself" in f for f in findings)

    def test_mixed_case_cycle_detected(self):
        # External code review finding (high): a cycle whose edges reference
        # ids in a different case than the row that defines them must still
        # be caught by cycle detection, not just by existence resolution.
        rows = [{"id": "R0", "depends_on": ["b"]}, {"id": "B", "depends_on": ["r0"]}]
        findings = validate_dependency_graph(rows)
        assert any("cycle" in f for f in findings)

    def test_missing_id_is_its_own_structural_finding_no_crash(self):
        # External code review finding (medium): a row with a missing/non-
        # string id used to reach a bare sorted()/set() on mixed types and
        # could raise TypeError before any finding was ever returned.
        rows = [{"depends_on": []}, {"id": "A", "depends_on": []}]
        findings = validate_dependency_graph(rows)
        assert any("missing a valid" in f for f in findings)

    def test_non_string_id_is_its_own_structural_finding_no_crash(self):
        rows = [{"id": 5, "depends_on": []}, {"id": "5", "depends_on": []}]
        findings = validate_dependency_graph(rows)  # must not raise TypeError
        assert any("missing a valid" in f for f in findings)


class TestCheckFrozenContracts:
    def test_pending_unit_edit_is_not_frozen(self):
        rows = [{"id": "B", "depends_on": ["A", "C"]}]
        loop_units = [{"id": "B", "status": "pending", "depends_on": ["A"]}]
        violations = check_frozen_contracts(rows, loop_units)
        assert violations == []
        assert rows[0]["depends_on"] == ["A", "C"]  # untouched

    def test_non_pending_unit_edit_is_reverted(self):
        rows = [{"id": "B", "depends_on": ["A", "C"]}]
        loop_units = [{"id": "B", "status": "in_progress", "depends_on": ["A"]}]
        violations = check_frozen_contracts(rows, loop_units)
        assert len(violations) == 1
        assert "B" in violations[0]
        assert rows[0]["depends_on"] == ["A"]  # reverted to frozen

    def test_unrelated_unit_unaffected(self):
        rows = [{"id": "A", "depends_on": []}, {"id": "B", "depends_on": ["A", "C"]}]
        loop_units = [{"id": "B", "status": "merged", "depends_on": ["A"]}]
        check_frozen_contracts(rows, loop_units)
        assert rows[0]["depends_on"] == []  # A never touched

    def test_no_change_no_violation(self):
        rows = [{"id": "B", "depends_on": ["A"]}]
        loop_units = [{"id": "B", "status": "merged", "depends_on": ["A"]}]
        assert check_frozen_contracts(rows, loop_units) == []

    def test_case_mismatched_unit_id_still_frozen(self):
        # External code review finding: a case-mismatched id between
        # campaign.md and loop_state.json must still be matched, not
        # silently skip the frozen check.
        rows = [{"id": "b", "depends_on": ["A", "C"]}]
        loop_units = [{"id": "B", "status": "in_progress", "depends_on": ["A"]}]
        violations = check_frozen_contracts(rows, loop_units)
        assert len(violations) == 1
        assert rows[0]["depends_on"] == ["A"]  # reverted to frozen


class TestSafeProjectCampaignStatus:
    def _write(self, tmp_path, *, md=CAMPAIGN_MD, status=None, loop_state=None):
        campaign_dir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "demo"
        campaign_dir.mkdir(parents=True)
        (campaign_dir / "campaign.md").write_text(md, encoding="utf-8")
        if status is not None:
            (campaign_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        if loop_state is not None:
            (tmp_path / ".shipwright" / "loop_state.json").write_text(json.dumps(loop_state), encoding="utf-8")
        events_log = tmp_path / "shipwright_events.jsonl"
        events_log.write_text("", encoding="utf-8")
        return campaign_dir, events_log

    def test_happy_path_carries_depends_on(self, tmp_path):
        campaign_dir, events_log = self._write(tmp_path, status=_committed())
        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["depends_on"] == ["A"]
        assert by_id["A"]["depends_on"] == []
        assert "degraded_reason" not in summary

    def test_structural_violation_degrades_to_last_successful(self, tmp_path):
        committed = _committed()
        bad_md = CAMPAIGN_MD.replace("| B | bravo | Second | pending | A |",
                                      "| B | bravo | Second | pending | ZZZ |")
        campaign_dir, events_log = self._write(tmp_path, md=bad_md, status=committed)
        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        assert status == committed  # verbatim last-successful projection
        assert "degraded_reason" in summary
        assert "unknown id" in summary["degraded_reason"]

    def test_charset_violation_only_warns_not_degrades(self, tmp_path):
        committed = _committed()
        charset_md = CAMPAIGN_MD.replace("| B | bravo", "| bad--id | bravo").replace(
            "| pending | A |", "| pending |  |")
        campaign_dir, events_log = self._write(tmp_path, md=charset_md, status=committed)
        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        assert "degraded_reason" not in summary
        assert any(w.startswith("charset:") for w in summary["warnings"])

    def test_frozen_contract_degrades_only_that_unit(self, tmp_path):
        committed = _committed()
        loop_state = {"units": [{"id": "B", "status": "in_progress", "depends_on": []}]}
        campaign_dir, events_log = self._write(tmp_path, status=committed, loop_state=loop_state)
        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["depends_on"] == []  # reverted to the frozen (empty) value
        assert by_id["A"]["depends_on"] == []  # A's own [] is unaffected, not "also reverted"
        assert by_id["C"]["depends_on"] == []
        assert "degraded_reason" in summary
        assert "frozen" in summary["degraded_reason"]

    def test_frozen_edit_to_unknown_id_reverts_instead_of_degrading_whole_campaign(self, tmp_path):
        # External Tier-3 PR review (blocking): a non-pending unit's edited
        # depends_on that ALSO happens to be structurally invalid (an
        # unknown id) previously hit validate_dependency_graph BEFORE
        # check_frozen_contracts ever ran, degrading the WHOLE campaign
        # instead of being caught and reverted per-unit like any other
        # frozen violation.
        committed = _committed()
        bad_md = CAMPAIGN_MD.replace("| B | bravo | Second | pending | A |",
                                      "| B | bravo | Second | pending | ZZZ |")
        loop_state = {"units": [{"id": "B", "status": "in_progress", "depends_on": ["A"]}]}
        campaign_dir, events_log = self._write(tmp_path, md=bad_md, status=committed, loop_state=loop_state)
        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["depends_on"] == ["A"]  # reverted to frozen, not "ZZZ"
        assert by_id["A"]["depends_on"] == []
        assert by_id["C"]["depends_on"] == []
        assert "degraded_reason" in summary
        assert "frozen" in summary["degraded_reason"]
        assert status != committed  # NOT the whole-campaign fallback

    def test_schema_invalid_loop_state_units_does_not_crash(self, tmp_path):
        # External code review finding (medium): syntactically valid but
        # schema-invalid loop_state.json (a non-dict element, or "units" not
        # even a list) must degrade to "no frozen contracts recorded", not
        # crash check_frozen_contracts's .get() calls.
        committed = _committed()
        campaign_dir, events_log = self._write(tmp_path, status=committed)
        loop_state_path = tmp_path / ".shipwright" / "loop_state.json"
        loop_state_path.write_text(json.dumps({"units": [None, "not-a-dict", 5]}), encoding="utf-8")
        status, summary = safe_project_campaign_status(campaign_dir, events_log)  # must not raise
        assert "degraded_reason" not in summary

    def test_non_list_depends_on_on_retained_unit_does_not_crash(self, tmp_path):
        # External Tier-3 PR review (blocking): a dict unit passes the
        # dict-element filter but had an un-validated depends_on field.
        # check_frozen_contracts builds list(u.get("depends_on") or []), and
        # a truthy non-list (e.g. an int) raised TypeError before this fix.
        committed = _committed()
        campaign_dir, events_log = self._write(tmp_path, status=committed)
        loop_state_path = tmp_path / ".shipwright" / "loop_state.json"
        loop_state_path.write_text(
            json.dumps({"units": [{"id": "A", "status": "in_progress", "depends_on": 5}]}),
            encoding="utf-8",
        )
        status, summary = safe_project_campaign_status(campaign_dir, events_log)  # must not raise
        assert "degraded_reason" not in summary

    def test_units_not_a_list_does_not_crash(self, tmp_path):
        committed = _committed()
        campaign_dir, events_log = self._write(tmp_path, status=committed)
        loop_state_path = tmp_path / ".shipwright" / "loop_state.json"
        loop_state_path.write_text(json.dumps({"units": {}}), encoding="utf-8")
        status, summary = safe_project_campaign_status(campaign_dir, events_log)  # must not raise
        assert "degraded_reason" not in summary

    def test_missing_campaign_md_degrades(self, tmp_path):
        campaign_dir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "demo"
        campaign_dir.mkdir(parents=True)
        events_log = tmp_path / "shipwright_events.jsonl"
        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        assert status == {"sub_iterates": []}
        assert summary["degraded_reason"] == "campaign.md missing"
