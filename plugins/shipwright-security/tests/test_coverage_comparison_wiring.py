"""Round-trip tests: what the wrapper writes is what the comparison reads.

Split out of ``test_coverage_wiring.py`` (which covers the scan CLI and the
report renderer) to keep both files under the 300-LOC guideline.

Boundary pairs asserted here — producer to disk to consumer, never a hand-built
fixture, because a fixture cannot catch a producer that changed shape:

    run_scan_and_report -> latest.json / history/scan-*.json -> scan_compare
    run_scan_and_report -> report directory                  -> compare_scans CLI
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

import run_scan_and_report as rsr  # noqa: E402
from scan_compare import compare_scans  # noqa: E402
from scan_coverage import build_coverage  # noqa: E402

_FINDING = {
    "id": "f1", "severity": "high", "type": "sast", "rule": "r1",
    "source": "semgrep", "affected_file": "a.py", "affected_line": 3,
    "description": "boom",
}


class _Backend:
    """Minimal stand-in for a scanner backend."""

    name = "oss"

    def __init__(self, caps: set[str], findings: list[dict] | None = None) -> None:
        self.capabilities = caps
        self.scan_errors: list[dict] = []
        self._findings = findings or []

    def scan(self, target, scan_types=None):  # noqa: ARG002
        return list(self._findings)


def _run(tmp_path: Path, caps: set[str], findings: list[dict]) -> dict:
    with patch.object(rsr, "get_backend", return_value=_Backend(caps, findings)):
        rsr.run(project_root=tmp_path, repo="o/r")
    return json.loads(
        (tmp_path / rsr.REPORTS_DIR / rsr.LATEST_JSON).read_text(encoding="utf-8")
    )


@pytest.mark.covers("FR-01.07")
class TestWrapperRoundTrip:
    def test_latest_json_and_history_carry_the_same_manifest(
        self, tmp_path: Path
    ) -> None:
        latest = _run(tmp_path, {"sast"}, [_FINDING])
        history = list((tmp_path / rsr.REPORTS_DIR / "history").glob("*.json"))
        assert len(history) == 1
        archived = json.loads(history[0].read_text(encoding="utf-8"))
        assert archived["coverage"] == latest["coverage"]
        assert archived["scan_id"] == latest["scan_id"]

    def test_written_sidecars_feed_the_comparison_unchanged(
        self, tmp_path: Path
    ) -> None:
        monday = _run(tmp_path, {"sast", "secrets"}, [_FINDING])
        tuesday = _run(tmp_path, {"sast", "secrets"}, [])
        assert compare_scans(monday, tuesday)["counts"]["resolved"] == 1

    def test_losing_a_tool_between_runs_reports_nothing_fixed(
        self, tmp_path: Path
    ) -> None:
        """The failure this feature exists to prevent: gitleaks is uninstalled
        between Monday and Tuesday, every secret finding vanishes from the
        output, and none of them was fixed."""
        secret = {**_FINDING, "source": "gitleaks", "type": "secret_detection"}
        monday = _run(tmp_path, {"sast", "secrets"}, [secret])
        tuesday = _run(tmp_path, {"sast"}, [])
        result = compare_scans(monday, tuesday)
        assert result["counts"]["resolved"] == 0
        assert any(e["class"] == "secrets" for e in result["not_comparable"])

    def test_gaining_a_tool_between_runs_reports_nothing_new(
        self, tmp_path: Path
    ) -> None:
        """Symmetric: findings from a class Monday never checked are not new."""
        secret = {**_FINDING, "source": "gitleaks", "type": "secret_detection"}
        monday = _run(tmp_path, {"sast"}, [])
        tuesday = _run(tmp_path, {"sast", "secrets"}, [secret])
        result = compare_scans(monday, tuesday)
        assert result["counts"]["new"] == 0


@pytest.mark.covers("FR-01.07")
class TestCompareCli:
    def _cli(self):
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
        import compare_scans as cli  # noqa: PLC0415

        return cli

    def test_cli_renders_a_comparison_from_the_report_directory(
        self, tmp_path: Path, capsys
    ) -> None:
        caps = {"sast", "sca", "secrets"}
        _run(tmp_path, caps, [_FINDING])
        _run(tmp_path, caps, [])
        with patch.object(sys, "argv",
                          ["compare_scans.py", "--project-root", str(tmp_path)]):
            assert self._cli().main() == 0
        assert "**Fixed:** 1" in capsys.readouterr().out

    def test_cli_names_the_classes_it_could_not_compare(
        self, tmp_path: Path, capsys
    ) -> None:
        _run(tmp_path, {"sast", "secrets"}, [_FINDING])
        _run(tmp_path, {"sast"}, [])
        with patch.object(sys, "argv",
                          ["compare_scans.py", "--project-root", str(tmp_path)]):
            self._cli().main()
        out = capsys.readouterr().out
        assert "Not compared" in out
        assert "secrets" in out

    def test_cli_exits_2_without_a_previous_scan(self, tmp_path: Path) -> None:
        with patch.object(sys, "argv",
                          ["compare_scans.py", "--project-root", str(tmp_path)]):
            assert self._cli().main() == 2


@pytest.mark.covers("FR-01.07")
class TestBackendUnchanged:
    def test_no_backend_has_to_populate_coverage(self) -> None:
        """The manifest is derived, so a backend (or a MagicMock) that knows
        nothing about coverage still produces an honest one — the reason this
        is not a second ``scan_errors``-style backend-populated channel."""
        mock = MagicMock()
        mock.capabilities = {"sast"}
        assert len(build_coverage(available=mock.capabilities)) == 3
