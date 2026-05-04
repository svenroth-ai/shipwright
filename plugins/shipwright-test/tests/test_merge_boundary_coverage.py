"""Tests for plugins/shipwright-test/scripts/tools/merge_boundary_coverage.py.

E spec HIGH-4: standalone helper for the two-step flow (run report →
merge into shipwright_test_results.json). The single-step alternative
is `boundary_coverage_report.py --merge-into <path>` (covered by
`test_boundary_coverage_report.py::TestMergeIntoFlag`).

This file covers:
- Round-trip: write a fixture report, merge, read back the merged file
- Idempotency: running the merge twice yields equal output
- Missing-input handling: returns non-zero exit, doesn't touch target
- Existing top-level keys preserved
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_TOOL_PATH = PLUGIN_ROOT / "scripts" / "tools" / "merge_boundary_coverage.py"
_spec = importlib.util.spec_from_file_location("merge_boundary_coverage", _TOOL_PATH)
mbc = importlib.util.module_from_spec(_spec)
sys.modules["merge_boundary_coverage"] = mbc
_spec.loader.exec_module(mbc)  # noqa: E402


FIXTURE_REPORT = {
    "summary": {
        "specs_scanned": 5,
        "specs_with_boundaries": 3,
        "total_boundaries": 7,
        "round_trip_tested": 4,
        "round_trip_unknown": 1,
        "drift_signals": 1,
    },
    "rows": [
        {
            "spec_path": "fixture/A.md",
            "boundaries": [
                {"producer": "p", "consumer": "c", "format": "JSON",
                 "round_trip_tested": True}
            ],
            "commits": ["abc1234"],
            "drift_signal": False,
            "drift_reason": "",
        }
    ],
}


def _write_input(tmp_path: Path) -> Path:
    p = tmp_path / "boundary-coverage-fixture.json"
    p.write_text(json.dumps(FIXTURE_REPORT, indent=2), encoding="utf-8")
    return p


def test_merge_round_trip_creates_key(tmp_path):
    """Run the merge; the target file gains the boundary_coverage_report key."""
    input_path = _write_input(tmp_path)
    target = tmp_path / "shipwright_test_results.json"

    rc = mbc.main(["--input", str(input_path), "--target", str(target)])
    assert rc == 0
    merged = json.loads(target.read_text(encoding="utf-8"))
    assert "boundary_coverage_report" in merged
    assert merged["boundary_coverage_report"]["summary"]["specs_scanned"] == 5
    assert (
        merged["boundary_coverage_report"]["rows"][0]["spec_path"]
        == "fixture/A.md"
    )


def test_merge_preserves_existing_top_level_keys(tmp_path):
    """Other keys in the target file are preserved across the merge."""
    input_path = _write_input(tmp_path)
    target = tmp_path / "shipwright_test_results.json"
    target.write_text(
        json.dumps(
            {
                "tests": {"unit": {"passed": 100, "total": 100}},
                "metadata": "preserved",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rc = mbc.main(["--input", str(input_path), "--target", str(target)])
    assert rc == 0
    merged = json.loads(target.read_text(encoding="utf-8"))
    assert merged["tests"]["unit"]["passed"] == 100
    assert merged["metadata"] == "preserved"
    assert "boundary_coverage_report" in merged


def test_merge_is_idempotent(tmp_path):
    """Running the merge twice produces identical content."""
    input_path = _write_input(tmp_path)
    target = tmp_path / "shipwright_test_results.json"

    rc1 = mbc.main(["--input", str(input_path), "--target", str(target)])
    assert rc1 == 0
    first = json.loads(target.read_text(encoding="utf-8"))

    rc2 = mbc.main(["--input", str(input_path), "--target", str(target)])
    assert rc2 == 0
    second = json.loads(target.read_text(encoding="utf-8"))

    assert first == second


def test_missing_input_returns_nonzero(tmp_path, capsys):
    """If the input file does not exist, exit non-zero and do not touch the target."""
    target = tmp_path / "shipwright_test_results.json"
    target.write_text(json.dumps({"a": 1}), encoding="utf-8")
    pre = target.read_bytes()

    rc = mbc.main([
        "--input", str(tmp_path / "does-not-exist.json"),
        "--target", str(target),
    ])
    assert rc != 0
    # Target untouched.
    assert target.read_bytes() == pre


def test_atomic_write_no_leftover_tmp_file(tmp_path):
    """After a successful merge, there's no .tmp residue in the target dir."""
    input_path = _write_input(tmp_path)
    target = tmp_path / "shipwright_test_results.json"

    rc = mbc.main(["--input", str(input_path), "--target", str(target)])
    assert rc == 0
    leftovers = list(target.parent.glob("*.tmp"))
    assert leftovers == [], f"Atomic write leaked tmp files: {leftovers!r}"
