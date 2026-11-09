"""Q2 phase 1: the shared spec-reviewer prompt takes the claims file as an OPTIONAL third input and stays inside the runtime-prompt cap."""

from __future__ import annotations

from pathlib import Path

import pytest

_PROMPT = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-build" / "agents" / "spec-reviewer.md"


def _text() -> str:
    return _PROMPT.read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.11/AC50")
def test_the_prompt_stays_within_the_runtime_prompt_cap():
    assert len(_text().splitlines()) <= 400


@pytest.mark.covers("FR-01.11/AC50")
def test_without_the_claims_file_the_behaviour_is_stated_to_be_unchanged():
    text = _text()
    assert "Without\n   this third input" in text.replace("\r\n", "\n") and "never passes one" in text


@pytest.mark.covers("FR-01.11/AC50")
def test_the_per_ac_output_shape_and_the_phase_one_rule_are_in_the_prompt():
    flat = " ".join(_text().split())
    for needle in ("ac_verdicts", "matches | diverges", "diff_location", "weakens", "do **not** change `verdict`"):
        assert needle in flat, needle
    assert flat.index("## AC claims") < flat.index("## Anti-rationalization")
