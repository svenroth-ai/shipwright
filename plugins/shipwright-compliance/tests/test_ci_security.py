"""Tests for ci_security.py — AR-10 CI-security ingest into the dashboard.

Outcome-focused + boundary-probe (touches_io_boundary): the public-safe
summarizer, the ``.trivyignore.yaml`` accepted-risk parser, the
write→load round-trip, the grader signal (never a false CRITICAL), and the
dashboard render. All offline — no network, deterministic given a fixed ``now``.
"""

from __future__ import annotations

import json
from datetime import date

from types import SimpleNamespace

from scripts.lib._control_block import build_grade_inputs
from scripts.lib._dashboard_sections import render_date
from scripts.lib.ci_security import (
    grade_security_signal,
    load_ci_security,
    parse_accepted_risks,
    render_ci_security,
    summarize_ci_security,
    write_ci_security,
)

# --- Fixtures mirroring the real CI findings.json finding shape -------------

_HIGH_CRYPTO = {"severity": "high", "cve_id": "GHSA-537c-gmf6-5ccf",
                "affected_package": "cryptography",
                "affected_file": "plugins/shipwright-plan/uv.lock"}
_HIGH_WS = {"severity": "high", "cve_id": "CVE-2026-48779",
            "affected_package": "ws"}
_MED_OTEL = {"severity": "medium", "cve_id": "CVE-2026-54285",
             "affected_package": "@opentelemetry/core"}
_LIVE_FINDINGS = [_HIGH_CRYPTO, _MED_OTEL, _HIGH_WS, _HIGH_WS]

_TRIVYIGNORE = """\
vulnerabilities:
  - id: CVE-2026-54285
    paths:
      - "plugins/shipwright-test/scripts/perf/package-lock.json"
    expired_at: 2026-12-22
    statement: >-
      Accepted risk; dev-only transitive.
  - id: CVE-2025-00001
    expired_at: 2026-01-01
    statement: An entry whose re-review date has already passed.
"""


class TestSummarize:
    """AC1 — public-safe summary, no finding detail leaked."""

    def test_severity_breakdown_and_gate_pass(self):
        s = summarize_ci_security(
            _LIVE_FINDINGS, [], scan_date="2026-06-22T11:45:52+00:00",
            source="security.yml#27950188761")
        assert s["by_severity"] == {"critical": 0, "high": 3, "medium": 1, "low": 0}
        assert s["total"] == 4
        assert s["open_high_critical"] == 3
        assert s["critical_gate"] == "pass"   # 0 critical
        assert s["scan_date"] == "2026-06-22T11:45:52+00:00"
        assert s["prompt_injection"] == 0
        assert s["degraded"] is False

    def test_critical_gate_fails_on_a_critical(self):
        s = summarize_ci_security(
            [{"severity": "critical"}], [], scan_date="x", source="y")
        assert s["critical_gate"] == "fail"
        assert s["open_high_critical"] == 1

    def test_public_safe_no_finding_detail_leaks(self):
        # The summary must never carry file paths / package names / cve ids.
        s = summarize_ci_security(_LIVE_FINDINGS, [], scan_date="x", source="y")
        blob = json.dumps(s)
        for secret in ("uv.lock", "cryptography", "GHSA-537c", "package-lock"):
            assert secret not in blob

    def test_prompt_injection_counted_separately(self):
        s = summarize_ci_security(
            [], [{"severity": "high"}, {"severity": "low"}],
            scan_date="x", source="y")
        assert s["prompt_injection"] == 2
        assert s["by_severity"]["high"] == 0  # prompt risks are not OSS findings

    def test_empty_clean_scan(self):
        s = summarize_ci_security([], [], scan_date="x", source="y")
        assert s["open_high_critical"] == 0
        assert s["critical_gate"] == "pass"
        assert s["total"] == 0


class TestGradeSignal:
    """AC3 — light the grader honestly; never a false CRITICAL."""

    def test_measurable_when_summary_present(self):
        s = summarize_ci_security(_LIVE_FINDINGS, [], scan_date="x", source="y")
        assert grade_security_signal(s) == (True, 3)

    def test_clean_scan_is_measurable_zero(self):
        s = summarize_ci_security([], [], scan_date="x", source="y")
        assert grade_security_signal(s) == (True, 0)

    def test_none_summary_not_measurable(self):
        # No ingest yet → n/a, NOT a false 0 (which would read as "clean").
        assert grade_security_signal(None) == (False, None)

    def test_degraded_summary_not_measurable(self):
        s = summarize_ci_security([], [], scan_date="x", source="y", degraded=True)
        assert grade_security_signal(s) == (False, None)

    def test_garbage_open_count_not_measurable(self):
        assert grade_security_signal({"open_high_critical": -1}) == (False, None)
        assert grade_security_signal({"open_high_critical": "lots"}) == (False, None)
        assert grade_security_signal({}) == (False, None)


