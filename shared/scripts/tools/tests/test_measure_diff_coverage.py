"""Tests for measure_diff_coverage.py — the diff-coverage measurement tool.

Phase 1 of the diff-coverage roadmap (``iterate-2026-07-03-diff-coverage-measure-one-tier``).
The tool parses a ``coverage.xml`` (overall line-rate -> ``total``) and a diff-cover JSON
report (``diff`` = % of changed lines covered) and writes a **gitignored transient**
``.shipwright/coverage/diff_coverage.json``. It must **never** mutate the tracked
``shipwright_test_results.json`` (boundary probe) and must be absent-input safe.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure shared scripts are importable (package root = shared/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import types

import scripts.tools.measure_diff_coverage as mod
from scripts.tools.measure_diff_coverage import (
    build_payload,
    diff_percent_from_report,
    line_rate_percent,
    main as measure_main,
    run_diff_cover,
    write_transient,
)

# --------------------------------------------------------------------------- #
# Fixtures (inline — no real coverage run / no diff-cover subprocess)
# --------------------------------------------------------------------------- #
COVERAGE_XML = (
    '<?xml version="1.0" ?>\n'
    '<coverage line-rate="0.835" branch-rate="0" version="7.0" timestamp="0">\n'
    "  <packages/>\n"
    "</coverage>\n"
)

DIFF_REPORT_OK = {
    "report_name": ["coverage.xml"],
    "diff_name": "origin/main...HEAD",
    "src_stats": {"shared/scripts/tools/measure_diff_coverage.py": {"percent_covered": 90.0}},
    "total_num_lines": 40,
    "total_num_violations": 4,
    "total_percent_covered": 90,
    "num_changed_lines": 55,
}

DIFF_REPORT_NO_CHANGED_LINES = {
    "report_name": ["coverage.xml"],
    "src_stats": {},
    "total_num_lines": 0,
    "total_num_violations": 0,
    "total_percent_covered": 100,
    "num_changed_lines": 0,
}


# --------------------------------------------------------------------------- #
# line_rate_percent
# --------------------------------------------------------------------------- #
class TestLineRatePercent:
    def test_parses_root_line_rate(self, tmp_path):
        xml = tmp_path / "coverage.xml"
        xml.write_text(COVERAGE_XML, encoding="utf-8")
        assert line_rate_percent(xml) == 83.5

    def test_missing_attr_returns_none(self, tmp_path):
        xml = tmp_path / "coverage.xml"
        xml.write_text('<?xml version="1.0" ?>\n<coverage version="7.0"/>\n', encoding="utf-8")
        assert line_rate_percent(xml) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert line_rate_percent(tmp_path / "nope.xml") is None

    def test_malformed_xml_returns_none(self, tmp_path):
        xml = tmp_path / "coverage.xml"
        xml.write_text("not xml <<<", encoding="utf-8")
        assert line_rate_percent(xml) is None


# --------------------------------------------------------------------------- #
# diff_percent_from_report
# --------------------------------------------------------------------------- #
class TestDiffPercentFromReport:
    def test_reads_total_percent_covered(self):
        assert diff_percent_from_report(DIFF_REPORT_OK) == 90.0

    def test_zero_changed_lines_is_none(self):
        # No changed lines under coverage -> "n/a", not a misleading 100%.
        assert diff_percent_from_report(DIFF_REPORT_NO_CHANGED_LINES) is None

    def test_missing_key_returns_none(self):
        assert diff_percent_from_report({"total_num_lines": 10}) is None

    def test_non_dict_returns_none(self):
        assert diff_percent_from_report(None) is None
        assert diff_percent_from_report("nope") is None


# --------------------------------------------------------------------------- #
# build_payload
# --------------------------------------------------------------------------- #
class TestBuildPayload:
    def test_ok_shape(self):
        p = build_payload(total=83.5, diff=90.0, compare_branch="origin/main",
                          coverage_xml="coverage.xml")
        assert p["schema"] == "diff_coverage/v1"
        assert p["measured_tier"] == "shared"
        assert p["compare_branch"] == "origin/main"
        assert p["total"] == 83.5
        assert p["diff"] == 90.0
        assert p["status"] == "ok"

    def test_na_when_diff_none(self):
        p = build_payload(total=83.5, diff=None, compare_branch="origin/main",
                          coverage_xml="coverage.xml")
        assert p["status"] == "n/a"
        assert p["diff"] is None
        assert p.get("note")  # explains why


# --------------------------------------------------------------------------- #
# write_transient — atomic round-trip
# --------------------------------------------------------------------------- #
class TestWriteTransient:
    def test_roundtrip_creates_parent(self, tmp_path):
        out = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        payload = build_payload(total=83.5, diff=90.0, compare_branch="origin/main",
                                coverage_xml="coverage.xml")
        write_transient(out, payload)
        assert out.exists()
        assert json.loads(out.read_text(encoding="utf-8")) == payload


# --------------------------------------------------------------------------- #
# main — integration; NEVER touches the tracked results file (boundary probe)
# --------------------------------------------------------------------------- #
class TestMainCLI:
    def _write_inputs(self, root: Path, *, report):
        (root / "coverage.xml").write_text(COVERAGE_XML, encoding="utf-8")
        rep = root / "diff_report.json"
        rep.write_text(json.dumps(report), encoding="utf-8")
        return rep

    def test_writes_transient_from_report_json(self, tmp_path):
        rep = self._write_inputs(tmp_path, report=DIFF_REPORT_OK)
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(rep),
            "--compare-branch", "origin/main",
        ])
        assert rc == 0
        out = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["diff"] == 90.0
        assert data["total"] == 83.5
        assert data["status"] == "ok"

    def test_absent_coverage_xml_writes_na_exit0(self, tmp_path):
        # No coverage.xml, no report -> n/a, exit 0, transient still written.
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "missing.xml"),
        ])
        assert rc == 0
        out = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "n/a"
        assert data["diff"] is None

    def test_relative_paths_resolve_against_project_root(self, tmp_path, monkeypatch):
        # Codex review SHOULD-FIX: relative --coverage-xml / --diff-cover-json
        # must resolve against --project-root, not the process CWD, so a call
        # from outside the repo still finds the inputs.
        self._write_inputs(tmp_path, report=DIFF_REPORT_OK)
        elsewhere = tmp_path.parent / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", "coverage.xml",        # relative
            "--diff-cover-json", "diff_report.json",  # relative
        ])
        assert rc == 0
        data = json.loads(
            (tmp_path / ".shipwright" / "coverage" / "diff_coverage.json")
            .read_text(encoding="utf-8"))
        assert data["diff"] == 90.0
        assert data["total"] == 83.5  # coverage.xml WAS found (not a false n/a)

    def test_never_creates_results_json(self, tmp_path):
        self._write_inputs(tmp_path, report=DIFF_REPORT_OK)
        measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(tmp_path / "diff_report.json"),
        ])
        assert not (tmp_path / "shipwright_test_results.json").exists()

    def test_never_mutates_existing_results_json(self, tmp_path):
        # Boundary probe: a pre-existing tracked results file is byte-identical after.
        results = tmp_path / "shipwright_test_results.json"
        sentinel = json.dumps({"iterate_latest": {"run_id": "sentinel"}}, indent=2) + "\n"
        results.write_text(sentinel, encoding="utf-8")
        self._write_inputs(tmp_path, report=DIFF_REPORT_OK)
        measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(tmp_path / "diff_report.json"),
        ])
        assert results.read_text(encoding="utf-8") == sentinel

    def test_zero_changed_lines_reports_na(self, tmp_path):
        self._write_inputs(tmp_path, report=DIFF_REPORT_NO_CHANGED_LINES)
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(tmp_path / "diff_report.json"),
        ])
        assert rc == 0
        out = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["status"] == "n/a"
        assert data["diff"] is None
        # total is still parsed from coverage.xml even when diff is n/a
        assert data["total"] == 83.5


# --------------------------------------------------------------------------- #
# run_diff_cover — the subprocess path (mocked; no real diff-cover / git)
# --------------------------------------------------------------------------- #
class TestRunDiffCover:
    def _fake_run_writing(self, report: dict):
        """A subprocess.run stub that writes ``report`` to the --json-report
        path passed in argv and returns success."""
        def _run(cmd, **kwargs):
            idx = cmd.index("--json-report")
            Path(cmd[idx + 1]).write_text(json.dumps(report), encoding="utf-8")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        return _run

    def test_parses_report_from_subprocess(self, tmp_path, monkeypatch):
        cov = tmp_path / "coverage.xml"
        cov.write_text(COVERAGE_XML, encoding="utf-8")
        monkeypatch.setattr(mod.subprocess, "run",
                            self._fake_run_writing(DIFF_REPORT_OK))
        report = run_diff_cover(cov, "origin/main", tmp_path)
        assert diff_percent_from_report(report) == 90.0

    def test_missing_coverage_xml_returns_none(self, tmp_path):
        assert run_diff_cover(tmp_path / "nope.xml", "origin/main", tmp_path) is None

    def test_binary_absent_returns_none(self, tmp_path, monkeypatch):
        cov = tmp_path / "coverage.xml"
        cov.write_text(COVERAGE_XML, encoding="utf-8")

        def _boom(cmd, **kwargs):
            raise FileNotFoundError("diff-cover not installed")
        monkeypatch.setattr(mod.subprocess, "run", _boom)
        assert run_diff_cover(cov, "origin/main", tmp_path) is None

    def test_main_without_json_invokes_diff_cover(self, tmp_path, monkeypatch):
        (tmp_path / "coverage.xml").write_text(COVERAGE_XML, encoding="utf-8")
        monkeypatch.setattr(mod.subprocess, "run",
                            self._fake_run_writing(DIFF_REPORT_OK))
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
        ])
        assert rc == 0
        data = json.loads(
            (tmp_path / ".shipwright" / "coverage" / "diff_coverage.json")
            .read_text(encoding="utf-8"))
        assert data["diff"] == 90.0
        assert data["status"] == "ok"
