"""Issue #1035: a one-reviewer pass is recorded as ``completed`` PLUS a ``partial`` marker.

The recorder reads the envelope itself, so no caller has to remember a flag.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, payload, run_tool  # noqa: E402

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.review_payloads import CANONICAL_PAYLOAD_BASENAMES  # noqa: E402

_GLM_OK = {
    "status": "success",
    "feedback": "- **Category:** Risk\n- **Severity:** Medium\n- **Finding:** x.\n\nSHIPWRIGHT_VERDICT: approve\n",
}
_GPT_OK = {
    "status": "success",
    "feedback": "- **Category:** Risk\n- **Severity:** Low\n- **Finding:** y.\n\nSHIPWRIGHT_VERDICT: approve\n",
}
_GPT_FAILED = {"status": "error", "via": "codex", "reason": "codex exec exited 1: usage limit"}


def _envelope(gpt: dict, **extra) -> str:
    return json.dumps({
        "review_schema": 2, "success": True, "provider": "codex", "reviewed": True,
        "reviews_succeeded": 2 if gpt["status"] == "success" else 1, "reviews_expected": 2,
        "reviews": {"glm": _GLM_OK, "openai": gpt}, **extra,
    })


def _marker(project) -> dict:
    path = project / ".shipwright" / "planning" / "iterate" / RUN_ID / "external_review_state.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _record(project, tmp_path, body: str) -> int:
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--from", "external-review-json", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, CANONICAL_PAYLOAD_BASENAMES["plan"], body),
    )
    assert code == 0, output
    return code


@pytest.mark.covers("FR-01.03/AC23")
def test_one_reviewer_pass_is_marked_partial(tmp_path):
    project = make_project(tmp_path)
    body = _envelope(_GPT_FAILED, partially_degraded=True, partially_degraded_legs=["openai"],
                     missing_legs=["openai"], verdicts={"glm": "approve", "openai": "unavailable"})
    _record(project, tmp_path, body)
    marker = _marker(project)
    assert marker["status"] == "completed"
    assert marker["partial"] is True
    assert marker["missing_legs"] == ["openai"]


_PARTIAL_BODY = _envelope(
    _GPT_FAILED, partially_degraded=True, partially_degraded_legs=["openai"],
    missing_legs=["openai"], verdicts={"glm": "approve", "openai": "unavailable"},
)


@pytest.mark.covers("FR-01.03/AC23")
def test_repair_markers_keeps_the_partial_marker(tmp_path):
    project = make_project(tmp_path)
    _record(project, tmp_path, _PARTIAL_BODY)
    planning = project / ".shipwright" / "planning" / "iterate"
    (planning / RUN_ID / "external_review_state.json").unlink()

    code, output = run_tool(project, "repair-markers", "--review-type", "plan", "--marker-status", "completed")

    assert code == 0, output
    marker = _marker(project)
    assert marker["partial"] is True and marker["missing_legs"] == ["openai"]


@pytest.mark.covers("FR-01.03/AC23")
@pytest.mark.parametrize("legs", [5, "openai", {"a": 1}])
def test_malformed_missing_legs_never_break_the_recorder(tmp_path, legs):
    project = make_project(tmp_path)
    body = _envelope(_GPT_FAILED, partially_degraded=True, missing_legs=legs,
                     verdicts={"glm": "approve", "openai": "unavailable"})
    _record(project, tmp_path, body)
    marker = _marker(project)
    assert marker["status"] == "completed"
    assert marker["partial"] is True and marker["missing_legs"] == []


@pytest.mark.covers("FR-01.03/AC23")
def test_full_pass_marker_keeps_its_shape(tmp_path):
    project = make_project(tmp_path)
    _record(project, tmp_path, _envelope(_GPT_OK, missing_legs=[]))
    marker = _marker(project)
    assert "partial" not in marker and "missing_legs" not in marker
