"""The one escalation that holds ONLY its own unit: an acceptance-criterion question for the operator.

A sub-iterate that must ask (an existing AC changed or removed, or no single FR owns the new AC) cannot be built
until the operator answers. Under a campaign that stops THAT unit - ``running -> held``, ``record`` exits 0 - while
the rest of the wave still builds and merges. Every other escalation keeps the whole-wave STRICT-STOP (exit 3).
Campaign finalize step 5 prints the open ``ac_questions`` from the held unit's ``result.json``.
"""

from __future__ import annotations

AC_HOLD_REASON = "ac_question_requires_operator"


def is_ac_hold(result: object) -> bool:
    """True for an ``escalated`` result whose reason code is the AC question."""
    return isinstance(result, dict) and result.get("status") == "escalated" and result.get("reason_code") == AC_HOLD_REASON
