"""The phase-runner names the run-23 choice tool, so an autonomous phase does not hand its questions back."""

from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "agents" / "phase-runner.md"


def test_phase_runner_points_at_the_precedence_and_routine_kinds():
    text = RUNNER.read_text(encoding="utf-8")
    assert "record_autonomous_choice.py" in text
    assert "--kind precedence" in text and "--kind routine" in text
    assert "hard requirement > brief > approved screen > plan" in text
