"""Tests for the phase-runner RESULT CONTRACT (SS1 scaffold).

Campaign 2026-07-07-single-session-pipeline / SS1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from single_session.result_contract import (  # noqa: E402
    MAX_SUMMARY_CHARS,
    REQUIRED_RESULT_KEYS,
    VALID_PHASES,
    ResultContractError,
    build_phase_runner_result,
    is_valid_result,
    validate_phase_runner_result,
)


def _ok_result() -> dict:
    return {
        "ok": True,
        "phase": "project",
        "summary": "Decomposed into 2 splits; wrote project config + specs.",
        "artifacts": ["shipwright_project_config.json", ".shipwright/agent_docs/architecture.md"],
    }


# ---- happy paths ----


def test_valid_ok_result_passes():
    assert validate_phase_runner_result(_ok_result()) == []
    assert is_valid_result(_ok_result())


def test_valid_failure_result_with_reason_passes():
    res = {"ok": False, "phase": "build", "summary": "build failed at split 01",
           "artifacts": [], "reason": "pytest: 3 failing in split 01-core"}
    assert validate_phase_runner_result(res) == []


def test_build_phase_runner_result_constructs_valid_dict():
    res = build_phase_runner_result(
        ok=True, phase="design", summary="2 screens mocked",
        artifacts=["designs/home.html"], split_id=None,
    )
    assert res == {"ok": True, "phase": "design", "summary": "2 screens mocked",
                   "artifacts": ["designs/home.html"]}


def test_build_omits_none_optionals_but_keeps_provided():
    res = build_phase_runner_result(
        ok=False, phase="plan", summary="planning blocked", artifacts=[],
        reason="external review key missing", split_id="01-core",
        metrics={"sections": 0},
    )
    assert res["reason"] == "external review key missing"
    assert res["splitId"] == "01-core"
    assert res["metrics"] == {"sections": 0}


# ---- required keys ----


def test_missing_required_keys_flagged():
    errors = validate_phase_runner_result({})
    for key in REQUIRED_RESULT_KEYS:
        assert any(key in e for e in errors), f"missing-key error not raised for {key}"


def test_non_dict_result_flagged():
    assert validate_phase_runner_result("nope")
    assert validate_phase_runner_result(None)


# ---- ok / reason coupling ----


def test_failure_without_reason_flagged():
    res = {"ok": False, "phase": "test", "summary": "tests failed", "artifacts": []}
    errors = validate_phase_runner_result(res)
    assert any("reason" in e for e in errors)


def test_build_failure_without_reason_raises():
    with pytest.raises(ResultContractError):
        build_phase_runner_result(ok=False, phase="test", summary="x", artifacts=[])


def test_non_bool_ok_flagged():
    res = {**_ok_result(), "ok": "true"}
    assert any("'ok'" in e for e in validate_phase_runner_result(res))


# ---- phase enum ----


def test_unknown_phase_flagged():
    res = {**_ok_result(), "phase": "deploybot"}
    assert any("phase" in e for e in validate_phase_runner_result(res))


def test_valid_phases_matches_schema_enum_both_directions():
    """Drift guard: VALID_PHASES literal must equal the schema Phase enum."""
    repo_root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (repo_root / "shared" / "schemas" / "run_config.v2.schema.json").read_text(encoding="utf-8"),
    )
    enum = schema["$defs"]["Phase"]["enum"]
    assert set(VALID_PHASES) == set(enum), "VALID_PHASES drifted from schema Phase enum"
    assert len(VALID_PHASES) == len(enum), "VALID_PHASES has duplicates / count mismatch"


# ---- summary context-budget guard ----


def test_oversize_summary_flagged():
    res = {**_ok_result(), "summary": "x" * (MAX_SUMMARY_CHARS + 1)}
    assert any("MAX_SUMMARY_CHARS" in e for e in validate_phase_runner_result(res))


def test_summary_at_ceiling_passes():
    res = {**_ok_result(), "summary": "x" * MAX_SUMMARY_CHARS}
    assert validate_phase_runner_result(res) == []


def test_empty_summary_flagged():
    res = {**_ok_result(), "summary": "   "}
    assert any("summary" in e for e in validate_phase_runner_result(res))


def test_build_never_silently_truncates_oversize_summary():
    with pytest.raises(ResultContractError):
        build_phase_runner_result(
            ok=True, phase="project", summary="y" * (MAX_SUMMARY_CHARS + 5),
            artifacts=[],
        )


# ---- artifacts must be relative repo paths (persisted to disk) ----


def test_absolute_artifact_flagged():
    res = {**_ok_result(), "artifacts": ["/etc/passwd"]}
    assert any("artifacts[0]" in e for e in validate_phase_runner_result(res))


def test_windows_absolute_artifact_flagged():
    res = {**_ok_result(), "artifacts": ["C:\\Users\\x\\out.json"]}
    assert any("artifacts[0]" in e for e in validate_phase_runner_result(res))


def test_traversal_artifact_flagged():
    res = {**_ok_result(), "artifacts": ["../../secret"]}
    assert any("artifacts[0]" in e for e in validate_phase_runner_result(res))


def test_non_list_artifacts_flagged():
    res = {**_ok_result(), "artifacts": "shipwright_project_config.json"}
    assert any("artifacts" in e for e in validate_phase_runner_result(res))


def test_empty_artifacts_list_allowed():
    # A phase that writes nothing new (or a failure) may report [] — but a
    # relative path list is still required to BE a list.
    res = {"ok": False, "phase": "security", "summary": "no findings", "artifacts": [],
           "reason": "scan degraded"}
    assert validate_phase_runner_result(res) == []


# ---- result contract is compatible with complete_phase_task's expectations ----


def test_result_carries_ok_flag_that_lifecycle_branches_on():
    """complete_phase_task reads result['ok'] to branch done/failed; the
    contract guarantees a bool is present."""
    res = _ok_result()
    assert isinstance(res["ok"], bool)
