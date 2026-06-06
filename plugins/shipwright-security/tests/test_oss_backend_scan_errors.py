"""scan_errors — the degraded-scan marker channel of OSSBackend.

(iterate-2026-06-05-scanner-degraded-marker)

A scanner that is in `capabilities` and is invoked but produces no parseable
output ("degraded") must NOT be indistinguishable from a scanner that ran and
found nothing ("clean"). Every `None`-returning branch of `_run_tool` is the
degraded case and must record one structured marker on the `errors`
accumulator — while the *findings* return stays `[]` (no data-plane pollution).
The wrappers accept an optional `errors` collector; `scan()` owns one and
exposes it as `OSSBackend.scan_errors`.

The clean/findings-return behaviour of the runners lives in test_oss_backend.py;
this module is the degraded-channel counterpart.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from oss_backend import (  # noqa: E402
    OSSBackend,
    SCAN_ERROR_REASONS,
    _run_gitleaks,
    _run_semgrep,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _empty_report_gitleaks(returncode=1, stderr="FTL could not open repo: dubious ownership"):
    """gitleaks fatal: exit 1 (same code as 'leaks found'), empty report file."""
    def run(cmd, **_kwargs):
        # Report file left untouched (mkstemp created it empty) → empty payload.
        return MagicMock(returncode=returncode, stdout="", stderr=stderr)
    return run


class TestRunToolScanErrorReasons:
    """Each `None`-return branch records exactly one marker with a closed-vocab
    `reason`; the *findings* return remains `[]`."""

    def test_records_nonzero_exit(self):
        errors: list[dict] = []
        result = MagicMock(returncode=2, stdout="", stderr="semgrep internal error")
        with patch("subprocess.run", return_value=result):
            findings = _run_semgrep("/tmp/test", errors)
        assert findings == []
        assert len(errors) == 1
        assert errors[0]["scanner"] == "semgrep"
        assert errors[0]["reason"] == "nonzero_exit"
        assert "internal error" in errors[0]["detail"]

    def test_records_empty_output_semgrep(self):
        """returncode 0 but empty stdout — a semgrep/trivy that emitted no JSON
        envelope (crash). 'Applies to semgrep/trivy empty-stdout too.'"""
        errors: list[dict] = []
        result = MagicMock(returncode=0, stdout="   ", stderr="")
        with patch("subprocess.run", return_value=result):
            findings = _run_semgrep("/tmp/test", errors)
        assert findings == []
        assert [e["reason"] for e in errors] == ["empty_output"]
        assert errors[0]["scanner"] == "semgrep"

    def test_records_empty_output_gitleaks_fatal(self):
        """gitleaks fatal (expect_nonzero): exit 1 + empty report → empty_output,
        NOT a clean 0-findings leg."""
        errors: list[dict] = []
        with patch("subprocess.run", side_effect=_empty_report_gitleaks()):
            findings = _run_gitleaks("/tmp/test", errors)
        assert findings == []
        assert len(errors) == 1
        assert errors[0]["scanner"] == "gitleaks"
        assert errors[0]["reason"] == "empty_output"
        assert "dubious ownership" in errors[0]["detail"]

    def test_records_timeout(self):
        errors: list[dict] = []
        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="gitleaks", timeout=300)):
            findings = _run_gitleaks("/tmp/test", errors)
        assert findings == []
        assert [e["reason"] for e in errors] == ["timeout"]

    def test_records_invalid_json(self):
        errors: list[dict] = []

        def garbage(cmd, **_kwargs):
            report_path = cmd[cmd.index("--report-path") + 1]
            Path(report_path).write_text("[ {not valid json", encoding="utf-8")
            return MagicMock(returncode=1, stdout="", stderr="")

        with patch("subprocess.run", side_effect=garbage):
            findings = _run_gitleaks("/tmp/test", errors)
        assert findings == []
        assert [e["reason"] for e in errors] == ["invalid_json"]

    def test_records_missing_binary(self):
        errors: list[dict] = []
        with patch("subprocess.run", side_effect=FileNotFoundError):
            findings = _run_gitleaks("/tmp/test", errors)
        assert findings == []
        assert [e["reason"] for e in errors] == ["missing_binary"]

    def test_clean_scan_records_nothing(self):
        """A legitimate clean leg (valid empty JSON envelope) records no marker."""
        errors: list[dict] = []
        result = MagicMock(returncode=0, stdout='{"results": []}', stderr="")
        with patch("subprocess.run", return_value=result):
            findings = _run_semgrep("/tmp/test", errors)
        assert findings == []
        assert errors == []

    def test_no_collector_is_a_silent_noop(self):
        """Back-compat: calling a runner WITHOUT an errors collector still
        degrades to [] and does not raise (existing direct-call tests)."""
        with patch("subprocess.run", side_effect=_empty_report_gitleaks()):
            assert _run_gitleaks("/tmp/test") == []

    def test_every_reason_is_in_closed_vocab(self):
        """Drift guard: every reason a runner can emit must be declared in
        SCAN_ERROR_REASONS (so the report/gate layer can rely on the set)."""
        observed: set[str] = set()

        def collect(run_side_effect, runner):
            errs: list[dict] = []
            with patch("subprocess.run", side_effect=run_side_effect):
                runner("/tmp/test", errs)
            observed.update(e["reason"] for e in errs)

        collect(_empty_report_gitleaks(), _run_gitleaks)
        collect(subprocess.TimeoutExpired(cmd="x", timeout=1), _run_gitleaks)
        collect(FileNotFoundError(), _run_gitleaks)

        def nonzero(cmd, **_k):
            return MagicMock(returncode=2, stdout="", stderr="boom")
        collect(nonzero, _run_semgrep)

        assert observed, "no reasons observed — test is inert"
        assert observed.issubset(set(SCAN_ERROR_REASONS)), (
            f"reasons {observed - set(SCAN_ERROR_REASONS)} not in SCAN_ERROR_REASONS"
        )


class TestOSSBackendScanErrors:
    """`OSSBackend.scan` owns the accumulator and exposes it as `scan_errors`."""

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t)
    def test_scan_errors_empty_on_clean(self, mock_which):
        semgrep_fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        trivy_fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        gitleaks_fixture = json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())

        def mock_run(cmd, **kwargs):
            result = MagicMock(stderr="")
            if "semgrep" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(semgrep_fixture)
            elif "trivy" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(trivy_fixture)
            elif "gitleaks" in cmd[0]:
                report_path = cmd[cmd.index("--report-path") + 1]
                Path(report_path).write_text(json.dumps(gitleaks_fixture), encoding="utf-8")
                result.returncode = 1
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test")

        assert len(findings) == 8
        assert backend.scan_errors == []

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t)
    def test_scan_errors_populated_on_degraded_leg(self, mock_which):
        """gitleaks fatals (empty report); semgrep + trivy succeed. The secrets
        leg is degraded → one marker; the other two legs' findings survive."""
        semgrep_fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        trivy_fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())

        def mock_run(cmd, **kwargs):
            result = MagicMock(stderr="")
            if "semgrep" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(semgrep_fixture)
            elif "trivy" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(trivy_fixture)
            elif "gitleaks" in cmd[0]:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "FTL could not open repo: dubious ownership"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test")

        # semgrep (3) + trivy (3) findings are NOT lost; gitleaks degraded → 0.
        assert len(findings) == 6
        assert all(f["source"] in ("semgrep", "trivy") for f in findings)
        assert len(backend.scan_errors) == 1
        marker = backend.scan_errors[0]
        assert marker["scanner"] == "gitleaks"
        assert marker["reason"] == "empty_output"
        assert "dubious ownership" in marker["detail"]

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/gitleaks" if t == "gitleaks" else None)
    def test_scan_errors_reset_between_calls(self, mock_which):
        """A second scan() must not inherit the first scan's markers."""
        backend = OSSBackend()

        with patch("subprocess.run", side_effect=_empty_report_gitleaks()):
            backend.scan("/tmp/test")
        assert len(backend.scan_errors) == 1

        # Second scan: gitleaks clean (writes []).
        def clean(cmd, **_kwargs):
            report_path = cmd[cmd.index("--report-path") + 1]
            Path(report_path).write_text("[]", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=clean):
            backend.scan("/tmp/test")
        assert backend.scan_errors == []
