"""Drift-protection for the design phase's requirement write-back rules.

The mechanised half of this work (the declaration, the touch check) has its own
unit tests. The half that lives in the runtime prompt cannot be unit-tested — but
it CAN be pinned, so that a future edit removing it fails loudly instead of
quietly restoring the old behaviour, where a feedback round changed what a flow
does and the requirement kept describing the older intent.

Anchors are normalized rule keys inside the section they belong to, not
arbitrary prose: this survives rewording and whitespace changes but fails when a
rule disappears. Mirrors the ADR-021 / iterate Step-6 drift-protection pattern.

Origin: trg-e9e5188e (FR-01.04).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DESIGN_SKILL = REPO_ROOT / "plugins" / "shipwright-design" / "skills" / "design"
REVIEW_LOOP = DESIGN_SKILL / "references" / "review-loop.md"
ITERATION_MODE = DESIGN_SKILL / "references" / "iteration-mode.md"

#: The recorder the design round must call. Renaming it without updating the
#: prompt would leave a rule that reads fine and does nothing.
RECORDER = "record_requirement_impact.py"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing runtime prompt: {path}"
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The body under ``heading`` up to the next same-or-higher-level heading."""
    match = re.search(rf"^(#{{2,3}})\s*{re.escape(heading)}.*$", text,
                      re.MULTILINE | re.IGNORECASE)
    assert match, f"heading not found: {heading}"
    level = len(match.group(1))
    rest = text[match.end():]
    nxt = re.search(rf"^#{{1,{level}}}\s", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


# --------------------------------------------------------------------------
# AC-3 — the feedback round declares, and writes back SUBSTANCE
# --------------------------------------------------------------------------

def test_option_b_carries_the_behaviour_vs_appearance_read():
    body = _section(_read(REVIEW_LOOP), "Option B — Process Feedback")
    lowered = body.lower()
    assert "behaviour" in lowered or "behavior" in lowered
    assert "appearance" in lowered


def test_option_b_backflow_writes_requirement_substance_not_only_pointers():
    """The row that did not exist: an FR spec row in the PARTIAL backflow table."""
    body = _section(_read(REVIEW_LOOP), "Option B — Process Feedback")
    assert ".shipwright/planning/*/spec.md" in body, (
        "the partial Spec Backflow table must carry a requirements-spec row — "
        "without it the round writes back pointers only"
    )
    assert "substance" in body.lower()


def test_option_b_snapshots_a_baseline_before_revising():
    """Without it the touch check is satisfiable for free — nothing commits
    before build, so every untracked spec.md reads as "changed"."""
    body = _section(_read(REVIEW_LOOP), "Option B — Process Feedback")
    assert "--snapshot-baseline" in body
    assert "baseline" in body.lower()


def test_option_b_records_the_declaration():
    body = _section(_read(REVIEW_LOOP), "Option B — Process Feedback")
    assert RECORDER in body
    assert "--phase design" in body
    assert "--impact none" in body and "--reason" in body


@pytest.mark.parametrize("flag", ["--run-id", "--scope", "--worktree"])
def test_declaration_command_carries_its_identity_and_evidence(flag):
    """Identity is (run_id, phase, scope); evidence comes from git, not the caller."""
    assert flag in _section(_read(REVIEW_LOOP), "Option B — Process Feedback")


# --------------------------------------------------------------------------
# AC-4 — finalization refuses while a round is silent
# --------------------------------------------------------------------------

def test_option_a_has_a_requirement_write_back_gate():
    body = _section(_read(REVIEW_LOOP), "Option A — Finalize")
    assert "Requirement Write-Back Gate" in body


def test_write_back_gate_runs_a_real_checker_not_a_prose_instruction():
    """AC-4 says finalization must REFUSE; an `ls` cannot refuse anything."""
    body = _section(_read(REVIEW_LOOP), "Option A — Finalize")
    assert "check_design_round_declarations.py" in body
    assert "--run-id" in body


def test_write_back_gate_documents_its_exit_codes():
    body = _section(_read(REVIEW_LOOP), "Option A — Finalize")
    assert "undeclared" in body
    assert "damaged" in body


def test_write_back_gate_rejects_a_declaration_from_another_run():
    body = _section(_read(REVIEW_LOOP), "Option A — Finalize")
    assert "run id" in body.lower()
    assert "does **not** count" in body or "does not count" in body


def test_flow_diagram_shows_the_declaration_step():
    text = _read(REVIEW_LOOP)
    assert "Declare the round's requirement impact" in text
    assert "Requirement Write-Back Gate" in text


# --------------------------------------------------------------------------
# The single-screen iteration path routes to the same rules
# --------------------------------------------------------------------------

def test_iteration_mode_points_at_the_declaration():
    text = _read(ITERATION_MODE)
    assert "requirement impact" in text.lower()
    assert "review-loop.md" in text
