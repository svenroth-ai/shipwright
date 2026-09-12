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

import pytest

from tests._check_plan_gates_support import SCRIPT, _problems, run_gates

# `planning` and `bare_planning_dir` fixtures come from conftest.py — no
# import needed, and importing them here would shadow the same-named
# test-function parameters (ruff F811).


def test_a_clean_plan_passes_every_gate(planning, no_e2e_plugin_root):
    code, out = run_gates(planning, plugin_root=no_e2e_plugin_root)
    assert code == 0, out
    assert out["success"] is True
    assert out["failed"] == []


def test_a_missing_planning_dir_is_a_usage_error(tmp_path):
    code, out = run_gates(tmp_path / "nope")
    assert code == 2
    assert out["error"] == "planning_dir_not_found"


def test_a_missing_plugin_root_dir_is_a_usage_error(planning, tmp_path):
    code, out = run_gates(planning, "sections", plugin_root=tmp_path / "no-such-plugin")
    assert code == 2
    assert out["error"] == "plugin_root_not_found"


def test_a_missing_project_root_dir_is_a_usage_error(planning, tmp_path):
    """External Tier-3 review, PR #726 round 9: --project-root was resolved
    but never validated as a directory, so a typo'd root made
    git_dirty_paths() return no evidence and --gate boundary falsely pass.
    subprocess.run raises before the script even starts if `cwd` does not
    exist (all platforms), so this calls the script directly rather than
    through `run_gates` (whose `cwd` follows `project_root`)."""
    proc = subprocess.run(
        [
            sys.executable, SCRIPT,
            "--planning-dir", str(planning),
            "--project-root", str(tmp_path / "no-such-root"),
            "--gate", "boundary",
        ],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    out = json.loads(proc.stdout)
    assert proc.returncode == 2
    assert out["error"] == "project_root_not_found"


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


@pytest.mark.covers("FR-01.03/AC04")
def test_no_marker_blocks_section_splitting(planning):
    """FR-01.03/AC04: the review step's route must be on record before
    dividing the plan into sections is allowed to begin — a missing marker
    blocks the same review gate Step 9 requires to have passed first."""
    (planning / "external_review_state.json").unlink()
    code, out = run_gates(planning, "review")
    assert code == 1
    assert "did not run to completion" in _problems(out, "review")[0]


@pytest.mark.covers("FR-01.03/AC13")
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


@pytest.mark.covers("FR-01.03/AC13")
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


def test_gate_selection_runs_only_what_was_asked_for(planning, no_e2e_plugin_root):
    assert [g["gate"] for g in run_gates(planning, "review")[1]["gates"]] == ["review"]
    assert [
        g["gate"] for g in run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)[1]["gates"]
    ] == ["sections"]
    assert [
        g["gate"] for g in run_gates(planning, "all", plugin_root=no_e2e_plugin_root)[1]["gates"]
    ] == ["review", "sections", "boundary"]


def test_plugin_root_is_required_for_the_all_gate_too(planning):
    """External code review, iterate-2026-09-11-e1-checks-plan-design: a
    silently-optional --plugin-root let gate #11 (E2E journeys) skip without
    a trace instead of failing the usage. The `sections`-only case is
    covered in test_check_plan_gates_sections.py, next to gate #11."""
    code, out = run_gates(planning, "all")
    assert code == 2
    assert out["error"] == "plugin_root_required"
    # boundary/review alone still don't need it.
    assert run_gates(planning, "review")[0] == 0
    assert run_gates(planning, "boundary")[0] == 0


# --- the boundary gate (FR-01.03 #7) ----------------------------------------


def test_boundary_passes_on_a_non_git_project(planning):
    code, out = run_gates(planning, "boundary")
    assert code == 0, out


def test_boundary_passes_when_only_shipwright_paths_changed(bare_planning_dir):
    assert run_gates(bare_planning_dir, "boundary")[0] == 0


def test_boundary_passes_with_the_early_in_progress_plan_config(tmp_path, bare_planning_dir):
    """Stage-1 spec review, iterate-2026-09-11-e1-checks-plan-design: SKILL.md's
    First Action E writes ``shipwright_plan_config.json`` to the project root
    on EVERY session (not only at completion), so the boundary gate must
    allow it or it fails on every real plan session."""
    (tmp_path / "shipwright_plan_config.json").write_text("{}\n", encoding="utf-8")
    code, out = run_gates(bare_planning_dir, "boundary")
    assert code == 0, _problems(out, "boundary")


@pytest.mark.covers("FR-01.03/AC17")
def test_boundary_fails_on_a_production_path(tmp_path, bare_planning_dir):
    """FR-01.03/AC17: a finished plan hands on no production code — writing
    outside the planning phase's allowed prefixes is exactly that violation."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')\n", encoding="utf-8")
    code, out = run_gates(bare_planning_dir, "boundary")
    assert code == 1
    assert any("src/app.py" in p for p in _problems(out, "boundary"))

# The review gate's reviewer-failure / reviewer-identity handling
# (FR-01.03 AC19/AC20) is split into test_check_plan_gates_reviewers.py to
# stay under this file's own 300-LOC budget.
