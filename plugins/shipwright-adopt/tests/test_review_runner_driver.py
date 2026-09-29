"""Adopt's Layer-3 review passes the Codex driver through to ``llm_review``.

Under Codextender (``CODEXTENDER_ACTIVE``) the session is Codex-driven, so the
shared review must swap its OpenAI-family leg for the cross-vendor 'opus' leg.
Outside it, the call shape stays exactly ``run_review(content, context)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import review_runner  # noqa: E402

_SNAPSHOT = {"profile": {"matched": "python"}, "features": [], "stack": {}}


def _capture_kwargs(monkeypatch) -> dict:
    captured: dict = {}
    fake = type(sys)("llm_review")

    def _run_review(content, context, **kwargs):
        captured.update(kwargs)
        return {"success": True, "provider": "openrouter", "reviews": {}}

    fake.run_review = _run_review  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_review", fake)
    return captured


def test_codextender_session_passes_driver_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    captured = _capture_kwargs(monkeypatch)

    review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)

    assert captured == {"driver": "codex"}


def test_plain_claude_session_passes_no_driver(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("CODEXTENDER_ACTIVE", raising=False)
    captured = _capture_kwargs(monkeypatch)

    review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)

    assert captured == {}
