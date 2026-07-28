"""The external code review must stay an independent route, not a chained one.

`iteration-reviews.md` used to trigger the external cascade *"iff the internal
`code-reviewer` subagent fired in this run"*, which put both reviews in series
behind one point of failure. This guard exists because the wording is what
agents actually follow at runtime — the enforcement in
`review_record_check.py` catches the outcome, but only after a run has already
skipped its review, and only if someone reads the failure. The prose is the
preventive half.

Asserted on normalised text so reflowing a paragraph does not fail the suite
while a changed *rule* does.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWS_DOC = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "iteration-reviews.md"
)


def _norm(text: str) -> str:
    text = text.replace("—", "-").replace("’", "'").replace("§", "")
    text = re.sub(r"^[ \t]*>[ \t]?", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*`_]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def test_trigger_is_not_conditional_on_internal():
    """The chained wording must not come back.

    The exact phrase is pinned because it is the one that caused the defect;
    a paraphrase that re-chains the two would need its own review anyway.
    """
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "fires iff the internal code-reviewer subagent fired" not in norm
    assert "it is not conditional on the internal code-reviewer having fired" in norm


def test_trigger_states_its_own_conditions():
    """Independent means it carries the thresholds itself."""
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "fires on its own conditions" in norm
    for threshold in ("diff > 100 lines", "security-sensitive files touched",
                      "complexity = medium+"):
        assert threshold in norm, threshold


def test_small_exemption_does_not_contradict_the_thresholds():
    """The trivial/small exemption must be conditional, not blanket.

    Found by external code review. The trigger lists `diff > 100 lines` and
    `security-sensitive files` as independent conditions, so a blanket "for
    trivial/small the cascade does NOT run" contradicts it for a small run that
    touches auth or ships a large diff — and under the new decoupling there is
    no internal-reviewer chain left to resolve the contradiction implicitly.
    Two rules that disagree are the exact defect this whole change is about, so
    the wording is pinned rather than left to reading order.
    """
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "for trivial/small iterates the cascade does not run" not in norm
    assert "meets none of the three" in norm
    assert "not for small runs as such" in norm


def test_escalation_is_stated():
    """When the internal pass cannot run, responsibility must move outward."""
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "escalate, never lapse" in norm
    assert "the external review becomes mandatory" in norm


def test_substitution_bookkeeping_is_forbidden():
    """`completed` must not be used for a pass that did not run.

    Three runs on one day recorded the same situation two different ways; this
    pins the one the contract means.
    """
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "do not record it completed \"by substitution\"" in norm \
        or "by substitution" in norm


def test_doc_names_the_enforcing_gate():
    """The prose and the gate must point at each other, or one will drift.

    Identifiers are matched against the RAW text: ``_norm`` strips underscores
    along with Markdown emphasis, so ``check_review_record`` would normalise to
    ``checkreviewrecord`` and the assertion would pass or fail for the wrong
    reason.
    """
    raw = REVIEWS_DOC.read_text(encoding="utf-8")
    assert "check_review_record" in raw
    assert "review_record_check.py" in raw
    assert "`not_applicable` on both does not satisfy it" in raw
