"""Integration tests for tools/record_review_pass.py.

AC8 is the important one: a real run of the CLI across all five types, driven
from the payload shapes the reviewers actually emit, produces a record that the
F11 gate then PASSES. Unit-testing the pieces separately would not have caught a
CLI that writes a record the gate rejects — the two must be exercised together.

Also covers the immutability exit code (AC3), the marker dual-write (AC7), and
the `close-missing` escape hatch for runs predating the record (AC10).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.review_record import record_path  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402

TOOL = str(_SHARED / "scripts" / "tools" / "record_review_pass.py")
RUN_ID = "iterate-2026-07-21-review-record"
REASON = "docs-only diff; the doubt pass is conditional per iteration-reviews.md"

CODE_REVIEWER_REPLY = """\
Here is my review.

```json
{"section": "review-record", "review": [
  {"severity": "high", "category": "correctness", "file": "lib/x.py", "line": 12,
   "finding": "the lock is released before the write", "suggestion": "widen the lock"}
]}
```
"""

DOUBT_REVIEWER_REPLY = json.dumps({
    "stage": "doubt", "gating": "advisory-must-address", "trigger": "io-boundary",
    "doubts": [{"severity": "medium", "lens": "reversibility",
                "claim_under_doubt": "the record is safe to rewrite",
                "disproof_attempt": "a terminal status can be overwritten with --force",
                "what_would_resolve_it": "log every forced overwrite"}],
})

SELF_REVIEW_REPLY = json.dumps({"items": [
    {"name": "Spec Compliance", "verdict": "pass", "note": "all ACs covered"},
    {"name": "Test Quality", "verdict": "fail", "note": "no error-path test on the CLI"},
]})

EXTERNAL_REVIEW_OUTPUT = json.dumps({
    "success": True, "provider": "openrouter",
    "reviews": {
        "gemini": {"status": "success", "feedback":
                   "- **Category:** Risk\n- **Severity:** Medium\n"
                   "- **Finding:** The gate blocks in-flight runs.\n"},
        "openai": {"status": "success", "feedback":
                   "- Category: bug\n- Severity: high\n- File: tools/x.py:7\n"
                   "- Finding: the marker write is not transactional.\n"},
    },
})


@pytest.fixture
def project(tmp_path):
    iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True)
    (iterates / f"{RUN_ID}.json").write_text(json.dumps({
        "run_id": RUN_ID, "date": "2026-07-21T00:00:00+00:00", "type": "feature",
        "complexity": "medium", "branch": "iterate/review-record", "tests_passed": True,
    }), encoding="utf-8")
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    return tmp_path


def run_tool(project, *args):
    result = subprocess.run(
        [sys.executable, TOOL, *args, "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode, result.stdout + result.stderr


def payload(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


# --- AC8: the whole path, CLI → gate ----------------------------------------


def test_recording_all_five_types_makes_the_gate_pass(project, tmp_path):
    assert check_review_record(project, RUN_ID).ok is False  # nothing recorded yet

    code, _ = run_tool(project, "init")
    assert code == 0

    for args in (
        ["record", "--review-type", "self", "--status", "completed",
         "--from", "self-review",
         "--payload-file", payload(tmp_path, "self.json", SELF_REVIEW_REPLY)],
        ["record", "--review-type", "code", "--status", "completed",
         "--from", "code-reviewer",
         "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY)],
        ["record", "--review-type", "doubt", "--status", "completed",
         "--from", "doubt-reviewer",
         "--payload-file", payload(tmp_path, "doubt.json", DOUBT_REVIEWER_REPLY)],
        ["record", "--review-type", "plan", "--status", "completed",
         "--from", "external-review-json", "--provider", "openrouter",
         "--marker-status", "completed",
         "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT)],
        ["record", "--review-type", "external_code", "--status", "not_applicable",
         "--disposition", REASON],
    ):
        code, output = run_tool(project, *args)
        assert code == 0, output

    result = check_review_record(project, RUN_ID)
    assert result.ok, result.detail

    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    reviews = record["reviews"]
    assert reviews["code"]["findings"][0]["severity"] == "high"
    assert reviews["code"]["findings"][0]["source"] == "code-reviewer"
    assert reviews["doubt"]["findings"][0]["category"] == "reversibility"
    assert reviews["self"]["findings_count"] == 1, "only the failed item is a finding"
    assert reviews["plan"]["findings_count"] == 2, "both provider legs are merged"
    assert reviews["external_code"]["status"] == "not_applicable"


# --- AC7: marker dual-write -------------------------------------------------


def test_a_plan_record_dual_writes_the_legacy_marker(project, tmp_path):
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--from", "external-review-json", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT),
    )
    assert code == 0, output

    planning = project / ".shipwright" / "planning" / "iterate"
    shared_marker = planning / "external_review_state.json"
    run_scoped_marker = planning / RUN_ID / "external_review_state.json"

    assert shared_marker.exists(), "the historic shared path must keep working"
    assert run_scoped_marker.exists(), "the run-scoped copy is what the Mission view reads"
    assert json.loads(shared_marker.read_text(encoding="utf-8"))["status"] == "completed"
    assert json.loads(run_scoped_marker.read_text(encoding="utf-8"))["findings_count"] == 2


def test_a_marker_is_not_written_for_an_internal_type(project, tmp_path):
    run_tool(project, "init")
    code, _ = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--from", "code-reviewer", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY),
    )
    assert code == 2, "internal passes have no legacy marker — this is a usage error"


# --- AC3: immutability ------------------------------------------------------


def test_re_recording_a_terminal_type_exits_3(project, tmp_path):
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "code", "--status", "completed",
             "--from", "code-reviewer",
             "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY))
    before = record_path(project, RUN_ID).read_bytes()

    code, output = run_tool(project, "record", "--review-type", "code",
                            "--status", "not_run", "--disposition", REASON)

    assert code == 3, output
    assert json.loads(output)["error"] == "immutable"
    assert record_path(project, RUN_ID).read_bytes() == before


def test_force_overrides_immutability(project, tmp_path):
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "code", "--status", "completed",
             "--from", "code-reviewer",
             "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY))

    code, output = run_tool(project, "record", "--review-type", "code",
                            "--status", "not_run", "--disposition", REASON, "--force")

    assert code == 0, output


# --- AC2 / AC10: dispositions and the escape hatch --------------------------


def test_a_generic_disposition_is_rejected(project):
    run_tool(project, "init")
    code, output = run_tool(project, "record", "--review-type", "doubt",
                            "--status", "not_run", "--disposition", "skipped")
    assert code == 2
    assert "disposition" in output


def test_close_missing_unblocks_a_run_that_predates_the_record(project):
    """AC10 — a run already past its review phases when this landed must be one
    command away from finalizing, not trapped."""
    assert check_review_record(project, RUN_ID).ok is False

    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the per-run review record")

    assert code == 0, output
    assert set(json.loads(output)["closed"]) == {
        "self", "plan", "code", "doubt", "external_code"}
    assert check_review_record(project, RUN_ID).ok


def test_close_missing_leaves_already_recorded_types_alone(project, tmp_path):
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "code", "--status", "completed",
             "--from", "code-reviewer",
             "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY))

    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the per-run review record")

    assert code == 0
    assert "code" not in json.loads(output)["closed"]
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["code"]["status"] == "completed"
    assert record["reviews"]["code"]["findings_count"] == 1


def test_close_missing_refuses_to_assert_completed_in_bulk(project):
    code, output = run_tool(project, "close-missing", "--status", "completed",
                            "--disposition", "everything was definitely reviewed")
    assert code == 2
    assert "cannot be asserted in bulk" in output


# --- regressions from the code-review round ---------------------------------


def test_an_out_of_vocabulary_marker_status_is_rejected(project, tmp_path):
    """mark-review-state.py rejects these; recording through the new tool must
    not quietly lose that check and write a marker no consumer understands."""
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "complete",  # typo for "completed"
        "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT),
    )
    assert code == 2, output
    planning = project / ".shipwright" / "planning" / "iterate"
    assert not (planning / "external_review_state.json").exists()
    assert check_review_record(project, RUN_ID).ok is False


def test_recording_a_marker_type_as_completed_requires_a_marker_status(project, tmp_path):
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "external_code", "--status", "completed",
        "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT),
    )
    assert code == 2
    assert "marker-status is required" in output


def test_a_not_applicable_marker_type_needs_no_marker_status(project):
    """The marker vocabulary has no term for 'not applicable at this
    complexity'; forcing one would make the caller misstate why it did not run."""
    run_tool(project, "init")
    code, output = run_tool(project, "record", "--review-type", "external_code",
                            "--status", "not_applicable", "--disposition", REASON)
    assert code == 0, output


