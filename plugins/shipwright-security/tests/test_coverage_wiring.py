"""End-to-end wiring + round-trip tests for the coverage manifest.

Covers the producer/consumer pairs declared in the iterate spec's Affected
Boundaries table (``touches_io_boundary`` → Boundary Probe):

    scan.py            -> findings.json      -> generate_security_report.py
    build_json_sidecar -> latest.json        -> scan_compare.py
    run_scan_and_report-> history/scan-*.json-> compare_scans.py

Each pair is asserted by writing with the real producer and reading with the
real consumer, so a shape change on one side cannot pass unnoticed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
sys.path.insert(0, str(PLUGIN_ROOT.parent.parent / "shared" / "scripts"))

from test_hygiene import is_ci  # noqa: E402
import generate_security_report as gsr  # noqa: E402
import scan as scan_cli  # noqa: E402
from scan_coverage import build_coverage  # noqa: E402

SCAN_PY = PLUGIN_ROOT / "scripts" / "tools" / "scan.py"
COMPARE_PY = PLUGIN_ROOT / "scripts" / "tools" / "compare_scans.py"

_FINDING = {
    "id": "f1", "severity": "high", "type": "sast", "rule": "r1",
    "source": "semgrep", "affected_file": "a.py", "affected_line": 3,
    "description": "boom",
}


class _Backend:
    """Minimal stand-in for a scanner backend."""

    name = "oss"

    def __init__(self, caps: set[str], findings=None, errors=None) -> None:
        self.capabilities = caps
        self.scan_errors = errors or []
        self._findings = findings or []

    def scan(self, target, scan_types=None):  # noqa: ARG002
        return list(self._findings)


@pytest.mark.covers("FR-01.07")
class TestScanCliWritesCoverage:
    def test_findings_json_names_the_missing_tools(self, tmp_path: Path) -> None:
        out = tmp_path / "findings.json"
        with patch.object(scan_cli, "get_backend", return_value=_Backend({"sast"})):
            with patch.object(sys, "argv", [
                "scan.py", "--path", str(tmp_path), "--output", str(out),
            ]):
                assert scan_cli.main() == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        statuses = {r["class"]: r["status"] for r in payload["coverage"]}
        assert statuses == {
            "sast": "covered", "sca": "not_available", "secrets": "not_available",
        }

    def test_coverage_survives_the_input_from_cache_round_trip(
        self, tmp_path: Path
    ) -> None:
        """A re-read must not forget which classes the cached scan covered —
        otherwise the SARIF step re-emits a manifest-less, clean-looking file."""
        first = tmp_path / "findings.json"
        with patch.object(scan_cli, "get_backend", return_value=_Backend({"sast"})):
            with patch.object(sys, "argv", [
                "scan.py", "--path", str(tmp_path), "--output", str(first),
            ]):
                scan_cli.main()
        original = json.loads(first.read_text(encoding="utf-8"))["coverage"]

        second = tmp_path / "again.json"
        with patch.object(sys, "argv", [
            "scan.py", "--path", str(tmp_path), "--output", str(second),
            "--input-from-cache", str(first),
        ]):
            scan_cli.main()
        assert json.loads(second.read_text(encoding="utf-8"))["coverage"] == original

    def test_scan_types_filter_reads_as_not_requested(self, tmp_path: Path) -> None:
        out = tmp_path / "findings.json"
        backend = _Backend({"sast", "sca", "secrets"})
        with patch.object(scan_cli, "get_backend", return_value=backend):
            with patch.object(sys, "argv", [
                "scan.py", "--path", str(tmp_path), "--output", str(out),
                "--scan-types", "sast",
            ]):
                scan_cli.main()
        statuses = {
            r["class"]: r["status"]
            for r in json.loads(out.read_text(encoding="utf-8"))["coverage"]
        }
        assert statuses["sca"] == "not_requested"

    @pytest.mark.slow
    def test_real_subprocess_emits_valid_json_with_coverage(
        self, tmp_path: Path
    ) -> None:
        """Cross-process probe: the file scan.py actually writes parses, and
        the coverage key is there even when no scanner is installed."""
        out = tmp_path / "findings.json"
        proc = subprocess.run(
            [sys.executable, str(SCAN_PY), "--path", str(tmp_path),
             "--output", str(out)],
            capture_output=True, text=True,
        )
        if proc.returncode == 2 and not out.exists():
            msg = (
                "no scanner backend configured, so scan.py could not write a "
                "findings.json to probe. Install at least one scanner: "
                "`pip install semgrep`, or see "
                "plugins/shipwright-security/skills/security/references/"
                "oss-scanners.md. "
                f"stderr: {proc.stderr[:300]}"
            )
            if is_ci():
                pytest.fail(msg, pytrace=False)
            pytest.skip(msg)
        assert "coverage" in json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.covers("FR-01.07")
class TestReportRendersCoverage:
    def test_report_banner_names_the_unchecked_classes(self) -> None:
        report = gsr.generate_standard_report(
            [], "o/r", None, build_coverage(available={"sast"}))
        assert "Incomplete Coverage" in report
        assert "Leaked secrets" in report

    def test_complete_coverage_shows_no_banner(self) -> None:
        report = gsr.generate_standard_report(
            [], "o/r", None, build_coverage(available={"sast", "sca", "secrets"}))
        assert "Incomplete Coverage" not in report
        assert "## Coverage" in report

    def test_absent_manifest_reads_as_not_reported_not_clean(self) -> None:
        report = gsr.generate_standard_report([], "o/r", None, None)
        assert "Coverage not reported" in report

    def test_pr_report_also_carries_the_banner(self) -> None:
        report = gsr.generate_pr_report(
            [], "o/r", None, build_coverage(available={"sast"}))
        assert "Incomplete Coverage" in report

    def test_sidecar_carries_coverage_and_keeps_schema_version_1(self) -> None:
        sidecar = gsr.build_json_sidecar(
            [], "o/r", None, build_coverage(available={"sast"}))
        assert sidecar["schema_version"] == 1
        assert [r["class"] for r in sidecar["coverage"]] == ["sast", "sca", "secrets"]


@pytest.mark.covers("FR-01.07")
class TestReportCliRoundTrip:
    def test_findings_json_coverage_reaches_the_markdown_and_the_sidecar(
        self, tmp_path: Path
    ) -> None:
        """The pair that matters: scan.py writes, the report generator reads."""
        findings_json = tmp_path / "findings.json"
        with patch.object(scan_cli, "get_backend",
                          return_value=_Backend({"sast"}, [_FINDING])):
            with patch.object(sys, "argv", [
                "scan.py", "--path", str(tmp_path), "--output", str(findings_json),
            ]):
                scan_cli.main()

        md_out = tmp_path / "report.md"
        json_out = tmp_path / "latest.json"
        with patch.object(sys, "argv", [
            "generate_security_report.py",
            "--project-root", str(tmp_path),
            "--input", str(findings_json),
            "--output", str(md_out),
            "--json-output", str(json_out),
            "--repo", "o/r",
        ]):
            assert gsr.main() == 0

        assert "Incomplete Coverage" in md_out.read_text(encoding="utf-8")
        sidecar = json.loads(json_out.read_text(encoding="utf-8"))
        statuses = {r["class"]: r["status"] for r in sidecar["coverage"]}
        assert statuses["secrets"] == "not_available"
        # the prompt-injection class is named too, not silently omitted
        assert statuses["prompt_injection"] == "not_requested"

    def test_prompt_risks_flag_marks_the_class_covered(self, tmp_path: Path) -> None:
        """Even with no scanner manifest to attach to: the prompt scan really
        ran, so recording it adds knowledge."""
        prompt_risks = tmp_path / "prompt_risks.json"
        prompt_risks.write_text(json.dumps({"findings": []}), encoding="utf-8")
        json_out = tmp_path / "latest.json"
        with patch.object(sys, "argv", [
            "generate_security_report.py",
            "--project-root", str(tmp_path),
            "--prompt-risks", str(prompt_risks),
            "--json-output", str(json_out),
        ]):
            gsr.main()
        statuses = {
            r["class"]: r["status"]
            for r in json.loads(json_out.read_text(encoding="utf-8"))["coverage"]
        }
        assert statuses["prompt_injection"] == "covered"


# The wrapper -> sidecar -> comparison round-trip lives in
# test_coverage_comparison_wiring.py; the card actually landing in
# .shipwright/triage.jsonl is asserted in shared/tests/test_security_scan_card.py
# (importing the shared `triage` module from a plugin pytest session hits the
# ADR-044 `lib` namespace collision, which is why the sibling producer test for
# the per-finding mirrors already lives under shared/tests/).
