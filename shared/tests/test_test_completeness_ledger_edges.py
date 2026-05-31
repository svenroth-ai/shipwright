"""Asymptote probe — type-robustness edges of check_test_completeness_ledger.

iterate-2026-05-30-test-completeness-gate, follow-up.

The main suite pins the semantic branches (escape-hatch disposition, bad
reason_code, untested>0, n/a rules, enumeration gap). This file closes the
last *testable* defensive branches the coverage stopping rule surfaced:
malformed SHAPES that are valid JSON but the wrong type — a list where an
object is expected. Each must fail closed (ERROR), never crash. New file so
the ADR-093 verifier-test ceiling is not ratcheted further.
"""

import json
from pathlib import Path

from tools.verifiers.iterate_checks import check_test_completeness_ledger


def _seed(proj: Path, complexity: str = "medium") -> None:
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": "r1", "complexity": complexity, "type": "feature"},
        ],
    }), encoding="utf-8")


def _write(proj: Path, iterate_latest) -> None:
    (proj / "shipwright_test_results.json").write_text(
        json.dumps({"iterate_latest": iterate_latest}), encoding="utf-8"
    )


def test_iterate_latest_is_a_list_fails_closed(tmp_path):
    """`iterate_latest: []` (valid JSON, wrong type) → ERROR, no crash."""
    proj = tmp_path / "webui"
    _seed(proj)
    _write(proj, [])
    result = check_test_completeness_ledger(proj, "r1")
    assert result.ok is False
    assert "missing" in result.detail.lower()


def test_test_completeness_block_is_a_list_fails_closed(tmp_path):
    """`test_completeness: []` → treated as missing block → ERROR."""
    proj = tmp_path / "webui"
    _seed(proj)
    _write(proj, {"test_completeness": []})
    result = check_test_completeness_ledger(proj, "r1")
    assert result.ok is False
    assert "test_completeness" in result.detail


def test_behavior_entry_not_an_object_fails_closed(tmp_path):
    """A behaviors row that is a bare string (not an object) → ERROR."""
    proj = tmp_path / "webui"
    _seed(proj)
    _write(proj, {"test_completeness": {
        "status": "complete",
        "behaviors": ["I am not an object"],
        "counts": {"untested_testable": 0},
    }})
    result = check_test_completeness_ledger(proj, "r1")
    assert result.ok is False
    assert "not an object" in result.detail.lower()


def test_counts_absent_is_rejected(tmp_path):
    """status=complete, behaviors valid, but `counts` omitted entirely →
    untested_testable is unknowable → ERROR (no silent pass)."""
    proj = tmp_path / "webui"
    _seed(proj)
    _write(proj, {"test_completeness": {
        "status": "complete",
        "behaviors": [
            {"behavior": "x", "disposition": "tested", "evidence": "t::x PASSED"},
        ],
    }})
    result = check_test_completeness_ledger(proj, "r1")
    assert result.ok is False
    assert "untested" in result.detail.lower()
