"""Prose guards for the review CONTRACT — `references/iteration-reviews.md`.

Third split of this suite, kept consistently **by artifact**. The lifecycle
prose that defers to this contract is guarded in `test_iterate_skill_prose.py`;
the campaign-side contract in `test_campaign_review_contract_prose.py`.

What these pin: the cascade description is not conditioned on the runner
contract delegating it; the `code` row belongs to Stage 2 and Stage 1 has none
(a stated CORRECTNESS gap, not a cosmetic one); and the escalation ladder first
establishes that the cascade genuinely cannot run — four blockers, an explicit
"anything else is not a blocker", and a conditional session policy excluded
until the request has been made and declined.
"""


from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE = REPO_ROOT / "plugins" / "shipwright-iterate"
_SKILL_DIR = _ITERATE / "skills" / "iterate"

SKILL_DOC = _SKILL_DIR / "SKILL.md"
REVIEWS_DOC = _SKILL_DIR / "references" / "iteration-reviews.md"


def _norm(text: str) -> str:
    """Normalise markdown so wording is asserted, not layout.

    Kept byte-identical to its campaign-side sibling so both files normalise the
    same way. Underscores are PRESERVED because the sibling asserts CLI flags
    (`--review-type external_code`); stripping `_` as markdown emphasis once
    turned every such assertion into one that could never match.
    """
    text = text.replace("—", "-").replace("’", "'").replace("§", "")
    text = re.sub(r"^[ \t]*>[ \t]?", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _section(doc: Path, heading: str, *, stop: str = "\n### ") -> str:
    """The body of one `###` section, up to the next same-level heading."""
    text = doc.read_text(encoding="utf-8")
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find(stop)
    return heading + (rest if end < 0 else rest[:end])

# --- AC2: the reference stops routing through the runner contract -----------


def test_cascade_section_is_not_conditioned_on_the_runner_contract():
    """`When the runner contract delegates …, all three stages run` made the
    cascade's execution a consequence of a contract a standalone run never
    invokes."""
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "when the sub-iterate-runner contract" not in norm, (
        "the cascade description must not be conditioned on the runner "
        "contract delegating it — standalone runs have no runner"
    )


def test_cascade_section_names_the_standalone_owner_explicitly():
    """Stating who runs it must not be left to inference from a delegation."""
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "a standalone iterate spawns the cascade itself" in norm, (
        "the reference must say plainly that a standalone iterate spawns the "
        "cascade itself — it has the Agent tool"
    )


def test_escalation_defines_what_a_real_blocker_is():
    """The ladder opened at 'cannot be run' and never said what that means, so
    a conditional policy read as one."""
    # Scoped to the section, not the document: normalized "no agent tool"
    # already occurs four times elsewhere in this file (campaign + runner
    # prose), so a document-wide search made that item vacuous and let step 0
    # migrate out of the ladder while staying green. Stage-2 finding.
    body = _norm(_section(REVIEWS_DOC, "### When the internal reviewer cannot run"))
    assert "there are exactly four" in body, (
        "the COUNT must be pinned in the same phrase the disposition rule "
        "refers to, or a fifth class silently makes 'which of the four' stale"
    )
    assert "anything not on this list is not a blocker" in body, (
        "listing four without excluding everything else lets a rewrite add "
        "'and a standing session policy' while keeping all four words "
        "(Stage-3 doubt T4)"
    )
    for blocker in ("no agent tool", "errored", "autonomous", "declined"):
        assert blocker in body, (
            f"the escalation section must name '{blocker}' as a real blocker"
        )


def test_a_conditional_policy_is_not_a_blocker_until_declined():
    """The whole point: 'not yet asked' is not 'cannot run'."""
    norm = _norm(_section(REVIEWS_DOC, "### When the internal reviewer cannot run"))
    # Contiguous: the 21-char fragment alone had no subject and no object, so
    # "a tool error is not a blocker until it recurs" satisfied it while the
    # policy sentence was deleted outright (Stage-3 doubt T5).
    assert "a standing session policy that a request would lift" in norm, (
        "the SUBJECT of the exclusion must be pinned"
    )
    assert "if you cannot establish from this session that permission was given, ask" in norm, (
        "the fail-open rule must be pinned — nothing carries a grant across "
        "compaction, handoff or resume (Stage-3 doubt: permission has no carrier)"
    )
    assert "is not a blocker until" in norm, (
        "the section must say a standing policy a request would lift is not a "
        "blocker until the request has been made and declined"
    )


def test_the_disposition_must_name_which_blocker_applied():
    """'a session directive' reads identically whether or not anyone asked."""
    # Section-scoped and EXACT. A 320-char backward window was measured by
    # Stage 2 to sit ~22 chars from a false green: delete the guarded clause
    # and an unrelated "doubt roles are not cascaded externally" drifts into
    # range. Proximity is not the rule; the clause is.
    body = _norm(_section(REVIEWS_DOC, "### When the internal reviewer cannot run"))
    assert "which of the four" in body, (
        "the not_run disposition requirement must force naming the blocker class"
    )
    assert "record code - and doubt" in body, (
        "AC4 covers code AND doubt — the first version required it of `code` "
        "only, and a doubt not_run is one of the observed instances it exists "
        "to fix"
    )


def test_a_project_grant_satisfies_the_policy_outright():
    """Step 0 said a policy is not a blocker 'until asked and declined'. With a
    standing grant there is nothing left to ask — the policy is already
    satisfied, which is a different state from 'not yet asked'."""
    body = _norm(_section(REVIEWS_DOC, "### When the internal reviewer cannot run"))
    assert "has already made it" in body, (
        "the ladder must say a CLAUDE.md grant has already made the request"
    )
    assert "nothing is gated, and there is nothing to ask" in body, (
        "'satisfied' is a different state from 'not yet asked' — pin both"
    )


def test_the_grant_is_scoped_to_subagents_not_workflows():
    """The carve-out has to survive where the grant is described, or a reader
    of this file alone concludes fan-out is granted too."""
    body = _norm(_section(REVIEWS_DOC, "### When the internal reviewer cannot run"))
    assert "the grant covers the review cascade only" in body, (
        "dynamic workflows, deep-research and parallel implementation "
        "subagents keep their own per-invocation opt-in — the Workflow tool's "
        "contract requires it, and Stage 2 caught the first wording silently "
        "authorising build's section-builder fan-out"
    )
    assert "read the file - do not assume it" in body, (
        "the ladder must tell the agent to LOOK for the grant; asserting that "
        "every onboarded project carries one is false for repos adopted "
        "before it shipped and for any project that deleted the section"
    )
