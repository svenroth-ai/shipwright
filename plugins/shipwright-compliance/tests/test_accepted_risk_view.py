"""The dashboard's accepted-risk view — correlated, not concatenated.

The old view could only show ``.trivyignore.yaml`` entries, so a Semgrep or
CI-posture acceptance was invisible and a repo using the classic flat
``.trivyignore`` (which the scanner honours) had suppression with no visibility
at all. These tests pin the widened behaviour, and in particular the distinction
the section exists to make: *suppressed* is not the same as *accepted*.
"""

from __future__ import annotations

from datetime import date

from scripts.lib.accepted_risk_view import (
    SOURCE_REGISTERED_ACTIVE,
    SOURCE_REGISTERED_ONLY,
    SOURCE_UNREGISTERED,
    accepted_risk_rows,
    parse_trivyignore,
)
from scripts.lib.ci_security import (
    render_ci_security,
    summarize_ci_security,
    write_ci_security,
)

_NOW = date(2026, 6, 28)

_REGISTER = """\
schema: 1
acceptances:
  - id: ar-test-cve
    target: trivy-ignore
    rule: CVE-2026-54285
    expires: 2026-12-22
    rationale_ref: iterate-2026-06-22-trivy-risk-accept
    statement: >-
      Dev-only transitive dependency, the vulnerable path is not reachable here.
"""

_TRIVYIGNORE = """\
vulnerabilities:
  - id: CVE-2026-54285
    paths: ["a/b"]
    expired_at: 2026-12-22
    statement: x
"""


def _repo(tmp_path, *, register=None, trivy=None):
    if register:
        (tmp_path / "shipwright_accepted_risks.yaml").write_text(
            register, encoding="utf-8")
    if trivy:
        (tmp_path / ".trivyignore.yaml").write_text(trivy, encoding="utf-8")
    return tmp_path


class TestCorrelation:
    def test_registered_and_active_is_one_row(self, tmp_path):
        rows, note = accepted_risk_rows(
            _repo(tmp_path, register=_REGISTER, trivy=_TRIVYIGNORE), now=_NOW)
        assert note is None
        assert len(rows) == 1, "register + suppression must correlate into ONE row"
        assert rows[0]["source"] == SOURCE_REGISTERED_ACTIVE
        assert rows[0]["id"] == "ar-test-cve"

    def test_register_entry_without_suppression_is_flagged(self, tmp_path):
        rows, _ = accepted_risk_rows(_repo(tmp_path, register=_REGISTER), now=_NOW)
        assert [r["source"] for r in rows] == [SOURCE_REGISTERED_ONLY]

    def test_suppression_without_register_entry_is_drift(self, tmp_path):
        rows, _ = accepted_risk_rows(_repo(tmp_path, trivy=_TRIVYIGNORE), now=_NOW)
        assert [r["source"] for r in rows] == [SOURCE_UNREGISTERED]

    def test_audit_fields_reach_the_row(self, tmp_path):
        rows, _ = accepted_risk_rows(
            _repo(tmp_path, register=_REGISTER, trivy=_TRIVYIGNORE), now=_NOW)
        assert rows[0]["rationale_ref"] == "iterate-2026-06-22-trivy-risk-accept"
        assert "not reachable" in rows[0]["statement"]

    def test_expiry_is_computed_against_now(self, tmp_path):
        root = _repo(tmp_path, register=_REGISTER, trivy=_TRIVYIGNORE)
        assert accepted_risk_rows(root, now=date(2027, 1, 1))[0][0]["expired"] is True
        assert accepted_risk_rows(root, now=_NOW)[0][0]["expired"] is False


class TestDegradation:
    def test_malformed_register_is_announced_not_silently_empty(self, tmp_path):
        rows, note = accepted_risk_rows(
            _repo(tmp_path, register="schema: 1\nacceptances: [broken\n"), now=_NOW)
        assert rows == []
        assert note and "INVALID" in note, (
            "an unreadable register must never render as 'nothing accepted'")

    def test_absent_register_is_not_a_degradation(self, tmp_path):
        _rows, note = accepted_risk_rows(_repo(tmp_path, trivy=_TRIVYIGNORE), now=_NOW)
        assert note is None


class TestTrivyignoreForms:
    def test_classic_flat_file_is_read(self, tmp_path):
        (tmp_path / ".trivyignore").write_text(
            "# comment\nCVE-2026-1\n\nCVE-2026-2\n", encoding="utf-8")
        assert {e["id"] for e in parse_trivyignore(tmp_path)} == {
            "CVE-2026-1", "CVE-2026-2"}

    def test_yaml_form_carries_scope(self, tmp_path):
        entries = parse_trivyignore(_repo(tmp_path, trivy=_TRIVYIGNORE))
        assert entries[0]["scope"] == ["a/b"]

    def test_missing_file_is_empty(self, tmp_path):
        assert parse_trivyignore(tmp_path) == []


