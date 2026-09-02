"""Rendering contract for the one-off assistant UI review writer."""

from __future__ import annotations

import sys
import types
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
sys.path.insert(0, str(_TOOLS))

import review_assistant_ui_plan as subject  # noqa: E402


def test_degraded_review_keeps_reason_and_partial_body(tmp_path, monkeypatch):
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    fake = types.ModuleType("lib.llm_review")
    fake.DEFAULT_TIMEOUT_SECONDS = 240
    fake.detect_provider = lambda: "openrouter"
    captured = {}
    fake.run_review = lambda **kw: captured.update(kw) or {
        "provider": "openrouter",
        "reviews": {
            "glm": {
                "status": "degraded",
                "reason": "reply cut off",
                "feedback": "partial finding body",
            }
        },
    }
    monkeypatch.setitem(sys.modules, "lib.llm_review", fake)
    monkeypatch.setattr(sys, "argv", ["review_assistant_ui_plan.py", str(plan)])

    assert subject.main() == 0

    rendered = plan.with_name("plan-review.md").read_text(encoding="utf-8")
    assert "- Status: **degraded**" in rendered
    assert "- Reason: reply cut off" in rendered
    assert "## Reviewer: glm" in rendered
    assert "z-ai/glm-5.3, openai/gpt-5.6-terra" in rendered
    assert "partial finding body" in rendered
    assert captured["timeout"] == 240
