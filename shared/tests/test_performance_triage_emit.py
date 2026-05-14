"""AC-2 producer test: Performance budget failures land in triage.jsonl.

Unit-tests the `_emit_failures_to_triage` helper in
``plugins/shipwright-test/scripts/lib/performance_check.py``.

The helper takes the synthesized `results` block that `main()` builds
(after `evaluate_gate`) and emits one triage item per failed sub-check:
Lighthouse score, Lighthouse LCP, bundle size. Skipped or passing
sub-checks emit nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_PERF_PATH = (
    _WORKTREE / "plugins" / "shipwright-test" / "scripts" / "lib"
    / "performance_check.py"
)
_spec = importlib.util.spec_from_file_location(
    "performance_check_for_test", _PERF_PATH,
)
assert _spec is not None and _spec.loader is not None
perf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(perf)

from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _lh_failed_score(score: int = 60, budget: int = 85) -> dict:
    """Lighthouse sub-block with a score below budget."""
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "score": score, "score_budget": budget, "score_passed": False,
        "lcp_ms": 1500, "lcp_budget_ms": 2500, "lcp_passed": True,
    }


def _lh_failed_lcp(lcp_ms: int = 4000, budget_ms: int = 2500) -> dict:
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "score": 92, "score_budget": 85, "score_passed": True,
        "lcp_ms": lcp_ms, "lcp_budget_ms": budget_ms, "lcp_passed": False,
    }


def _bundle_failed(total_kb_gz: float = 320.0, budget: int = 250) -> dict:
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "total_kb_gz": total_kb_gz, "budget_kb_gz": budget,
        "files_measured": 3, "files": ["app.js", "vendor.js", "main.css"],
        "passed": False,
    }


def _lh_skipped() -> dict:
    return {
        "ran": False, "skipped": True,
        "skip_reason": "no dev_url available",
        "score": None, "lcp_ms": None,
        "score_passed": True, "lcp_passed": True,
    }


def _bundle_skipped() -> dict:
    return {
        "ran": False, "skipped": True,
        "skip_reason": "no build artifacts found",
        "total_kb_gz": 0.0, "files_measured": 0, "files": [],
        "passed": True,
    }


def _lh_passed() -> dict:
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "score": 92, "score_budget": 85, "score_passed": True,
        "lcp_ms": 1500, "lcp_budget_ms": 2500, "lcp_passed": True,
    }


def _bundle_passed() -> dict:
    return {
        "ran": True, "skipped": False, "skip_reason": "",
        "total_kb_gz": 210.0, "budget_kb_gz": 250,
        "files_measured": 3, "files": [], "passed": True,
    }


# --- Failed sub-check → triage item ----------------------------------------

def test_score_failure_emits_one_item(project: Path) -> None:
    results = {"lighthouse": _lh_failed_score(), "bundle": _bundle_passed()}
    appended = perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/dashboard", run_id="r1",
    )
    assert appended == 1
    [item] = read_all_items(project)
    assert item["source"] == "performance"
    assert item["kind"] == "improvement"
    assert item["suggestedDomain"] == "engineering"
    assert "perf:score:" in item["dedupKey"]
    assert "/dashboard" in item["dedupKey"]


def test_lcp_failure_emits_one_item(project: Path) -> None:
    results = {"lighthouse": _lh_failed_lcp(), "bundle": _bundle_passed()}
    appended = perf._emit_failures_to_triage(
        project, results=results, gate="warn",
        dev_url="http://localhost:3000/", run_id="r1",
    )
    assert appended == 1
    [item] = read_all_items(project)
    assert item["source"] == "performance"
    assert "perf:lcp:" in item["dedupKey"]


def test_bundle_failure_emits_global_dedup_key(project: Path) -> None:
    results = {"lighthouse": _lh_passed(), "bundle": _bundle_failed()}
    appended = perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/", run_id="r1",
    )
    assert appended == 1
    [item] = read_all_items(project)
    assert item["dedupKey"] == "perf:bundle:global"


def test_severity_high_when_over_10_percent(project: Path) -> None:
    """LCP 4000ms vs budget 2500ms → 60% over → high."""
    results = {
        "lighthouse": _lh_failed_lcp(lcp_ms=4000, budget_ms=2500),
        "bundle": _bundle_passed(),
    }
    perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/", run_id="r1",
    )
    [item] = read_all_items(project)
    assert item["severity"] == "high"
    assert item["suggestedPriority"] == "P1"


def test_severity_medium_when_under_10_percent(project: Path) -> None:
    """LCP 2700ms vs budget 2500ms → 8% over → medium."""
    results = {
        "lighthouse": _lh_failed_lcp(lcp_ms=2700, budget_ms=2500),
        "bundle": _bundle_passed(),
    }
    perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/", run_id="r1",
    )
    [item] = read_all_items(project)
    assert item["severity"] == "medium"
    assert item["suggestedPriority"] == "P2"


def test_skipped_sub_checks_emit_nothing(project: Path) -> None:
    results = {"lighthouse": _lh_skipped(), "bundle": _bundle_skipped()}
    appended = perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="", run_id="r1",
    )
    assert appended == 0
    assert read_all_items(project) == []


def test_all_passed_emits_nothing(project: Path) -> None:
    results = {"lighthouse": _lh_passed(), "bundle": _bundle_passed()}
    appended = perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/", run_id="r1",
    )
    assert appended == 0
    assert read_all_items(project) == []


def test_two_failures_emit_two_items(project: Path) -> None:
    """Score+LCP both fail → two items (one per metric)."""
    lh = _lh_failed_score()
    lh["lcp_ms"] = 4000
    lh["lcp_budget_ms"] = 2500
    lh["lcp_passed"] = False
    results = {"lighthouse": lh, "bundle": _bundle_failed()}
    appended = perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/dashboard", run_id="r1",
    )
    assert appended == 3
    keys = {it["dedupKey"] for it in read_all_items(project)}
    assert any("perf:score:" in k for k in keys)
    assert any("perf:lcp:" in k for k in keys)
    assert "perf:bundle:global" in keys


def test_same_failure_dedups_within_window(project: Path) -> None:
    results = {"lighthouse": _lh_failed_score(), "bundle": _bundle_passed()}
    perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/dashboard", run_id="r1",
    )
    appended2 = perf._emit_failures_to_triage(
        project, results=results, gate="block",
        dev_url="http://localhost:3000/dashboard", run_id="r1",
    )
    assert appended2 == 0
    assert len(read_all_items(project)) == 1
