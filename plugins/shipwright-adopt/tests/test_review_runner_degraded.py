"""A degraded Layer-3 review must not read as a completed one
(iterate-2026-08-01-llm-review-truncation-guard, AC-9).

``llm_review.py`` gained a third per-leg status, ``degraded`` — a reply the
provider itself declared truncated or returned empty. Before that fix a
cut-off answer was reported as ``success``, so adopt's Layer-3 gate could be
satisfied by half a review.

Adopt is the consumer whose status vocabulary changed, and the external plan
review asked for this boundary to be pinned rather than reasoned about: the
concern was that ``review_runner`` might treat any non-error result as usable
and preserve the fail-open under a new status name. It does not — it keys off
the aggregate ``success`` — and this test keeps that true.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import review_runner  # noqa: E402

_SNAPSHOT = {"profile": {"matched": "python"}, "features": [], "stack": {}}


def _install_fake_llm_review(monkeypatch, result: dict):
    """Make review_runner's dynamic ``import llm_review`` resolve to a stub."""
    fake = type(sys)("llm_review")
    fake.run_review = lambda *_a, **_kw: result  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_review", fake)


def _degraded_result() -> dict:
    return {
        # What run_review now returns when every leg was cut off: success is the
        # aggregate `any(status == "success")`, so it is False.
        "success": False,
        "provider": "openrouter",
        "reviews": {
            "deepseek": {
                "status": "degraded",
                "feedback": "1. Findi",
                "via": "openrouter",
                "reason": "provider reported the reply was cut off (finish_reason=length)",
            },
            "openai": {
                "status": "degraded",
                "feedback": "",
                "via": "openrouter",
                "reason": "provider returned an empty reply",
            },
        },
    }


def test_degraded_only_review_is_not_completed(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_llm_review(monkeypatch, _degraded_result())

    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)

    assert got["status"] != "completed"
    assert got["status"] == "skipped"
    assert got["reason"] == "llm_returned_unsuccess"


def test_degraded_status_is_visible_in_the_written_review(tmp_path, monkeypatch):
    """The partial text is kept, but labelled — a human reading the artifact
    must be able to see the review did not finish."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_llm_review(monkeypatch, _degraded_result())

    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)
    body = Path(got["review_path"]).read_text(encoding="utf-8")

    # Assert on the rendered per-leg HEADING, not a whole-document substring:
    # the feedback text itself could contain either word, which would make a
    # bare `"success" not in body` pass or fail for the wrong reason.
    assert "## deepseek — degraded" in body
    assert "## openai — degraded" in body
    assert "— success" not in body


def test_a_real_review_still_completes(tmp_path, monkeypatch):
    """Guard against over-correction: a genuine review must still pass."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_llm_review(
        monkeypatch,
        {
            "success": True,
            "provider": "openrouter",
            "reviews": {
                "deepseek": {
                    "status": "success",
                    "feedback": "1. Finding: real",
                    "via": "openrouter",
                    "reasoning_cap_dropped": "retried with reasoning UNBOUNDED",
                },
                "openai": {"status": "degraded", "feedback": "", "via": "openrouter"},
            },
            "partial": True,
            "warnings": ["deepseek: provider route degraded"],
        },
    )

    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)

    assert got["status"] == "completed"
    assert got["provider"] == "openrouter"
    assert got["partial"] is True
    assert got["warnings"]
    body = Path(got["review_path"]).read_text(encoding="utf-8")
    assert "> Warning: retried with reasoning UNBOUNDED" in body
