"""The in-session gates — Step 6's STOP and Step 9's checklist, as a command.

Strict on purpose: unlike the phase verifier, which is lenient toward plans
written before these formats existed, this runs against the plan being
written now.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "checks" / "check-plan-gates.py"
)

WELL_FORMED = (
    "# Section: {name}\n\n"
    "Requirements: {frs}\n\n"
    "## Overview\nDoes the thing.\n\n"
    "## Implementation Steps\n1. one\n2. two\n\n"
    "## Tests First\n- a unit test\n"
)


def run_gates(planning_dir: Path, gate: str = "all") -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--planning-dir", str(planning_dir), "--gate", gate],
        capture_output=True, text=True, encoding="utf-8",
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:  # pragma: no cover - diagnostic path
        raise AssertionError(f"non-JSON stdout: {proc.stdout!r} / {proc.stderr!r}")


@pytest.fixture
def planning(tmp_path):
    """A planning split whose every gate passes."""
    d = tmp_path / "01-auth"
    (d / "sections").mkdir(parents=True)
    (d / "spec.md").write_text(
        "# Spec\n\n| ID | Requirement | Priority |\n| FR-01.01 | thing | Must |\n",
        encoding="utf-8",
    )
    (d / "plan.md").write_text(
        "# Plan\n\n<!-- SECTION_MANIFEST\n01-a\n02-b: 01-a\nEND_MANIFEST -->\n",
        encoding="utf-8",
    )
    for name in ("01-a", "02-b"):
        (d / "sections" / f"{name}.md").write_text(
            WELL_FORMED.format(name=name, frs="FR-01.01"), encoding="utf-8"
        )
    (d / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed",
            "provider": "openrouter",
            "verdicts": {"gemini": "approve", "openai": "revise"},
        }),
        encoding="utf-8",
    )
    return d


def _problems(out: dict, gate: str) -> list[str]:
    return next(g for g in out["gates"] if g["gate"] == gate)["problems"]


def test_a_clean_plan_passes_every_gate(planning):
    code, out = run_gates(planning)
    assert code == 0, out
    assert out["success"] is True
    assert out["failed"] == []


def test_a_missing_planning_dir_is_a_usage_error(tmp_path):
    code, out = run_gates(tmp_path / "nope")
    assert code == 2
    assert out["error"] == "planning_dir_not_found"


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


# --- the section gates (Step 9) ---------------------------------------------


def test_a_prerequisite_after_its_user_fails(planning):
    (planning / "plan.md").write_text(
        "# Plan\n\n<!-- SECTION_MANIFEST\n01-a: 02-b\n02-b\nEND_MANIFEST -->\n",
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections")
    assert code == 1
    assert any("numbered after it" in p for p in _problems(out, "sections"))


def test_an_uncovered_requirement_fails(planning):
    (planning / "spec.md").write_text(
        "# Spec\n\n| ID | Requirement | Priority |\n"
        "| FR-01.01 | thing | Must |\n| FR-01.02 | other thing | Must |\n",
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections")
    assert code == 1
    assert any("FR-01.02" in p and "no section" in p for p in _problems(out, "sections"))


def test_a_section_serving_no_requirement_fails(planning):
    (planning / "sections" / "02-b.md").write_text(
        "# Section: 02-b\n\n## Overview\nWork nobody asked for.\n\n"
        "## Implementation Steps\n1. one\n2. two\n\n## Tests First\n- t\n",
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections")
    assert code == 1
    assert any("02-b" in p and "no live requirement" in p for p in _problems(out, "sections"))


def test_an_ill_formed_section_fails_even_in_a_new_plan(planning):
    """No leniency in session: a section written today has no excuse."""
    (planning / "sections" / "02-b.md").write_text(
        "# Section: 02-b\n\nRequirements: FR-01.01\n\nJust prose.\n", encoding="utf-8"
    )
    code, out = run_gates(planning, "sections")
    assert code == 1
    problems = _problems(out, "sections")
    assert sum(1 for p in problems if p.startswith("02-b")) == 3


def test_a_declared_but_unwritten_section_fails(planning):
    (planning / "sections" / "02-b.md").unlink()
    code, out = run_gates(planning, "sections")
    assert code == 1
    assert any("declared but not written: 02-b" in p for p in _problems(out, "sections"))


def test_an_unparseable_manifest_reports_the_parse_errors(planning):
    (planning / "plan.md").write_text(
        "# Plan\n\n<!-- SECTION_MANIFEST\nBad Name\nEND_MANIFEST -->\n", encoding="utf-8"
    )
    code, out = run_gates(planning, "sections")
    assert code == 1
    assert any("Invalid section name" in p for p in _problems(out, "sections"))


def test_gate_selection_runs_only_what_was_asked_for(planning):
    assert [g["gate"] for g in run_gates(planning, "review")[1]["gates"]] == ["review"]
    assert [g["gate"] for g in run_gates(planning, "sections")[1]["gates"]] == ["sections"]
    assert [g["gate"] for g in run_gates(planning, "all")[1]["gates"]] == ["review", "sections"]
