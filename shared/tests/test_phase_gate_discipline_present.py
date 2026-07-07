"""Honoring drift-guard (SS2): every covered phase skill must carry the
single-session gate-discipline block, and the shared contract it points to must
exist. This is what makes "each phase skill HONORS it" a testable claim.

The block lives wherever that plugin keeps its First-Actions detail: inline in
SKILL.md (project / design / deploy) or in references/first-actions.md
(plan / build). We assert the honoring tokens appear in that union.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.gate_policy import COVERED_PHASES

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_CONTRACT = _REPO_ROOT / "shared" / "prompts" / "single-session-gate-discipline.md"


def _skill_dir(phase: str) -> Path:
    return _REPO_ROOT / "plugins" / f"shipwright-{phase}" / "skills" / phase


def _honoring_text(phase: str) -> str:
    """Combined text of the places a phase may carry its First-Actions detail."""
    d = _skill_dir(phase)
    parts = []
    for cand in (d / "SKILL.md", d / "references" / "first-actions.md"):
        if cand.is_file():
            parts.append(cand.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_shared_contract_exists():
    assert _SHARED_CONTRACT.is_file(), "shared/prompts/single-session-gate-discipline.md missing"
    text = _SHARED_CONTRACT.read_text(encoding="utf-8")
    for token in ("auto-default", "orchestrator-approve", "hard-stop", "resolve_gate_policy.py"):
        assert token in text


@pytest.mark.parametrize("phase", list(COVERED_PHASES))
def test_phase_skill_has_discipline_block(phase):
    text = _honoring_text(phase)
    assert text, f"no SKILL.md/first-actions.md found for phase {phase}"
    # The recognizable marker.
    assert "Single-Session Gate Discipline" in text, (
        f"phase {phase} is missing the Single-Session Gate Discipline block"
    )
    # It must invoke the resolver for THIS phase.
    assert "resolve_gate_policy.py" in text
    assert f"--phase {phase}" in text
    # And point at the shared contract (single source of the full rule).
    assert "single-session-gate-discipline.md" in text
