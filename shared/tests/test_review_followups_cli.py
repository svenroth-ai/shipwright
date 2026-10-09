"""Follow-ups to U0 / U3 / U10 of the finalization-claims hardening, at the recorder CLI.

A bare ``--reason-code`` re-run must repair a marker with the default text (not a null
reason); ``make_entry`` takes ``reason_code`` itself; a Stage-1 REJECT has its own code;
a skipped marker-bound row can be corrected with ``--force`` without a marker, while
overwriting a ``completed`` one still needs it; the stderr capture that backs an
``unavailable`` row is masked when the row is recorded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402
from lib.review_companion import force_strands_marker  # noqa: E402
from lib.review_record import make_entry, new_record, upsert_review, write_record  # noqa: E402
from lib.review_unavailable import artifact_paths  # noqa: E402


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def _show(project: Path) -> dict:
    code, out = run_tool(project, "show")
    assert code == 0, out
    return json.loads(out)["reviews"]


@pytest.mark.covers("FR-01.11")
def test_make_entry_carries_reason_code_and_omits_it_when_absent():
    assert make_entry("doubt", "not_run", disposition="closed by rule", reason_code="user-opt-out")["reason_code"] == "user-opt-out"
    assert "reason_code" not in make_entry("doubt", "not_run", disposition="closed by rule")


@pytest.mark.covers("FR-01.11")
def test_make_entry_reason_code_outside_the_vocabulary_is_refused_at_write(tmp_path):
    record = upsert_review(new_record(RUN_ID), make_entry(
        "doubt", "not_run", disposition="closed by rule", reason_code="felt-fine"), force=True)
    with pytest.raises(Exception, match="felt-fine"):
        write_record(tmp_path, RUN_ID, record)


@pytest.mark.covers("FR-01.11")
def test_a_bare_reason_code_rerun_repairs_the_marker_with_the_default_reason(project):
    cmd = ("record", "--review-type", "external_code", "--status", "not_run",
           "--reason-code", "user-opt-out", "--marker-status", "skipped_user_opt_out")
    assert run_tool(project, *cmd)[0] == 0
    run_dir = project / ".shipwright" / "planning" / "iterate" / RUN_ID
    for marker in run_dir.glob("*review_state.json"):
        marker.unlink()  # the marker write "failed"; the record is already durable
    code, out = run_tool(project, *cmd)
    assert code == 0, out
    markers = list(run_dir.glob("*review_state.json"))
    assert markers, "the re-run did not repair the marker"
    assert json.loads(markers[0].read_text(encoding="utf-8"))["reason"] == "closed by reason_code user-opt-out"


@pytest.mark.covers("FR-01.11")
def test_a_stage_1_reject_is_recorded_under_its_own_reason_code(project):
    code, out = run_tool(project, "record", "--review-type", "spec", "--status", "not_run",
                         "--reason-code", "stage-1-rejected",
                         "--disposition", "Stage-1 REJECTED: AC2 is not implemented")
    assert code == 0, out
    assert _show(project)["spec"]["reason_code"] == "stage-1-rejected"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("first", ["missing-keys", "unavailable"])
def test_a_skipped_marker_bound_row_can_be_corrected_with_force_and_no_marker(project, first):
    if first == "unavailable":  # needs its capture: an unstamped one is refused at record time
        raw_rel, _ = artifact_paths(RUN_ID, "plan")
        (project / raw_rel).parent.mkdir(parents=True, exist_ok=True)
        (project / raw_rel).write_text("", encoding="utf-8")
        (project / artifact_paths(RUN_ID, "plan")[1]).write_text("uv: failed", encoding="utf-8")
    assert run_tool(project, "record", "--review-type", "plan", "--status", "not_run",
                    "--reason-code", first)[0] == 0
    code, out = run_tool(project, "record", "--review-type", "plan", "--status", "not_run",
                         "--reason-code", "config-disabled", "--force")
    assert code == 0, out
    assert _show(project)["plan"]["reason_code"] == "config-disabled"


@pytest.mark.covers("FR-01.11")
def test_force_over_a_completed_marker_bound_row_still_needs_the_marker(project):
    record = upsert_review(new_record(RUN_ID), make_entry(
        "plan", "completed", recorded_by="external-review-json", provider="openrouter"), force=True)
    write_record(project, RUN_ID, record)
    assert force_strands_marker(project, RUN_ID, "plan", "not_run") is True
    code, out = run_tool(project, "record", "--review-type", "plan", "--status", "not_run",
                         "--reason-code", "config-disabled", "--force")
    assert code == 2 and "requires --marker-status" in out, out


@pytest.mark.covers("FR-01.11")
def test_force_strands_marker_is_conservative_where_it_cannot_tell(tmp_path):
    assert force_strands_marker(tmp_path, RUN_ID, "doubt", "completed") is False  # no legacy marker exists
    assert force_strands_marker(tmp_path, RUN_ID, "plan", "completed") is True    # a completed result states itself
    assert force_strands_marker(tmp_path, RUN_ID, "plan", "not_run") is False     # no record yet: nothing to strand
    broken = tmp_path / ".shipwright" / "planning" / "iterate" / RUN_ID
    broken.mkdir(parents=True)
    (broken / "reviews.json").write_text("{not json", encoding="utf-8")
    assert force_strands_marker(tmp_path, RUN_ID, "plan", "not_run") is True      # unreadable: stay on the safe side


@pytest.mark.covers("FR-01.11")
def test_recording_unavailable_masks_urls_and_secrets_in_the_stderr_capture(project):
    raw_rel, err_rel = artifact_paths(RUN_ID, "external_code")
    (project / raw_rel).parent.mkdir(parents=True, exist_ok=True)
    (project / raw_rel).write_text(json.dumps({
        "review_schema": 2, "success": False, "error": "no provider answered", "mode": "code",
        "capture": {"run_id": RUN_ID, "at": "2026-10-09T00:00:00+00:00"}}), encoding="utf-8")
    (project / err_rel).write_text(
        "httpx.ConnectError: https://gw.internal.example/v1/chat?key=abc123\nAuthorization: Bearer abcdefgh12345678\n",
        encoding="utf-8")
    code, out = run_tool(project, "record", "--review-type", "external_code", "--status", "not_run",
                         "--reason-code", "unavailable")
    assert code == 0, out
    assert json.loads(out)["redacted"] == [err_rel]
    masked = (project / err_rel).read_text(encoding="utf-8")
    assert "gw.internal.example" not in masked and "abcdefgh12345678" not in masked
    assert "ConnectError" in masked, "the error text stays readable"


@pytest.mark.covers("FR-01.11")
def test_force_needs_the_marker_when_a_stale_completed_marker_sits_beside_a_skipped_row(project):
    assert run_tool(project, "record", "--review-type", "plan", "--status", "not_run",
                    "--reason-code", "missing-keys")[0] == 0
    run_dir = project / ".shipwright" / "planning" / "iterate" / RUN_ID
    (run_dir / "external_review_state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    assert force_strands_marker(project, RUN_ID, "plan", "not_run") is True
    (run_dir / "external_review_state.json").write_text(json.dumps({"status": "skipped_config_disabled"}), encoding="utf-8")
    assert force_strands_marker(project, RUN_ID, "plan", "not_run") is False
