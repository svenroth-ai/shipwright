"""Drift tests for FR-01.07 #6 and #7, downgraded to
``prompt-only (judgement)`` by sub-iterate ``e3-checks-test-security``
(campaign ``req3-06-enforcement-mono``).

**Why a drift test and not a gate.** Both criteria promise an OUTCOME is
*recorded*:

- #6 — "'fixed' means the tests passed after the fix". The only field that
  could carry this outcome, ``_remediation_status``, is READ with a default
  of ``"open"`` (``generate_security_report.py``) but is never WRITTEN by any
  code path (confirmed by grep across ``plugins/shipwright-security/scripts/``
  before writing this — the only two producer candidates,
  ``remediation-loop.md``'s prose Auto-Fix/Agent-Fix flows, never persist the
  status they describe).
- #7 — "a human-judgement finding carries the decision and the reason".
  ``classify_finding`` correctly routes a finding to ``needs-review``, but
  nothing downstream (``security_triage_emit.py`` enumerates findings and asks
  a *scope* question, never a per-finding Fix/Decline/Defer decision) ever
  records that decision or its reason anywhere.

Building a check against a field nothing writes would be exactly the
"weaker gate that pretends" the campaign forbids
(``2026-07-23-req3-ac-evidence-ledger-mono.md``'s own abort condition): no
deterministic oracle exists TODAY, so both lines are downgraded from
``prompt-only (mechanisable)`` to ``prompt-only (judgement)``. Per campaign
decision D7 (see sub-iterate ``e6-judgement-drift-tests``), a judgement line
gets a drift test on its instruction text and NOTHING ELSE — these two tests
are that remedy, scoped to the two lines this sub-iterate itself downgraded
(``e6`` owns the pre-existing 19; these are new).
"""

from __future__ import annotations

from pathlib import Path

_DOC = (
    Path(__file__).resolve().parents[1]
    / "skills" / "security" / "references" / "remediation-loop.md"
)

_LEDGER = (
    Path(__file__).resolve().parents[3]
    / ".shipwright" / "planning" / "campaigns"
    / "2026-07-23-req3-ac-evidence-ledger-mono.md"
)


def _read_doc() -> str:
    assert _DOC.exists(), f"remediation-loop.md missing at {_DOC}"
    return _DOC.read_text(encoding="utf-8")


def test_doc_exists():
    _read_doc()


def test_fr0107_line6_fixed_means_tests_passed_instruction_present():
    """FR-01.07 #6: the promise that 'fixed' is only claimed after the fix's
    own tests pass — pinned at both the flow-step and the status-vocabulary
    level, so either half disappearing silently fails this test."""
    text = _read_doc()
    assert 'If tests pass → mark as "fixed"' in text, (
        "remediation-loop.md's Auto-Fix Flow no longer ties 'fixed' to a "
        "passing test run (FR-01.07 #6, judgement line — instruction drifted)"
    )
    assert "`fixed` — successfully remediated" in text, (
        "remediation-loop.md's Status Tracking table no longer defines "
        "`fixed` (FR-01.07 #6, judgement line — instruction drifted)"
    )


def test_fr0107_line7_needs_review_decision_and_reason_instruction_present():
    """FR-01.07 #7: a human-judgement finding must carry a decision (Fix /
    Decline / Defer) and, for Decline, a reason — pinned at both the
    classification table and the interview-flow level."""
    text = _read_doc()
    assert (
        "`needs-review` | Architecture, business logic, complex issues | "
        "User decides: Fix / Decline / Defer" in text
    ), (
        "remediation-loop.md's classification table no longer routes "
        "needs-review findings to a Fix/Decline/Defer decision "
        "(FR-01.07 #7, judgement line — instruction drifted)"
    )
    assert "Decline: Skip with logged reason" in text, (
        "remediation-loop.md's User Interview Flow no longer requires a "
        "logged reason for Decline (FR-01.07 #7, judgement line — "
        "instruction drifted)"
    )


def test_ledger_records_both_lines_as_judgement_with_a_reason():
    """External review (openai, e3-checks-test-security PR): a wording-
    preserving ledger regression on the STATUS/reason/owner fields would go
    undetected by the two instruction-text assertions above alone. Assert
    the ledger's own rows separately, so a status flip back to
    'mechanisable' (or a silently dropped reason) fails here even if
    remediation-loop.md's prose is untouched."""
    assert _LEDGER.exists(), f"AC-evidence ledger missing at {_LEDGER}"
    text = _LEDGER.read_text(encoding="utf-8")
    assert (
        '| 6 | "fixed" means the tests passed after the fix | '
        "`prompt-only (judgement)` |" in text
    ), "ledger no longer records FR-01.07 #6 as prompt-only (judgement)"
    assert (
        "| 7 | a human-judgement finding carries the decision and the reason | "
        "`prompt-only (judgement)` |" in text
    ), "ledger no longer records FR-01.07 #7 as prompt-only (judgement)"
    assert "downgraded, sub-iterate e3-checks-test-security" in text, (
        "ledger no longer carries the downgrade reason for FR-01.07 #6/#7"
    )