class TestRenderedSection:
    def _with_summary(self, root):
        write_ci_security(root, summarize_ci_security(
            [], [], scan_date="2026-06-22T00:00:00+00:00", source="security.yml#1"))
        return root

    def test_unregistered_suppression_is_not_laundered_into_accepted(self, tmp_path):
        root = self._with_summary(_repo(tmp_path, trivy=_TRIVYIGNORE))
        md = "\n".join(render_ci_security(root, now=_NOW))
        assert "UNRECORDED" in md
        assert "CVE-2026-54285" in md

    def test_registered_entry_renders_its_authority(self, tmp_path):
        root = self._with_summary(_repo(tmp_path, register=_REGISTER, trivy=_TRIVYIGNORE))
        md = "\n".join(render_ci_security(root, now=_NOW))
        assert "iterate-2026-06-22-trivy-risk-accept" in md
        assert "UNRECORDED" not in md

    def test_expired_and_unrecorded_are_both_reported(self, tmp_path):
        # Composed status: reporting only the first fact would hide the other.
        root = self._with_summary(_repo(tmp_path, trivy=_TRIVYIGNORE))
        md = "\n".join(render_ci_security(root, now=date(2027, 1, 1)))
        assert "UNRECORDED" in md and "EXPIRED" in md

    def test_degradation_note_is_rendered(self, tmp_path):
        root = self._with_summary(
            _repo(tmp_path, register="schema: 1\nacceptances: [broken\n"))
        md = "\n".join(render_ci_security(root, now=_NOW))
        assert "INVALID" in md


class TestFallbackAndEdges:
    """Branches that only fire when something is missing or broken.

    The dashboard must degrade LOUDLY: every path here still produces either a
    row or a note, never a quietly empty table that reads as 'nothing accepted'.
    """

    def test_datetime_expiry_is_narrowed_to_a_date(self):
        from datetime import datetime
        from scripts.lib.accepted_risk_view import _coerce_date
        # datetime is a SUBCLASS of date, so order of checks matters.
        assert _coerce_date(datetime(2026, 12, 22, 8, 30)) == date(2026, 12, 22)
        assert _coerce_date(date(2026, 12, 22)) == date(2026, 12, 22)
        assert _coerce_date("2026-12-22T00:00:00Z") == date(2026, 12, 22)
        assert _coerce_date("not-a-date") is None
        assert _coerce_date(None) is None
        assert _coerce_date(12345) is None

    def test_falls_back_to_trivy_only_when_the_shared_reader_is_missing(
            self, tmp_path, monkeypatch):
        import scripts.lib.accepted_risk_view as view
        monkeypatch.setattr(view, "_load_shared", lambda: None)
        rows, note = view.accepted_risk_rows(
            _repo(tmp_path, trivy=_TRIVYIGNORE), now=_NOW)
        assert note and "register reader unavailable" in note
        assert [r["id"] for r in rows] == ["CVE-2026-54285"]

    def test_github_dismissal_is_recorded_but_not_claimed_active(self, tmp_path):
        register = (
            "schema: 1\nacceptances:\n"
            "  - id: ar-test-codeql\n    target: github-dismissal\n"
            "    rule: py/some-query\n    expires: 2099-01-01\n"
            "    rationale_ref: ADR-271\n"
            "    statement: >-\n      A sufficiently long justification here.\n"
        )
        rows, _ = accepted_risk_rows(_repo(tmp_path, register=register), now=_NOW)
        # Its counterpart is live GitHub state, so it can never read as verified.
        assert rows[0]["source"] == SOURCE_REGISTERED_ONLY

    def test_discovery_failure_does_not_crash_the_dashboard(
            self, tmp_path, monkeypatch):
        import scripts.lib.accepted_risk_view as view
        shared = view._load_shared()
        assert shared is not None
        accepted_risks, scan = shared

        def _boom(*_a, **_kw):
            raise RuntimeError("discovery exploded")

        monkeypatch.setattr(scan, "discovered_suppressions", _boom)
        rows, note = view.accepted_risk_rows(
            _repo(tmp_path, register=_REGISTER), now=_NOW)
        # The register still renders; only the "is it wired up" half is lost.
        assert note is None
        assert [r["id"] for r in rows] == ["ar-test-cve"]

    def test_unreadable_trivyignore_yields_no_rows(self, tmp_path, monkeypatch):
        from pathlib import Path as _P
        (tmp_path / ".trivyignore").write_text("CVE-1\n", encoding="utf-8")

        def _boom(*_a, **_kw):
            raise OSError("permission denied")

        monkeypatch.setattr(_P, "read_text", _boom)
        assert parse_trivyignore(tmp_path) == []

    def test_malformed_trivyignore_yaml_yields_no_rows(self, tmp_path):
        (tmp_path / ".trivyignore.yaml").write_text("[oops\n - x", encoding="utf-8")
        assert parse_trivyignore(tmp_path) == []

    def test_non_mapping_trivyignore_yields_no_rows(self, tmp_path):
        (tmp_path / ".trivyignore.yaml").write_text("- a\n- b\n", encoding="utf-8")
        assert parse_trivyignore(tmp_path) == []
