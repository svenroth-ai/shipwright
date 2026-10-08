"""U3: the Test Completeness Ledger at trivial is a RECORDED row, not a SKIP.

A trivial run closes the ledger with ``{"status": "n/a", "reason_code":
"trivial-auto"}``; with no block at all it fails like any other complexity. The
default code is refused above trivial, where ``n/a`` keeps needing a
justification. Also pins that the check moved out of ``iterate_checks.py``
without changing its public import path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from tools.verifiers import _ledger_completeness, iterate_checks  # noqa: E402
from tools.verifiers.common import Severity  # noqa: E402

RUN = "iterate-2026-10-08-ledger"
TRIVIAL_ROW = {"status": "n/a", "reason_code": "trivial-auto"}
COMPLETE = {
    "status": "complete",
    "behaviors": [{"behavior": "x", "disposition": "tested", "evidence": "t::x PASSED"}],
    "counts": {"untested_testable": 0},
}


def _entry(root: Path, complexity: str, block: dict | None) -> None:
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    entry = {"run_id": RUN, "type": "change", "complexity": complexity,
             "branch": "iterate/x", "tests_passed": True,
             "date": "2026-10-08T00:00:00+00:00"}
    if block is not None:
        entry["test_completeness"] = block
    (d / f"{RUN}.json").write_text(json.dumps(entry), encoding="utf-8")


def _check(root: Path):
    return _ledger_completeness.check_test_completeness_ledger(root, RUN)


@pytest.mark.covers("FR-01.11")
def test_trivial_default_row_passes_and_is_not_a_skip(tmp_path):
    _entry(tmp_path, "trivial", TRIVIAL_ROW)

    result = _check(tmp_path)

    assert result.ok, result.detail
    assert result.severity != Severity.SKIPPED.value
    assert "trivial-auto" in result.detail


@pytest.mark.covers("FR-01.11")
def test_trivial_with_no_block_fails_and_names_the_row(tmp_path):
    _entry(tmp_path, "trivial", None)

    result = _check(tmp_path)

    assert result.is_failure
    assert '"reason_code": "trivial-auto"' in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("block", [
    {"status": "n/a", "justification": "markdown-only edit; no executable behavior changed"},
    COMPLETE,
])
def test_trivial_may_still_justify_or_enumerate(tmp_path, block):
    _entry(tmp_path, "trivial", block)

    assert _check(tmp_path).ok


@pytest.mark.covers("FR-01.11")
def test_the_default_row_is_refused_at_small(tmp_path):
    _entry(tmp_path, "small", {**TRIVIAL_ROW, "justification": "docs only"})

    result = _check(tmp_path)

    assert result.is_failure and "TRIVIAL iterate only" in result.detail


@pytest.mark.covers("FR-01.11")
def test_n_a_at_medium_is_still_refused_even_with_the_code(tmp_path):
    _entry(tmp_path, "medium", TRIVIAL_ROW)

    assert "not allowed at medium" in _check(tmp_path).detail


@pytest.mark.covers("FR-01.11")
def test_any_other_ledger_code_is_refused(tmp_path):
    _entry(tmp_path, "trivial", {"status": "n/a", "reason_code": "missing-keys"})

    result = _check(tmp_path)

    assert result.is_failure and "only code an n/a" in result.detail


@pytest.mark.covers("FR-01.11")
def test_trivial_n_a_with_neither_code_nor_justification_fails(tmp_path):
    _entry(tmp_path, "trivial", {"status": "n/a"})

    result = _check(tmp_path)

    assert result.is_failure and "trivial-auto" in result.detail


@pytest.mark.covers("FR-01.11")
def test_trivial_is_not_satisfied_by_another_runs_shared_block(tmp_path):
    """Moved here from test_iterate_latest_attribution.py, where it pinned the old
    trivial SKIP: another run's ledger is not this trivial run's row."""
    _entry(tmp_path, "trivial", None)
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({"iterate_latest": {
        "run_id": "iterate-2026-10-07-other", "test_completeness": COMPLETE}}), encoding="utf-8")

    result = _check(tmp_path)

    assert result.is_failure
    assert "iterate-2026-10-07-other" in result.detail and "trivial-auto" in result.detail


@pytest.mark.covers("FR-01.11")
def test_iterate_checks_still_exports_the_moved_names():
    """Historical import path kept: tests and the F11 wrapper import from iterate_checks."""
    assert iterate_checks.check_test_completeness_ledger is _ledger_completeness.check_test_completeness_ledger
    assert iterate_checks.UNTESTABLE_REASON_CODES is _ledger_completeness.UNTESTABLE_REASON_CODES
    assert callable(iterate_checks._no_entry_detail) and callable(iterate_checks._wrong_shape_detail)
