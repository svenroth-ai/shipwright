"""Tests for record_coverage_total.py + the W4 round-trip (the touches_io_boundary
Boundary Probe).

The producer (this recorder) writes ``shipwright_test_results.json.coverage.total``;
the consumer (W4, ``tools/verifiers/test_compliance.py``) reads it against
``shipwright_test_config.json.coverage.min``. The round-trip test proves the two
halves of the boundary agree: a real total + a calibrated min => W4 PASS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # shared/scripts

from scripts.tools.record_coverage_total import (
    main as record_main,
    merge_coverage_total,
)

COVERAGE_XML = (
    '<?xml version="1.0" ?>\n'
    '<coverage line-rate="0.842" version="7.0" timestamp="0">\n'
    "  <packages/>\n</coverage>\n"
)


def _write_xml(root: Path, body: str = COVERAGE_XML) -> Path:
    p = root / "coverage.xml"
    p.write_text(body, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# merge — preserves other top-level keys
# --------------------------------------------------------------------------- #
class TestMerge:
    def test_sets_coverage_block(self):
        out = merge_coverage_total({}, 84.2, measured_at="2026-07-04T00:00:00Z")
        assert out["coverage"]["total"] == 84.2
        assert out["coverage"]["measured_tier"] == "repo"
        assert out["coverage"]["measured_at"] == "2026-07-04T00:00:00Z"

    def test_preserves_iterate_latest(self):
        existing = {"iterate_latest": {"run_id": "keepme", "unit": {"passed": 5}}}
        out = merge_coverage_total(existing, 90.0)
        assert out["iterate_latest"] == {"run_id": "keepme", "unit": {"passed": 5}}
        assert out["coverage"]["total"] == 90.0

    def test_no_measured_at_key_when_omitted(self):
        out = merge_coverage_total({}, 84.2)
        assert "measured_at" not in out["coverage"]


# --------------------------------------------------------------------------- #
# main — write + refuse
# --------------------------------------------------------------------------- #
class TestMainCLI:
    def test_writes_total_preserving_iterate_latest(self, tmp_path):
        results = tmp_path / "shipwright_test_results.json"
        results.write_text(
            json.dumps({"iterate_latest": {"run_id": "r1"}}, indent=2) + "\n",
            encoding="utf-8")
        _write_xml(tmp_path)
        rc = record_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
        ])
        assert rc == 0
        data = json.loads(results.read_text(encoding="utf-8"))
        assert data["coverage"]["total"] == 84.2
        assert data["iterate_latest"] == {"run_id": "r1"}  # untouched

    def test_creates_file_when_absent(self, tmp_path):
        _write_xml(tmp_path)
        rc = record_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
        ])
        assert rc == 0
        data = json.loads(
            (tmp_path / "shipwright_test_results.json").read_text(encoding="utf-8"))
        assert data["coverage"]["total"] == 84.2

    def test_refuses_missing_xml_writes_nothing(self, tmp_path):
        rc = record_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "nope.xml"),
        ])
        assert rc == 1
        assert not (tmp_path / "shipwright_test_results.json").exists()

    def test_refuses_unparseable_xml(self, tmp_path):
        (tmp_path / "coverage.xml").write_text("<coverage/>", encoding="utf-8")
        rc = record_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
        ])
        assert rc == 1  # no line-rate attr -> refuse


# --------------------------------------------------------------------------- #
# THE ROUND-TRIP — recorder writes total, W4 reads it (Boundary Probe)
# --------------------------------------------------------------------------- #
class TestW4RoundTrip:
    def _w4(self, project_root: Path):
        from tools.verifiers.test_compliance import (
            check_w4_coverage_meets_threshold,
        )
        return check_w4_coverage_meets_threshold(project_root)

    @staticmethod
    def _status():
        from lib.phase_quality import STATUS_FAIL, STATUS_PASS, STATUS_SKIP
        return STATUS_PASS, STATUS_FAIL, STATUS_SKIP

    def test_total_plus_calibrated_min_is_pass(self, tmp_path):
        pass_, _fail, _skip = self._status()
        _write_xml(tmp_path)  # 84.2%
        record_main(["--project-root", str(tmp_path),
                     "--coverage-xml", str(tmp_path / "coverage.xml")])
        # Conservative anti-ratchet floor BELOW the measured total.
        (tmp_path / "shipwright_test_config.json").write_text(
            json.dumps({"coverage": {"min": 70}}, indent=2) + "\n", encoding="utf-8")
        finding = self._w4(tmp_path)
        assert finding["status"] == pass_, finding
        assert "84.2%" in finding["evidence"]

    def test_min_above_total_is_fail(self, tmp_path):
        _pass, fail, _skip = self._status()
        _write_xml(tmp_path)  # 84.2%
        record_main(["--project-root", str(tmp_path),
                     "--coverage-xml", str(tmp_path / "coverage.xml")])
        (tmp_path / "shipwright_test_config.json").write_text(
            json.dumps({"coverage": {"min": 90}}, indent=2) + "\n", encoding="utf-8")
        finding = self._w4(tmp_path)
        assert finding["status"] == fail, finding

    def test_no_total_is_skip(self, tmp_path):
        _pass, _fail, skip = self._status()
        # Before the recorder runs: no coverage.total -> W4 SKIP (the dormant
        # state Phase 2 lifts).
        (tmp_path / "shipwright_test_results.json").write_text(
            json.dumps({"iterate_latest": {"run_id": "r"}}) + "\n", encoding="utf-8")
        finding = self._w4(tmp_path)
        assert finding["status"] == skip, finding
