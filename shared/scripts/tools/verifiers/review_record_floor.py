"""Whether a RECORDED review pass actually counts — the substance half of the gate.

Split from :mod:`review_record_check` at the repo's 300-line source cap, on a
seam that was already there: that module asks *has every type answered, and did
the record ship*; this one asks *does the answer mean what it says*. Every
predicate here exists because a row can be well-formed, terminal, schema-valid —
and still describe a review nobody ran.

The gate calls them in order of specificity: an unanswered type reports as
unanswered, then the floor, then the Stage-1 precedence rule, because the three
need different repairs ("record the pass" / "run a review" / "run Stage 1
first") and the more specific message has to win.
"""

from __future__ import annotations


from lib.review_payloads import ADAPTERS  # noqa: E402
from lib.review_record import entry_for  # noqa: E402

from .common import CheckResult

__all__ = [
    "carries_evidence",
    "code_review_floor",
    "stage_one_precedes_stage_two",
    "substitution_note",
]

CHECK_NAME = "review record (every review pass closed)"

#: Complexities where a code review must actually have HAPPENED, not merely been
#: answered. The phase matrix says Full Code Review "always" from medium up; at
#: small it is conditional on risk flags, so a small run with neither review is
#: compliant and must not be blocked.
FLOORED_COMPLEXITIES = ("medium", "large")

#: The pair that can carry the code-review pass. `doubt` is deliberately absent:
#: it is Stage-3, conditional and advisory by design, so requiring it would
#: block runs the contract says may skip it.
_CODE_REVIEW_TYPES = ("code", "external_code")

#: ``lib.review_payloads.ADAPTERS``' no-op member. ``record --status completed``
#: with ``--from`` omitted defaults to it, so a row naming it as ``recorded_by``
#: is precisely the evidence-free shape.
_NO_ADAPTER = "none"

#: The adapter names that constitute evidence — every real one, minus the no-op.
_EVIDENCE_ADAPTERS = frozenset(ADAPTERS) - {_NO_ADAPTER}

_TOOL = "shared/scripts/tools/record_review_pass.py"


def substitution_note(record: dict, complexity: str) -> str:
    """Say what an external-only pass does NOT cover, on the PASSING result.

    The floor is satisfied by `code` OR `external_code`, and that is correct —
    the two are independent routes to a code review. But they are not
    equivalent routes: per `iteration-reviews.md`, the spec-compliance and
    doubt roles are deliberately NOT cascaded to external providers. So a run
    carried by `external_code` alone has had no Stage-1 gate and no adversarial
    pass, and nothing in a green gate said so.

    Reported rather than enforced on purpose. Requiring the internal cascade
    here would re-encode the phase matrix inside a verifier — the design this
    module's docstring rejects, and that rejection still stands. Naming the
    residual cost costs nothing and leaves the decision where it belongs.
    """
    if complexity not in FLOORED_COMPLEXITIES:
        return ""
    reviews = record.get("reviews", {}) or {}

    def _status(review_type: str) -> str:
        return str((reviews.get(review_type) or {}).get("status", ""))

    if _status("code") == "completed" or _status("external_code") != "completed":
        return ""
    note = (
        " — NOTE: the code-review floor is carried by `external_code` alone. "
        "The external route is a generic code-quality second opinion; Stage-1 "
        "spec-compliance (`spec-reviewer`, the HARD-GATE) and Stage-3 "
        "`doubt-reviewer` are not cascaded to external providers"
    )
    # `doubt` is recorded independently, so it may have run even when the
    # internal code pass did not. Claiming otherwise would make the note itself
    # the unreliable narrator it exists to prevent (Stage-1 spec-review REJECT).
    if _status("doubt") == "completed":
        return note + ", so Stage-1 did not run for this change (Stage-3 did)."
    return note + ", so neither ran for this change."


