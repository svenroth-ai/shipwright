"""Repo-level invariant: the W4 coverage gate is LIT GREEN on the committed files.

Diff-coverage roadmap Phase 2 (``iterate-2026-07-04-diff-coverage-rollout-
combine``) populates the tracked ``shipwright_test_results.json.coverage.total``
(the combined repo-wide line-rate) and a calibrated
``shipwright_test_config.json.coverage.min`` baseline. Together they move W4 from
its dormant SKIP to PASS. This test pins that outcome on the *real* repo files so
a regression (total dropped below min, config deleted, or min fudged up to/above
the measured total) is caught.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers.test_compliance import (  # noqa: E402
    check_w4_coverage_meets_threshold,
)

_CONFIG = _REPO_ROOT / "shipwright_test_config.json"
_RESULTS = _REPO_ROOT / "shipwright_test_results.json"


def _coverage_min() -> float:
    data = json.loads(_CONFIG.read_text(encoding="utf-8"))
    raw = data["coverage"]["min"]
    return raw * 100 if raw <= 1.0 else float(raw)


def _coverage_total() -> float:
    data = json.loads(_RESULTS.read_text(encoding="utf-8"))
    raw = data["coverage"]["total"]
    return raw * 100 if raw <= 1.0 else float(raw)


def test_config_has_numeric_coverage_min():
    assert _CONFIG.exists(), "shipwright_test_config.json must exist (Phase 2)"
    assert isinstance(_coverage_min(), float)


def test_results_has_numeric_coverage_total():
    data = json.loads(_RESULTS.read_text(encoding="utf-8"))
    assert isinstance(data.get("coverage", {}).get("total"), (int, float)), (
        "shipwright_test_results.json must carry a top-level coverage.total")
    # The repo-wide measurement — must be a real fraction, not a placeholder.
    assert 0.0 < _coverage_total() <= 100.0


def test_w4_is_green_on_committed_files():
    finding = check_w4_coverage_meets_threshold(_REPO_ROOT)
    assert finding["status"] == pq.STATUS_PASS, finding


def test_baseline_min_sits_below_measured_total():
    # Anti-ratchet honesty: the calibrated floor is BELOW the measured total
    # (headroom), never fudged up to/above it to force green.
    assert _coverage_min() < _coverage_total()


def test_gitignore_covers_coverage_transients():
    # The per-tier data files + the combine data dir are transient build
    # artifacts (never tracked). `.coverage*` covers the bare `.coverage` AND
    # `.coverage.<plugin>`; `.cov-data/` is the combine staging dir.
    gi = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".coverage*" in gi
    assert ".cov-data/" in gi