def test_repair_markers_rewrites_the_marker_without_touching_the_record(project, tmp_path):
    """The documented repair path: once the record is on disk it is immutable,
    so a failed marker write cannot be fixed by re-running `record`."""
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "plan", "--status", "completed",
             "--marker-status", "completed", "--from", "external-review-json",
             "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT))
    before = record_path(project, RUN_ID).read_bytes()
    planning = project / ".shipwright" / "planning" / "iterate"
    (planning / "external_review_state.json").unlink()

    code, output = run_tool(project, "repair-markers", "--review-type", "plan",
                            "--marker-status", "completed")

    assert code == 0, output
    assert (planning / "external_review_state.json").exists()
    assert record_path(project, RUN_ID).read_bytes() == before


def test_re_running_a_marker_bearing_record_repairs_instead_of_dead_ending(project, tmp_path):
    """Re-running the original command is what an operator actually does after a
    marker write fails; exit 3 with no way forward would be a dead end."""
    run_tool(project, "init")
    args = ["record", "--review-type", "plan", "--status", "completed",
            "--marker-status", "completed", "--from", "external-review-json",
            "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT)]
    run_tool(project, *args)
    planning = project / ".shipwright" / "planning" / "iterate"
    (planning / "external_review_state.json").unlink()

    code, output = run_tool(project, *args)

    assert code == 0, output
    assert json.loads(output).get("repaired") is True
    assert (planning / "external_review_state.json").exists()


def test_repair_markers_refuses_when_nothing_is_recorded_yet(project):
    run_tool(project, "init")
    code, output = run_tool(project, "repair-markers", "--review-type", "plan",
                            "--marker-status", "completed")
    assert code == 1
    assert "not recorded yet" in output


def test_init_over_a_corrupt_record_reports_json_not_a_traceback(project):
    """Every failure must exit through the JSON contract the orchestrator parses."""
    path = record_path(project, RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    code, output = run_tool(project, "init")

    assert code == 1
    assert json.loads(output)["error"] == "init_failed"
    assert path.read_text(encoding="utf-8") == "{not json"


def test_an_unsafe_run_id_is_reported_as_json(project):
    result = subprocess.run(
        [sys.executable, TOOL, "init", "--project-root", str(project),
         "--run-id", "../../escape"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["success"] is False


def test_a_leg_that_fails_to_parse_makes_the_merge_partial(project, tmp_path):
    """`structured` when only one of two legs parsed would hide that an entire
    provider's review was lost."""
    mixed = json.dumps({"success": True, "reviews": {
        "gemini": {"status": "success", "feedback":
                   "- Category: bug\n- Severity: high\n- Finding: a real defect\n"},
        "openai": {"status": "success", "feedback":
                   "I ran out of context mid-thought and never structured this"},
    }})
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "mixed.json", mixed),
    )

    assert code == 0, output
    assert json.loads(output)["parse_status"] == "partial"
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    plan = entry["reviews"]["plan"]
    assert plan["findings_count"] == 1
    assert "ran out of context" in plan["raw_excerpt"], (
        "the unparsed leg's own text must survive the shared excerpt budget"
    )


# --- regressions from the Stage-3 doubt pass --------------------------------


def test_a_restatement_is_rejected_not_answered_with_success(project, tmp_path):
    """The repair shortcut used to convert ANY immutability rejection into exit 0
    whenever --marker-status was present, rewriting the marker from the new
    arguments — so the record could say `completed` with 17 findings while the
    marker said the pass was skipped, with no --force and a success exit code."""
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "plan", "--status", "completed",
             "--marker-status", "completed", "--from", "external-review-json",
             "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT))
    before = record_path(project, RUN_ID).read_bytes()
    planning = project / ".shipwright" / "planning" / "iterate"
    marker_before = (planning / "external_review_state.json").read_bytes()

    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "not_run",
        "--disposition", REASON, "--marker-status", "skipped_config_disabled",
    )

    assert code == 3, output
    assert json.loads(output)["error"] == "immutable"
    assert record_path(project, RUN_ID).read_bytes() == before
    assert (planning / "external_review_state.json").read_bytes() == marker_before


def test_a_forced_correction_must_also_restate_the_marker(project, tmp_path):
    """--force rewrote the record but could leave the marker asserting the
    superseded result, with nothing to invalidate it."""
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "plan", "--status", "completed",
             "--marker-status", "completed", "--from", "external-review-json",
             "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT))

    code, output = run_tool(project, "record", "--review-type", "plan",
                            "--status", "not_run", "--disposition", REASON, "--force")

    assert code == 2
    assert "requires --marker-status" in output


def test_an_unitemizable_review_does_not_reach_the_marker_as_a_clean_zero(project, tmp_path):
    """`status: completed, findings_count: 0` is read by the existing consumer as
    'ran and found nothing'. A review whose prose could not be itemized must
    carry the caveat in the one field that consumer surfaces."""
    unparseable = json.dumps({"success": True, "reviews": {
        "gemini": {"status": "success",
                   "feedback": "I reviewed it and have thoughts but wrote no structure"},
    }})
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "u.json", unparseable),
    )

    assert code == 0, output
    assert json.loads(output)["parse_status"] == "unstructured"
    marker = json.loads((project / ".shipwright" / "planning" / "iterate"
                         / "external_review_state.json").read_text(encoding="utf-8"))
    assert marker["findings_count"] == 0
    assert "NOT a clean-review result" in (marker["reason"] or "")