def code_review_floor(
    record: dict, complexity: str, run_id: str,
) -> CheckResult | None:
    """At medium+, at least one code review must have actually run.

    Answering every type is bookkeeping; this asks whether a review HAPPENED.
    Without it the record could read `not_run` across the board — dispositions
    and all — and the gate still returned green, so a medium+ iterate could ship
    with no code review of any kind.

    ``not_applicable`` deliberately does NOT satisfy the floor. If it did, the
    gate would be satisfiable by re-labelling, which is the same
    substance-versus-bookkeeping failure it exists to close. An individual type
    may still be `not_applicable`; both of them cannot be.

    Runs AFTER the pending check so an unanswered type keeps reporting as
    unanswered — the two failures need different repairs ("record the pass" vs
    "run a review"), and the more specific message has to win.
    """
    if complexity not in FLOORED_COMPLEXITIES:
        return None

    reviews = record.get("reviews", {}) or {}
    completed = [
        t for t in _CODE_REVIEW_TYPES
        if str((reviews.get(t) or {}).get("status", "")) == "completed"
    ]
    evidenced = [t for t in completed if carries_evidence(reviews.get(t) or {})]
    if evidenced:
        return None
    if completed:
        return CheckResult(
            CHECK_NAME, False,
            f"the only completed code review(s) for this {complexity} iterate "
            f"({', '.join(completed)}) carry no evidence that one happened: no "
            "findings, no provider, no raw excerpt, and no recorded_by naming "
            "an adapter. A row in that shape is byte-identical to one nobody "
            "earned — `--status completed` with `--from` omitted produces "
            "exactly it. Re-record the pass handing over the reviewer's reply: "
            f"`record_review_pass.py record --run-id {run_id} --review-type "
            "<type> --status completed --from <adapter> --payload-file <reply> "
            "--force`",
        )

    return CheckResult(
        CHECK_NAME, False,
        f"no code review ran for this {complexity} iterate: both `code` and "
        "`external_code` are closed without having happened. Every review type "
        "being answered is bookkeeping — at medium+ the phase matrix requires a "
        "code review to actually take place. Run ONE of them and record it: the "
        "internal cascade (`spec-reviewer` → `code-reviewer` → `doubt-reviewer`) "
        "or the external one (`external_review.py --mode code`), then "
        f"`record_review_pass.py record --run-id {run_id} --review-type "
        "{code|external_code} --status completed …`. The two are independent "
        "routes, not a chain: if the internal reviewer cannot run, the external "
        "one carries the pass rather than lapsing with it.",
    )


