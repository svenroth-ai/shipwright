"""A gateway envelope travels producer -> recorder -> marker (#547).

``test_external_review_gateway_cli.py`` proves ``external_review.py`` emits a
``model-1``/``model-2`` envelope and that ``write_markers`` accepts that roster.
This file closes the hop between them: the real ``record_review_pass.py`` CLI
reading such an envelope, which is where an unregistered roster used to be
refused. Also pins ``reviewed`` on the two envelopes ``finalize_review_output``
does not build.
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
sys.path.insert(0, str(_SHARED / "scripts" / "lib"))
sys.path.insert(0, str(_SHARED / "scripts" / "tools"))

from lib.review_payloads import CANONICAL_PAYLOAD_BASENAMES  # noqa: E402
from lib.review_record import record_path  # noqa: E402

GATEWAY_OUTPUT = json.dumps({
    "review_schema": 2, "success": True, "provider": "gateway", "reviewed": True,
    "reviews": {
        "model-1": {"status": "success", "answering_model": "real/one", "feedback":
                    "- **Category:** Risk\n- **Severity:** Medium\n- **Finding:** x.\n\n"
                    "SHIPWRIGHT_VERDICT: approve\n"},
        "model-2": {"status": "success", "answering_model": "real/two", "feedback":
                    "- Category: bug\n- Severity: high\n- Finding: y.\n\n"
                    "SHIPWRIGHT_VERDICT: revise\n"},
    },
})


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.mark.covers("FR-01.13/AC07")
def test_recorder_accepts_a_gateway_envelope_and_writes_a_schema_6_marker(project, tmp_path):
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--from", "external-review-json", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, CANONICAL_PAYLOAD_BASENAMES["plan"], GATEWAY_OUTPUT),
    )
    assert code == 0, output

    marker = json.loads(
        (project / ".shipwright" / "planning" / "iterate" / RUN_ID / "external_review_state.json")
        .read_text(encoding="utf-8"))
    assert marker["marker_schema"] == 6
    assert marker["verdicts"] == {"model-1": "approve", "model-2": "revise"}
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["plan"]["verdicts"] == marker["verdicts"]


@pytest.mark.covers("FR-01.13/AC07")
def test_recorder_still_rejects_a_mixed_roster(project, tmp_path):
    """model-1 next to glm is neither the gateway pair nor a current roster."""
    mixed = json.loads(GATEWAY_OUTPUT)
    mixed["reviews"]["glm"] = mixed["reviews"].pop("model-2")
    run_tool(project, "init")
    code, _ = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--from", "external-review-json", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, CANONICAL_PAYLOAD_BASENAMES["plan"], json.dumps(mixed)),
    )
    assert code != 0


@pytest.mark.covers("FR-01.13/AC07")
def test_empty_diff_and_failure_envelopes_say_nothing_was_reviewed(monkeypatch, tmp_path, capsys):
    from external_review_empty import empty_diff_envelope

    assert empty_diff_envelope("claude", {"driver": "claude"})["reviewed"] is False

    import external_review

    assert external_review._fail_envelope("boom", {"driver": "claude"}) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is False and out["reviewed"] is False


@pytest.mark.covers("FR-01.13/AC07")
def test_a_gateway_record_is_not_counted_as_driver_attested(tmp_path):
    """Operator-chosen models: a Codextender session must not read the driver gate as proof."""
    from tools.verifiers.review_driver_check import check_review_driver

    run = "iterate-2026-10-09-gateway-driver"
    d = tmp_path / ".shipwright" / "planning" / "iterate" / run
    d.mkdir(parents=True)
    (d / "external-code-review-raw.json").write_text(
        '{"provider": "gateway", "driver": "claude"}', encoding="utf-8")

    result = check_review_driver(tmp_path, run, environ={"CODEXTENDER_ACTIVE": "1"})

    assert result.ok is None  # skipped, never a pass and never a false block
