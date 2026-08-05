"""Unit tests for the Step 3.4 recording-integrity F11 gate.

`check_risk_recheck_recorded` compares Step 3.4's persisted
`risk_recheck.json` (effective_complexity) against the F5c-recorded
complexity for the same run and FAILs when the recorded tier is outranked.

Malformed-artifact validation and path-safety (symlink escapes, unsafe
run_id) live in `test_risk_recheck_recording_malformed_artifact.py` — split
out to keep this file under the 300-line bloat guideline. Composition with
the real `diff_risk_recheck.py` CLI + a real F5c entry lives in
`integration-tests/test_risk_recheck_recording_integration.py`.
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
    _COMPLEXITY_ORDER,
    _rank,
    check_risk_recheck_recorded,
    recheck_record_relpath,
)

RUN_ID = "iterate-2026-08-05-example"


def _write_recheck(project_root: Path, path_run_id: str, **overrides) -> Path:
    """Write the artifact at `path_run_id`'s location. `overrides` may include
    `run_id` to make the ENVELOPE's run_id diverge from the file's location."""
    path = project_root / recheck_record_relpath(path_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": RECHECK_SCHEMA_VERSION,
        "run_id": path_run_id,
        "risk_recheck": {"effective_complexity": "medium"},
    }
    body.update(overrides)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _write_f5c_entry(project_root: Path, run_id: str, complexity: str) -> Path:
    entries_dir = project_root / ".shipwright" / "agent_docs" / "iterates"
    entries_dir.mkdir(parents=True, exist_ok=True)
    path = entries_dir / f"{run_id}.json"
    path.write_text(json.dumps({
        "run_id": run_id,
        "date": "2026-08-05T00:00:00Z",
        "type": "change",
        "complexity": complexity,
        "branch": f"iterate/{run_id}",
        "tests_passed": True,
    }), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Absence — the campaign-only SKIP path
# ---------------------------------------------------------------------------


def test_skip_when_artifact_absent(tmp_path: Path):
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is True
    assert result.is_skipped
    assert "no Step 3.4 risk re-check artifact found" in result.detail


def test_skip_message_does_not_claim_a_specific_cause(tmp_path: Path):
    """Absence is ambiguous between 'standalone iterate' and 'a campaign run
    whose write_recheck_record() call itself failed' (Stage-3 doubt review) —
    the message must not assert either as the reason."""
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert "standalone" not in result.detail
    assert "predates" not in result.detail


# ---------------------------------------------------------------------------
# Pass — F5c meets or exceeds the recorded floor
# ---------------------------------------------------------------------------


def test_pass_when_f5c_matches_effective_complexity(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID)
    _write_f5c_entry(tmp_path, RUN_ID, "medium")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is True
    assert not result.is_skipped


def test_pass_when_f5c_exceeds_effective_complexity(tmp_path: Path):
    """Escalating BEYOND the floor (e.g. mid-flight) must not be penalized."""
    _write_recheck(tmp_path, RUN_ID, risk_recheck={"effective_complexity": "small"})
    _write_f5c_entry(tmp_path, RUN_ID, "large")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is True


# ---------------------------------------------------------------------------
# Fail — the recording-integrity violation this gate exists to catch
# ---------------------------------------------------------------------------


def test_fail_when_f5c_underrecords(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID)  # effective_complexity=medium
    _write_f5c_entry(tmp_path, RUN_ID, "small")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert not result.is_skipped
    assert "medium" in result.detail
    assert "small" in result.detail


def test_fail_when_f5c_entry_missing(tmp_path: Path):
    """A runner cannot dodge the gate by simply omitting F5c."""
    _write_recheck(tmp_path, RUN_ID)
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "F5c" in result.detail


def test_fail_when_f5c_complexity_not_a_valid_value(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID)
    _write_f5c_entry(tmp_path, RUN_ID, "enormous")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "enormous" in result.detail


# ---------------------------------------------------------------------------
# _rank — no exception on bad input (deepseek finding)
# ---------------------------------------------------------------------------


def test_rank_returns_none_never_raises():
    for value in (None, 42, "", "enormous", [], {}):
        assert _rank(value) is None


def test_rank_orders_canonically():
    assert [_rank(lvl) for lvl in _COMPLEXITY_ORDER] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# Drift pin — the self-contained complexity-order copy (ADR-044)
# ---------------------------------------------------------------------------


def test_complexity_order_sync_with_plugin_vocabulary():
    """This shared verifier must never cross-plugin-import the iterate plugin's
    lib (ADR-044), so `_COMPLEXITY_ORDER` is a self-contained copy — this test
    is the drift protection. Only a TEST may cross-import both sides."""
    repo_root = Path(__file__).resolve().parents[2]
    plugin_lib = repo_root / "plugins" / "shipwright-iterate" / "scripts" / "lib"
    sys.path.insert(0, str(plugin_lib))
    from complexity_vocabulary import COMPLEXITY_ORDER

    assert list(_COMPLEXITY_ORDER) == COMPLEXITY_ORDER


def test_recheck_schema_version_sync():
    """`RECHECK_SCHEMA_VERSION` is duplicated on both sides of the same
    ADR-044 boundary (plugin-lib writer, shared-verifier reader) for the same
    reason `_COMPLEXITY_ORDER` is: a future bump landing in only one copy
    would go undetected until every subsequent F11 run failed on
    'unrecognized schema_version'."""
    repo_root = Path(__file__).resolve().parents[2]
    plugin_lib = repo_root / "plugins" / "shipwright-iterate" / "scripts" / "lib"
    sys.path.insert(0, str(plugin_lib))
    from risk_recheck_record import RECHECK_SCHEMA_VERSION as plugin_version

    assert RECHECK_SCHEMA_VERSION == plugin_version


# ---------------------------------------------------------------------------
# Registered in the real F11 check registry (external review finding: registry
# composition must be asserted, not merely conditional)
# ---------------------------------------------------------------------------


def test_registered_in_run_all_checks(tmp_path: Path):
    from tools.verifiers.iterate_checks import run_all_checks

    _write_recheck(tmp_path, RUN_ID)
    _write_f5c_entry(tmp_path, RUN_ID, "small")  # deliberately under-recorded

    results = run_all_checks(tmp_path, RUN_ID)
    matches = [r for r in results if r.name == "risk re-check recording integrity"]
    assert len(matches) == 1
    assert matches[0].ok is False
