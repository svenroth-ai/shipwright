"""The in-session gates — Step 6's STOP and the boundary check, as a
command. Step 9's section gates are split out into
``test_check_plan_gates_sections.py`` (300-LOC guideline).

Strict on purpose: unlike the phase verifier, which is lenient toward plans
written before these formats existed, this runs against the plan being
written now.
"""

import json
import subprocess
import sys

from tests._check_plan_gates_support import SCRIPT, _problems, run_gates

# `planning` and `bare_planning_dir` fixtures come from conftest.py — no
# import needed, and importing them here would shadow the same-named
# test-function parameters (ruff F811).


def test_a_clean_plan_passes_every_gate(planning):
    code, out = run_gates(planning)
    assert code == 0, out
    assert out["success"] is True
    assert out["failed"] == []


def test_a_missing_planning_dir_is_a_usage_error(tmp_path):
    code, out = run_gates(tmp_path / "nope")
    assert code == 2
    assert out["error"] == "planning_dir_not_found"


def test_project_root_is_required_not_defaulted_to_cwd(planning):
    """External code review, iterate-2026-09-11-e1-checks-plan-design: a
    silently-defaulted cwd let --gate boundary read an empty git evidence
    set and pass with nothing checked. Required now, matching
    check-design-gates.py."""
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--planning-dir", str(planning), "--gate", "review"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "--project-root" in proc.stderr


# --- the review gate (Step 6) -----------------------------------------------


def test_no_marker_blocks_section_splitting(planning):
    (planning / "external_review_state.json").unlink()
    code, out = run_gates(planning, "review")
    assert code == 1
    assert "did not run to completion" in _problems(out, "review")[0]


def test_an_undecided_reviewer_disagreement_blocks(planning):
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed",
            "verdicts": {"gemini": "approve", "openai": "reject"},
            "contradiction": {"detected": True, "requires_resolution": True,
                              "reason": "gemini=approve, openai=reject"},
        }),
        encoding="utf-8",
    )
    code, out = run_gates(planning, "review")
    assert code == 1
    assert "unresolved reviewer disagreement" in _problems(out, "review")[0]


def test_recording_the_decision_unblocks_it(planning):
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed",
            "verdicts": {"gemini": "approve", "openai": "reject"},
            "contradiction": {"detected": True, "requires_resolution": True, "reason": "x"},
            "contradiction_resolution": "sided with reject; re-split 02-b",
        }),
        encoding="utf-8",
    )
    assert run_gates(planning, "review")[0] == 0


def test_a_malformed_marker_blocks_rather_than_crashing(planning):
    (planning / "external_review_state.json").write_text("{ not json", encoding="utf-8")
    code, out = run_gates(planning, "review")
    assert code == 1
    assert "unreadable" in _problems(out, "review")[0]


def test_a_completed_review_that_recorded_no_verdicts_blocks(planning):
    """W5 only warns on this, because it audits plans of any age. In session
    the marker was written moments ago, so "no verdicts" means Step 5b ran
    without --verdict — which would make the disagreement check opt-out by
    omission."""
    (planning / "external_review_state.json").write_text(
        json.dumps({"status": "completed", "provider": "openrouter"}), encoding="utf-8"
    )
    code, out = run_gates(planning, "review")
    assert code == 1
    assert "no reviewer verdicts" in _problems(out, "review")[0]


def test_a_recorded_opt_out_still_passes(planning):
    """A skip branch has no reviewers, so it is not held to verdicts."""
    (planning / "external_review_state.json").write_text(
        json.dumps({"status": "skipped_user_opt_out", "reason": "offline demo"}),
        encoding="utf-8",
    )
    assert run_gates(planning, "review")[0] == 0


def test_a_marker_whose_stored_block_disagrees_with_its_verdicts_blocks(planning):
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed",
            "verdicts": {"gemini": "approve", "openai": "reject"},
            "contradiction": {"requires_resolution": False, "reason": "all fine, honest"},
        }),
        encoding="utf-8",
    )
    assert run_gates(planning, "review")[0] == 1


# --- the review gate's key-honesty check (Step 6, FR-01.03 #1) -------------


def test_a_skip_while_a_key_is_actually_available_is_a_false_skip(planning):
    (planning / "external_review_state.json").write_text(
        json.dumps({"status": "skipped_user_opt_out", "reason": "offline demo"}),
        encoding="utf-8",
    )
    code, out = run_gates(planning, "review", extra_env={"OPENROUTER_API_KEY": "sk-test-fake"})
    assert code == 1
    assert any("silently skipped" in p for p in _problems(out, "review"))


def test_a_completed_review_is_honest_even_when_a_key_is_available(planning):
    code, out = run_gates(planning, "review", extra_env={"OPENROUTER_API_KEY": "sk-test-fake"})
    assert code == 0, out


def test_a_skip_with_no_key_available_is_not_a_false_skip(planning):
    (planning / "external_review_state.json").write_text(
        json.dumps({"status": "skipped_user_opt_out", "reason": "offline demo"}),
        encoding="utf-8",
    )
    assert run_gates(planning, "review")[0] == 0


def test_gate_selection_runs_only_what_was_asked_for(planning):
    assert [g["gate"] for g in run_gates(planning, "review")[1]["gates"]] == ["review"]
    assert [g["gate"] for g in run_gates(planning, "sections")[1]["gates"]] == ["sections"]
    assert [g["gate"] for g in run_gates(planning, "all")[1]["gates"]] == [
        "review", "sections", "boundary",
    ]


# --- the boundary gate (FR-01.03 #7) ----------------------------------------


def test_boundary_passes_on_a_non_git_project(planning):
    code, out = run_gates(planning, "boundary")
    assert code == 0, out


def test_boundary_passes_when_only_shipwright_paths_changed(bare_planning_dir):
    assert run_gates(bare_planning_dir, "boundary")[0] == 0


def test_boundary_fails_on_a_production_path(tmp_path, bare_planning_dir):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')\n", encoding="utf-8")
    code, out = run_gates(bare_planning_dir, "boundary")
    assert code == 1
    assert any("src/app.py" in p for p in _problems(out, "boundary"))