def carries_evidence(entry: dict) -> bool:
    """Does this row show a review HAPPENED, beyond asserting that it did?

    Any ONE of four traces is enough, and each of them is something only a real
    pass produces:

    * ``findings`` — the review's own output;
    * ``provider`` — the external leg that answered;
    * ``raw_excerpt`` — the reply, kept verbatim when it could not be itemized;
    * ``recorded_by`` naming an adapter other than ``none``.

    The last is what separates the commonest honest case from the fabricated
    one. A clean internal review legitimately has no findings, no provider and
    no excerpt — but it was recorded ``--from code-reviewer``, so the adapter
    name is on the row. ``--status completed`` with ``--from`` omitted defaults
    to the ``none`` adapter and leaves all four empty.

    Blank is not present (external plan review, openai #6): ``provider: ""`` or
    a whitespace excerpt would otherwise be a one-character bypass of the whole
    check.

    This cannot defeat deliberate fabrication — nothing a verifier reads can,
    and this module's docstring already says so. It defeats the *accidental*
    evidence-free row, and turns the deliberate one into an explicit false
    statement in the diff rather than a default.
    """
    if entry.get("findings"):
        return True
    for key in ("provider", "raw_excerpt"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return True
    recorded_by = entry.get("recorded_by")
    # Membership, not non-blankness: the message calls this trace "a recorded_by
    # naming an ADAPTER", and `--recorded-by` takes no `choices`, so any string
    # cleared the floor with no payload, no provider and no excerpt — one
    # undocumented flag wide (Stage-3 doubt). Now the predicate and the message
    # say the same thing.
    return isinstance(recorded_by, str) and recorded_by.strip() in _EVIDENCE_ADAPTERS


def stage_one_precedes_stage_two(record: dict, run_id: str = "") -> CheckResult | None:
    """A completed internal ``code`` pass implies a completed ``spec`` pass.

    Stage 1 (``spec-reviewer``) is the spec-compliance HARD-GATE: per SKILL.md
    Step 8 a REJECT blocks Stage 2 until the diff is fixed and re-reviewed. So
    ``code = completed`` while ``spec`` is anything else describes a cascade
    that skipped its own first gate — the record now says both things and only
    one of them can be true.

    Scoped to the INTERNAL pass on purpose. ``external_code`` is a generic
    code-quality second opinion; ``iteration-reviews.md`` deliberately does not
    cascade the spec-compliance or doubt roles to external providers, so a run
    carried by ``external_code`` alone correctly closes ``spec`` as ``not_run``
    with a disposition. Requiring it there would block the documented external
    route — which is exactly the fallback that exists for when the internal
    reviewer cannot run. ``_substitution_note`` already REPORTS that residual
    cost on the passing result; this check does not convert it into a block.

    **The Stage-1 row is held to the same evidence bar as the others.** A
    ``completed`` status alone would make the HARD-GATE this whole change exists
    to render provable the ONE row that can still be asserted rather than
    evidenced — with :func:`carries_evidence` sitting forty lines above it
    (Stage-2 code review). ``--status completed`` with ``--from`` omitted
    produces exactly the empty shape AC-2 rejects for ``code``.
    """
    spec_entry = entry_for(record, "spec")
    if not spec_entry:
        # A record that carries no `spec` row in EITHER section cannot answer
        # this question, and every exit available to it is bad: invent evidence
        # for `spec`, --force-rewrite a real `code` row to not_run and destroy
        # its findings, or delete the record. Its `code` row is already terminal
        # and immutable. The ordering rule applies to cascades that could have
        # recorded Stage 1 (Stage-3 doubt).
        #
        # This asks whether the record can ANSWER, not which section it uses.
        # The predecessor asked `"gates" not in record`, which meant the same
        # thing only while `gates` was the sole home of `spec`. Once `spec` was
        # promoted and the seam retired, every NEW record also lacks the key —
        # so that guard would have waved through every run from then on and this
        # HARD-GATE ordering rule would have stopped firing silently, with all
        # tests still green (`test_review_record_stage_one_guard.py`).
        return None
    reviews = record.get("reviews", {}) or {}
    if str((reviews.get("code") or {}).get("status", "")) != "completed":
        return None
    # No `or "absent"` fallback: the guard above already returned for every
    # record that carries no `spec` row, so an empty status is unreachable here
    # and the message vocabulary should match the reachable states.
    spec_status = str(spec_entry.get("status", ""))
    # `--run-id` is REQUIRED by the CLI, so a remediation that omits it exits 2
    # on usage — the "blocks with no way forward" trap, twice over.
    how = (f"`{_TOOL} record --run-id {run_id or '<run-id>'} --review-type spec "
           "--status completed --from code-reviewer --payload-file <reply>`")
    if spec_status == "completed":
        if carries_evidence(spec_entry):
            return None
        return CheckResult(
            CHECK_NAME, False,
            "`spec` is recorded completed but carries no evidence a review "
            "happened: no findings, no provider, no raw excerpt, and no "
            "recorded_by naming an adapter. The Stage-1 HARD-GATE is held to "
            f"the same bar as the code review it precedes. Re-record it: {how} "
            "--force",
        )
    return CheckResult(
        CHECK_NAME, False,
        f"`code` is recorded completed but `spec` is {spec_status!r} — Stage 1 "
        "(`spec-reviewer`) is the HARD-GATE that must PASS before the "
        "code-reviewer runs, so a completed Stage 2 with no completed Stage 1 "
        f"describes a cascade that skipped its own first gate. Record it: {how}"
        ", or — if the pass was carried externally — record `code` as not_run "
        "and let `external_code` satisfy the floor.",
    )