class TestRoundTrip:
    """Boundary probe (touches_io_boundary): write→load is loss-free."""

    def test_write_then_load_identity(self, tmp_path):
        s = summarize_ci_security(
            _LIVE_FINDINGS, [{"severity": "high"}],
            scan_date="2026-06-22T11:45:52+00:00", source="security.yml#1")
        path = write_ci_security(tmp_path, s)
        assert path.exists()
        assert path.name == "ci-security.json"
        loaded = load_ci_security(tmp_path)
        assert loaded == s

    def test_load_missing_returns_none(self, tmp_path):
        assert load_ci_security(tmp_path) is None

    def test_load_none_project_root_returns_none(self):
        # A fake ComplianceData with project_root=None must not crash the grader.
        assert load_ci_security(None) is None

    def test_load_corrupt_returns_none(self, tmp_path):
        p = tmp_path / ".shipwright" / "compliance" / "ci-security.json"
        p.parent.mkdir(parents=True)
        p.write_text("{not json", encoding="utf-8")
        assert load_ci_security(tmp_path) is None

    def test_written_file_is_tracked_under_compliance(self, tmp_path):
        write_ci_security(tmp_path, summarize_ci_security([], [], scan_date="x", source="y"))
        assert (tmp_path / ".shipwright" / "compliance" / "ci-security.json").exists()


class TestAcceptedRisks:
    """AC2 — parse the .trivyignore.yaml register, flag expired entries."""

    def _write(self, root, body=_TRIVYIGNORE):
        (root / ".trivyignore.yaml").write_text(body, encoding="utf-8")

    def test_parses_ids_and_expiry(self, tmp_path):
        self._write(tmp_path)
        rows = parse_accepted_risks(tmp_path, now=date(2026, 6, 28))
        ids = {r["id"]: r for r in rows}
        assert ids["CVE-2026-54285"]["expired_at"] == "2026-12-22"
        assert ids["CVE-2026-54285"]["expired"] is False
        # 2026-01-01 is in the past relative to now → expired
        assert ids["CVE-2025-00001"]["expired"] is True

    def test_missing_register_is_empty(self, tmp_path):
        assert parse_accepted_risks(tmp_path, now=date(2026, 6, 28)) == []

    def test_malformed_register_is_tolerated(self, tmp_path):
        (tmp_path / ".trivyignore.yaml").write_text("::: not yaml :::", encoding="utf-8")
        assert parse_accepted_risks(tmp_path, now=date(2026, 6, 28)) == []

    def test_entry_without_id_skipped(self, tmp_path):
        self._write(tmp_path, "vulnerabilities:\n  - paths: [a]\n    expired_at: 2026-12-22\n")
        assert parse_accepted_risks(tmp_path, now=date(2026, 6, 28)) == []


class TestRender:
    """AC4 — dashboard section: scan date, severity table, gate, register."""

    def _root_with_summary(self, root, findings=_LIVE_FINDINGS):
        write_ci_security(root, summarize_ci_security(
            findings, [], scan_date="2026-06-22T11:45:52+00:00",
            source="security.yml#27950188761"))
        (root / ".trivyignore.yaml").write_text(_TRIVYIGNORE, encoding="utf-8")

    def test_renders_scan_date_gate_and_table(self, tmp_path):
        self._root_with_summary(tmp_path)
        md = "\n".join(render_ci_security(tmp_path, now=date(2026, 6, 28)))
        assert "CI Security" in md
        assert "2026-06-22" in md            # scan date
        assert "PASS" in md                  # critical-gate
        assert "| High | 3 |" in md          # severity table row
        assert "CVE-2026-54285" in md        # accepted-risk register id
        assert "2026-12-22" in md            # expiry

    def test_gate_fail_renders_fail_badge(self, tmp_path):
        self._root_with_summary(tmp_path, findings=[{"severity": "critical"}])
        md = "\n".join(render_ci_security(tmp_path, now=date(2026, 6, 28)))
        assert "FAIL" in md

    def test_no_summary_renders_not_ingested_note(self, tmp_path):
        md = "\n".join(render_ci_security(tmp_path, now=date(2026, 6, 28)))
        assert "CI Security" in md
        assert "not" in md.lower()  # "not yet ingested" / "not available"

    def test_expired_accepted_risk_flagged(self, tmp_path):
        self._root_with_summary(tmp_path)
        md = "\n".join(render_ci_security(tmp_path, now=date(2027, 1, 1)))
        # both register entries now past expiry → flagged as expired
        assert "EXPIRED" in md.upper()


class TestGraderIntegration:
    """The grade adapter lights the Security dimension from the committed summary."""

    def _data(self, project_root):
        return SimpleNamespace(
            work_events=[], requirements=[], dependencies=[],
            project_root=project_root)

    def test_security_lit_from_committed_summary(self, tmp_path):
        write_ci_security(tmp_path, summarize_ci_security(
            _LIVE_FINDINGS, [], scan_date="2026-06-22T11:44:18Z",
            source="security.yml#1"))
        inp = build_grade_inputs(self._data(tmp_path))
        assert inp.security_measurable is True
        assert inp.security_open_high_critical == 3

    def test_security_na_without_summary(self, tmp_path):
        inp = build_grade_inputs(self._data(tmp_path))
        assert inp.security_measurable is False
        assert inp.security_open_high_critical is None


class TestRenderDate:
    """The event-pinned reference date keeps the AR-10 render deterministic."""

    def test_parses_iso_timestamp_prefix(self):
        assert render_date("2026-06-28T08:48:14.752152+00:00") == date(2026, 6, 28)

    def test_parses_bare_date(self):
        assert render_date("2026-06-22") == date(2026, 6, 22)

    def test_unparseable_falls_back_to_today(self):
        # No crash on an empty/garbage pinned timestamp.
        assert isinstance(render_date(""), date)
        assert isinstance(render_date("not-a-date"), date)
