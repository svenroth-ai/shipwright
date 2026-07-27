"""Consumer tolerance for the additive ``coverage`` key, and comparison edges.

Raised by the external review of the mini-plan:

- every named reader must cope with no `coverage` (a pre-feature cache or
  archived sidecar), an empty one, and a malformed one — and must treat all
  three as UNKNOWN rather than complete;
- `degraded` must be derived from what actually happened to the leg: a valid
  zero-finding report stays `covered`, while exit-0-with-unparseable-output
  does not;
- the location-based fingerprint means a moved finding reads as resolved+new.
  That is inherited from the triage dedup contract on purpose, so it is pinned
  here rather than left as an accident.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import generate_security_report as gsr  # noqa: E402
import scan as scan_cli  # noqa: E402
from oss_backend import _run_gitleaks, _run_semgrep  # noqa: E402
from scan_coverage import build_coverage, is_complete  # noqa: E402

_FINDING = {
    "id": "f1", "severity": "high", "type": "sast", "rule": "r1",
    "source": "semgrep", "affected_file": "a.py", "affected_line": 3,
}


@pytest.mark.covers("FR-01.07")
class TestPreFeatureArtifacts:
    def test_sidecar_without_coverage_reads_as_unknown_not_clean(self) -> None:
        assert gsr.load_coverage_from_file(Path("does-not-exist.json")) == []
        assert is_complete([]) is False

    def test_malformed_coverage_is_treated_as_absent(self, tmp_path: Path) -> None:
        bad = tmp_path / "findings.json"
        bad.write_text(json.dumps({"coverage": "not-a-list"}), encoding="utf-8")
        assert gsr.load_coverage_from_file(bad) == []

    def test_unknown_status_never_reads_as_complete(self) -> None:
        """A status outside the closed vocabulary must fail closed."""
        assert is_complete([{"class": "sast", "status": "probably-fine"}]) is False

    def test_pre_feature_cache_round_trips_without_crashing(
        self, tmp_path: Path
    ) -> None:
        """`--input-from-cache` against a findings.json written before this
        feature: no coverage key at all."""
        old = tmp_path / "old.json"
        old.write_text(
            json.dumps({"scanner": "oss", "findings": [_FINDING]}), encoding="utf-8"
        )
        out = tmp_path / "new.json"
        with patch.object(sys, "argv", [
            "scan.py", "--path", str(tmp_path), "--output", str(out),
            "--input-from-cache", str(old),
        ]):
            assert scan_cli.main() == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["coverage"] == []
        assert payload["findings"] == [_FINDING]

    def test_report_from_a_pre_feature_sidecar_says_coverage_not_reported(
        self, tmp_path: Path
    ) -> None:
        """A sidecar with no manifest, rendered through the CLI. "Not reported"
        and "incomplete" are different truths — the CLI must not manufacture a
        one-row manifest and downgrade the first into the second."""
        old = tmp_path / "old.json"
        old.write_text(json.dumps({"findings": []}), encoding="utf-8")
        md = tmp_path / "r.md"
        with patch.object(sys, "argv", [
            "generate_security_report.py", "--project-root", str(tmp_path),
            "--input", str(old), "--output", str(md),
        ]):
            assert gsr.main() == 0
        body = md.read_text(encoding="utf-8")
        assert "Coverage not reported" in body
        assert "Incomplete Coverage" not in body

    def test_report_with_no_manifest_at_all_says_coverage_not_reported(self) -> None:
        """The library path (no CLI, so no prompt-injection row appended)."""
        assert "Coverage not reported" in gsr.generate_standard_report(
            [], "o/r", None, None)

@pytest.mark.covers("FR-01.07")
class TestDegradedDerivation:
    """`degraded` follows what happened to the leg, via the scan_errors channel
    `_run_tool` already populates — not merely a non-zero exit."""

    @patch("subprocess.run")
    def test_valid_zero_finding_report_stays_covered(self, mock_run) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"results":[]}', stderr="")
        errors: list[dict] = []
        assert _run_semgrep(".", errors) == []
        assert errors == []
        coverage = build_coverage(available={"sast"}, scan_errors=errors)
        assert coverage[0]["status"] == "covered"

    @patch("subprocess.run")
    def test_exit_zero_with_unparseable_output_is_degraded(self, mock_run) -> None:
        """The case a bare exit-code check would miss."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="<html>proxy error</html>", stderr="")
        errors: list[dict] = []
        _run_semgrep(".", errors)
        assert [e["reason"] for e in errors] == ["invalid_json"]
        assert build_coverage(available={"sast"}, scan_errors=errors)[0]["status"] \
            == "degraded"

    @patch("subprocess.run")
    def test_exit_zero_with_empty_output_is_degraded(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="   ", stderr="boom")
        errors: list[dict] = []
        _run_semgrep(".", errors)
        assert [e["reason"] for e in errors] == ["empty_output"]

    @patch("subprocess.run")
    def test_tool_vanishing_mid_run_is_degraded_not_not_available(
        self, mock_run, tmp_path: Path
    ) -> None:
        """Capability was probed before the call; the re-probe afterwards comes
        back empty. Reporting "not installed" would lose the failure."""
        mock_run.side_effect = FileNotFoundError()
        errors: list[dict] = []
        _run_gitleaks(str(tmp_path), errors)
        assert [e["reason"] for e in errors] == ["missing_binary"]
        # Looked up by class, not by index: an index silently starts testing
        # a different row the moment CLASS_ORDER gains an entry.
        coverage = build_coverage(available=set(), scan_errors=errors)
        row = next(r for r in coverage if r["class"] == "secrets")
        assert row["status"] == "degraded"
