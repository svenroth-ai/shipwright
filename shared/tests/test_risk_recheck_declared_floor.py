"""F11 gate: a recorded risk re-check may not sit below the unit's declared tier.

`check_risk_recheck_recorded` already refuses an F5c complexity below Step 3.4's
`effective_complexity`. A declared tier (the operator's brief) adds the other
side: a `risk_recheck.json` whose `effective_complexity` is below its own
`declared_complexity` is an inconsistent record (hand-edited, or produced by a
re-check run without the spec) and fails (FR-01.11/AC52).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tools.verifiers.risk_recheck_recording import (  # noqa: E402
    RECHECK_SCHEMA_VERSION,
    check_risk_recheck_recorded,
    recheck_record_relpath,
)

RUN_ID = "iterate-2026-11-16-declared-floor"


def _record(root: Path, block: dict) -> None:
    path = root / recheck_record_relpath(RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": RECHECK_SCHEMA_VERSION, "run_id": RUN_ID, "risk_recheck": block,
    }), encoding="utf-8")


def _f5c(root: Path, complexity: str) -> None:
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN_ID}.json").write_text(json.dumps({
        "run_id": RUN_ID, "date": "2026-11-16T00:00:00Z", "type": "bug",
        "complexity": complexity, "branch": f"iterate/{RUN_ID}", "tests_passed": True,
    }), encoding="utf-8")


def test_effective_below_declared_fails(tmp_path):
    _record(tmp_path, {"declared_complexity": "medium", "effective_complexity": "small"})
    _f5c(tmp_path, "medium")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "declares complexity='medium'" in result.detail


def test_unknown_declared_tier_fails(tmp_path):
    _record(tmp_path, {"declared_complexity": "huge", "effective_complexity": "medium"})
    _f5c(tmp_path, "medium")
    assert check_risk_recheck_recorded(tmp_path, RUN_ID).ok is False


def test_f5c_below_declared_floor_fails_through_effective(tmp_path):
    _record(tmp_path, {"declared_complexity": "medium", "effective_complexity": "medium"})
    _f5c(tmp_path, "small")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "small" in result.detail


def test_declared_medium_recorded_medium_passes(tmp_path):
    _record(tmp_path, {"declared_complexity": "medium", "effective_complexity": "medium"})
    _f5c(tmp_path, "medium")
    assert check_risk_recheck_recorded(tmp_path, RUN_ID).ok is True


def test_declared_small_raised_to_medium_passes(tmp_path):
    _record(tmp_path, {"declared_complexity": "small", "effective_complexity": "medium"})
    _f5c(tmp_path, "large")
    assert check_risk_recheck_recorded(tmp_path, RUN_ID).ok is True


def test_null_or_absent_declared_keeps_todays_behaviour(tmp_path):
    _f5c(tmp_path, "small")
    for block in ({"declared_complexity": None, "effective_complexity": "small"},
                  {"effective_complexity": "small"}):
        _record(tmp_path, block)
        assert check_risk_recheck_recorded(tmp_path, RUN_ID).ok is True
