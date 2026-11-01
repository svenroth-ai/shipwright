"""The one escalation that holds ONLY its own unit, and the signal that a run is unattended.

A sub-iterate that must ask (an existing AC changed or removed, no single FR owns the new AC, a new area of the
product) cannot be built until the operator answers. Under a campaign that stops THAT unit - ``running -> held``,
``record`` exits 0 - while the rest of the wave still builds and merges. Every other escalation keeps the
whole-wave STRICT-STOP (exit 3). The hold needs a well-formed escalation: ``status: escalated``, the reason code,
and a non-empty ``ac_questions`` whose every entry has a valid ``question_sha256`` (``cmd_record`` additionally
requires a claimed unit of a sub-iterate loop). Campaign finalize step 5 prints the open ``ac_questions``.

**Unattended** is read from state the agent does not type: the campaign loop environment
(``SHIPWRIGHT_LOOP_ID`` / ``SHIPWRIGHT_LOOP_UNIT_ID``, exported by the orchestrator) or a campaign worktree
directory (``campaign-*``, the name the isolation guard enforces). An unattended run refuses inline answers and
takes answers only from the operator channel. That channel is a guard, not authentication: the operator-side tool
sets ``SHIPWRIGHT_AC_OPERATOR_CHANNEL``, and an agent with a shell could set it too; what the guard buys is that
an answer cannot be produced by accident or by the plain tool flow, and that every decision records how it was
answered (``answered_via``) for the F11 check and the reviewers.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

AC_HOLD_REASON = "ac_question_requires_operator"
OPERATOR_ENV = "SHIPWRIGHT_AC_OPERATOR_CHANNEL"
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")


def is_ac_hold(result: object) -> bool:
    """True for a well-formed AC-question escalation (reason code AND non-empty ``ac_questions`` with valid sha256s)."""
    if not (isinstance(result, dict) and result.get("status") == "escalated" and result.get("reason_code") == AC_HOLD_REASON):
        return False
    qs = result.get("ac_questions")
    return isinstance(qs, list) and bool(qs) and all(isinstance(q, dict) and isinstance(q.get("question_sha256"), str) and _SHA.match(q["question_sha256"]) for q in qs)


def is_unattended(project_root: str | Path = "") -> bool:
    """True when this run is part of a campaign loop (environment) or lives in a campaign worktree."""
    if os.environ.get("SHIPWRIGHT_LOOP_ID") or os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID"):
        return True
    return bool(project_root) and Path(project_root).resolve().name.startswith("campaign-")


def operator_channel_open() -> bool:
    """True when the operator-side tool marked this process (a guard, not authentication)."""
    return bool(os.environ.get(OPERATOR_ENV))
