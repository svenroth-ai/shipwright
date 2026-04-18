"""Test-phase workflow compliance checks (Phase-Quality PR 2).

Implements W4 — ``shipwright_test_results.json.coverage.total`` must
meet the project's configured threshold. Threshold comes from
``shipwright_test_config.json.coverage.min`` (0..100); default 70.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    make_finding,
)


W4_NAME = "W4 coverage meets threshold"
W4_REMEDIATION = (
    "Re-run the test phase; add tests until coverage.total >= threshold "
    "(configured in shipwright_test_config.json.coverage.min)."
)
_DEFAULT_COVERAGE_MIN = 70


def _load_threshold(project_root: Path) -> int:
    cfg = project_root / "shipwright_test_config.json"
    if not cfg.exists():
        return _DEFAULT_COVERAGE_MIN
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_COVERAGE_MIN
    raw = data.get("coverage", {}).get("min")
    if isinstance(raw, (int, float)):
        # Accept either 70 or 0.70
        if raw <= 1.0:
            return int(raw * 100)
        return int(raw)
    return _DEFAULT_COVERAGE_MIN


def _load_coverage(project_root: Path) -> tuple[float | None, str]:
    path = project_root / "shipwright_test_results.json"
    if not path.exists():
        return None, "shipwright_test_results.json missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"malformed test_results: {exc}"
    coverage = data.get("coverage") or {}
    total = coverage.get("total")
    if not isinstance(total, (int, float)):
        return None, "coverage.total missing or non-numeric"
    if total <= 1.0:
        total = total * 100
    return float(total), ""


def check_w4_coverage_meets_threshold(project_root: Path) -> dict[str, Any]:
    total, err = _load_coverage(project_root)
    threshold = _load_threshold(project_root)
    if total is None:
        return make_finding(
            "W4", STATUS_SKIP,
            f"{err} — coverage unverifiable",
            name=W4_NAME,
            remediation=W4_REMEDIATION,
        )
    if total + 0.001 < threshold:
        return make_finding(
            "W4", STATUS_FAIL,
            f"coverage.total={total:.1f}% < threshold={threshold}%",
            name=W4_NAME,
            remediation=W4_REMEDIATION,
        )
    return make_finding(
        "W4", STATUS_PASS,
        f"coverage.total={total:.1f}% >= threshold={threshold}%",
        name=W4_NAME,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [check_w4_coverage_meets_threshold(project_root)]


__all__ = ["check_w4_coverage_meets_threshold", "run"]