def test_a_provider_that_errored_counts_toward_the_denominator(project, tmp_path):
    """An errored leg carries no `feedback`, so filtering it out first let one
    good leg of two report `structured` — hiding the likelier loss mode."""
    errored = json.dumps({"success": True, "reviews": {
        "gemini": {"status": "success",
                   "feedback": "- Category: bug\n- Severity: high\n- Finding: a real defect\n"},
        "openai": {"status": "error", "reason": "rate limited"},
    }})
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "e.json", errored),
    )

    assert code == 0, output
    assert json.loads(output)["parse_status"] == "partial"
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert "rate limited" in entry["reviews"]["plan"]["raw_excerpt"]


def test_close_missing_can_be_scoped_to_named_types(project):
    """The blanket form permanently asserts 'did not run' for passes that did —
    the self-review always runs, at every complexity."""
    run_tool(project, "init")
    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the per-run review record",
                            "--only", "doubt,external_code")

    assert code == 0, output
    assert set(json.loads(output)["closed"]) == {"doubt", "external_code"}
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["self"]["status"] == "pending"


def test_close_missing_rejects_an_unknown_type(project):
    run_tool(project, "init")
    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the record", "--only", "vibes")
    assert code == 2
    assert "vibes" in output


def test_a_not_run_pass_records_no_findings_even_with_a_payload(project, tmp_path):
    """A payload attached to a pass that did not run would attribute findings to
    a review that never happened."""
    run_tool(project, "init")
    code, _ = run_tool(
        project, "record", "--review-type", "code", "--status", "not_run",
        "--disposition", REASON, "--from", "code-reviewer",
        "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY),
    )
    assert code == 0
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["code"]["findings"] == []
