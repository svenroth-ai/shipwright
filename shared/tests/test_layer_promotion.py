"""Pins ``lib.layer_promotion.evaluate_fr``'s per-requirement predicate (P3.5)."""

from __future__ import annotations

import pytest

from lib.layer_promotion import (
    REASON_BOUND_TEST_ABSENT,
    REASON_CONTRADICTS_DECISION,
    REASON_LAYER_UNDETERMINABLE,
    SKIP_ALREADY_EXPLICIT,
    SKIP_ALREADY_EXPLICIT_CONSISTENT,
    SKIP_DEMOTED_CONSISTENT,
    SKIP_EXISTING_REQUIRED_NOT_VERIFIED,
    SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT,
    SKIP_NO_EVIDENCE_YET,
    bound_but_absent_layers,
    evaluate_fr,
    highest_ok_layer,
)
from lib.layer_promotion_ledger import evidence_fingerprint


def _link(*, layer, status="enabled", executed="pass"):
    return {"id": f"t::{layer}", "path": f"t::{layer}", "layer": layer,
            "status": status, "executed": executed}


def _node(**overrides):
    node = {
        "id": "FR-01.11",
        "spec_path": ".shipwright/planning/01-adopted/spec.md",
        "status": "active",
        "required_layers": ["unit"],
        "required_layers_source": "inferred_legacy",
        "tests": {"unit": [_link(layer="unit")]},
        "coverage": {"unit": "ok"},
    }
    node.update(overrides)
    return node


# ---------------------------------------------------------------------------
# highest_ok_layer / bound_but_absent_layers
# ---------------------------------------------------------------------------


def test_highest_ok_layer_none_when_nothing_ok():
    assert highest_ok_layer({"unit": "MISSING"}) is None
    assert highest_ok_layer({}) is None


def test_highest_ok_layer_picks_the_highest_ranked_ok():
    assert highest_ok_layer({"unit": "ok", "integration": "ok", "e2e": "MISSING"}) == "integration"


def test_highest_ok_layer_ranks_an_unrecognised_layer_label_below_every_canonical_one():
    # Mirrors `_layer_coverage_binding`'s own pinned contract (P3.3): an unknown
    # label is never credited over a canonical layer, but wins when it is alone.
    assert highest_ok_layer({"unit": "ok", "weird": "ok"}) == "unit"
    assert highest_ok_layer({"weird": "ok"}) == "weird"


def test_bound_but_absent_layers_needs_enabled_and_not_run():
    tests = {
        "unit": [_link(layer="unit", executed="pass")],
        "integration": [_link(layer="integration", executed="not_run")],
        "e2e": [_link(layer="e2e", status="skipped", executed="not_run")],
    }
    assert bound_but_absent_layers(tests) == {"integration"}


def test_bound_but_absent_layers_treats_any_undecided_executed_value_as_absent():
    # external code review (glm/low, P3.5 round 2): a missing key, None, or
    # an unrecognised value from schema drift is exactly as undecided as the
    # literal "not_run" sentinel -- not silently waved through.
    link_missing_key = {"id": "t", "path": "t", "layer": "integration", "status": "enabled"}
    tests = {
        "unit": [_link(layer="unit", executed="pass")],
        "integration": [link_missing_key],
        "e2e": [_link(layer="e2e", executed=None)],
    }
    assert bound_but_absent_layers(tests) == {"integration", "e2e"}


# ---------------------------------------------------------------------------
# evaluate_fr — collision / undeterminable
# ---------------------------------------------------------------------------


def test_collision_id_always_escalates_layer_undeterminable():
    node = _node(coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=True)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_LAYER_UNDETERMINABLE
    assert decision["fr"] == "FR-01.11"


def test_collision_id_cleared_by_a_recorded_demotion_is_exitable():
    # external code review (glm/high, P3.5 round 1): a collision must not be a
    # wall forever -- an operator's demoted decision clears it, permanently.
    node = _node(coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=True, ledger_entry={"action": "demoted"})
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_DEMOTED_CONSISTENT,
    }


def test_collision_id_cleared_by_a_recorded_promotion_that_matches_the_spec():
    node = _node(coverage={"unit": "ok"}, required_layers_source="explicit")
    decision = evaluate_fr(node, is_collision=True, ledger_entry={"action": "promoted"})
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_ALREADY_EXPLICIT_CONSISTENT,
    }


def test_collision_id_with_a_recorded_promotion_but_spec_not_explicit_escalates_contradiction():
    node = _node(coverage={"unit": "ok"}, required_layers_source="inferred_legacy")
    decision = evaluate_fr(node, is_collision=True, ledger_entry={"action": "promoted"})
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_CONTRADICTS_DECISION


# ---------------------------------------------------------------------------
# evaluate_fr — already explicit / no ledger
# ---------------------------------------------------------------------------


def test_already_explicit_with_no_ledger_entry_is_a_silent_skip():
    node = _node(required_layers_source="explicit")
    decision = evaluate_fr(node, is_collision=False)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_ALREADY_EXPLICIT}


# ---------------------------------------------------------------------------
# evaluate_fr — no evidence yet (the common case)
# ---------------------------------------------------------------------------


def test_no_ok_layer_and_no_absent_binding_skips_without_escalating():
    node = _node(tests={}, coverage={"unit": "MISSING"})
    decision = evaluate_fr(node, is_collision=False)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_NO_EVIDENCE_YET}


# ---------------------------------------------------------------------------
# evaluate_fr — bound test absent from CI evidence (case 2)
# ---------------------------------------------------------------------------


def test_absent_binding_above_highest_ok_escalates_bound_test_absent():
    node = _node(
        required_layers=["unit"],
        tests={
            "unit": [_link(layer="unit", executed="pass")],
            "integration": [_link(layer="integration", executed="not_run")],
        },
        coverage={"unit": "ok", "integration": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_BOUND_TEST_ABSENT


def test_absent_binding_at_or_below_highest_ok_still_escalates():
    # external code review (openai/high, P3.5 round 1): the spec's rule is
    # unconditional -- "the named test did not run ... at all" -- not "and
    # outranks what's green". A same-layer absent binding must escalate too,
    # not be waved through because SOME test at that layer passed.
    node = _node(
        required_layers=["unit"],
        tests={"unit": [_link(layer="unit", executed="pass"), _link(layer="unit", executed="not_run")]},
        coverage={"unit": "ok"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_BOUND_TEST_ABSENT


def test_a_failing_test_is_a_decided_non_promotion_not_an_escalation():
    # external plan review (openai/high, P3.5): a failing test is neither
    # "absent" (needs a human) nor "ok" (promotable) -- it is decided, and the
    # decision is simply "not yet", the same as no test at all.
    node = _node(
        required_layers=["e2e"],
        tests={"e2e": [_link(layer="e2e", executed="fail")]},
        coverage={"e2e": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_NO_EVIDENCE_YET}


def test_a_failing_higher_layer_does_not_block_promotion_at_a_lower_ok_layer():
    node = _node(
        required_layers=["unit"],
        tests={
            "unit": [_link(layer="unit", executed="pass")],
            "integration": [_link(layer="integration", executed="fail")],
        },
        coverage={"unit": "ok", "integration": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "promote"
    assert decision["required_layers"] == ["unit"]


def test_unrecognised_layer_reporting_ok_escalates_undeterminable():
    # external code review (openai/medium, P3.5 round 1): an unranked "ok"
    # can't be placed relative to the canonical layers, so it is undeterminable
    # rather than promotable, even though it is the only layer reporting "ok".
    node = _node(required_layers=[], tests={}, coverage={"weird": "ok"})
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_LAYER_UNDETERMINABLE


def test_unrecognised_layer_with_a_not_run_binding_also_escalates_absent():
    # external code review (glm/low, P3.5 round 1): a typo'd layer name must
    # not silently degrade to "no evidence yet" just because it has no rank.
    node = _node(
        required_layers=[], tests={"weird": [_link(layer="weird", executed="not_run")]},
        coverage={},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_BOUND_TEST_ABSENT


def test_existing_required_layer_without_fresh_ok_evidence_skips_not_promotes():
    # external code review (openai/high, P3.5 round 1): a NEW ok layer never
    # papers over an EXISTING required layer that isn't currently green.
    node = _node(
        required_layers=["unit", "integration"],
        tests={"unit": [_link(layer="unit")]},
        coverage={"unit": "ok", "integration": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "skip"
    assert decision["reason_code"] == "existing_required_layer_not_verified"


def test_absent_binding_with_no_ok_layer_at_all_escalates():
    node = _node(
        required_layers=["e2e"],
        tests={"e2e": [_link(layer="e2e", executed="not_run")]},
        coverage={"e2e": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_BOUND_TEST_ABSENT


# ---------------------------------------------------------------------------
# evaluate_fr — promote (union of required + ok layers, never a narrowing)
# ---------------------------------------------------------------------------


def test_promote_matches_current_required_layer_when_evidence_agrees():
    node = _node(required_layers=["unit"], coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=False)
    assert decision == {
        "fr": "FR-01.11", "action": "promote",
        "required_layers": ["unit"], "highest_ok": "unit",
    }


def test_promote_widens_required_layers_union_never_narrows():
    node = _node(
        required_layers=["unit"],
        tests={"unit": [_link(layer="unit")], "integration": [_link(layer="integration")]},
        coverage={"unit": "ok", "integration": "ok"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "promote"
    assert decision["required_layers"] == ["unit", "integration"]
    assert decision["highest_ok"] == "integration"


def test_promote_widens_by_the_highest_observable_layer_only_not_every_ok_layer():
    # external code review (glm/medium, P3.5 round 2): binding a layer the FR
    # never required just because it happens to be green too creates a HARD
    # gate obligation this promotion never justified -- "integration" here
    # must NOT be added, only "unit" (already required) and "e2e" (highest).
    node = _node(
        required_layers=["unit"],
        tests={
            "unit": [_link(layer="unit")],
            "integration": [_link(layer="integration")],
            "e2e": [_link(layer="e2e")],
        },
        coverage={"unit": "ok", "integration": "ok", "e2e": "ok"},
    )
    decision = evaluate_fr(node, is_collision=False)
    assert decision["action"] == "promote"
    assert decision["required_layers"] == ["unit", "e2e"]
    assert decision["highest_ok"] == "e2e"


def test_promotable_evidence_but_a_hand_annotated_live_cell_is_skipped_instead_of_overwriting():
    # Medium finding, Stage-3 doubt-review round 2, P3.5 post-push round:
    # same bug CLASS as the already-fixed HIGH (stale-manifest narrowing),
    # on the one axis that fix doesn't reach -- "widen never narrow" holds
    # over the canonical layer SET a promotion computes, not over the
    # cell's raw TEXT. A promotable FR whose live cell still carries a
    # hand-added annotation must be skipped, not have `render_layers`
    # silently delete that text on rewrite. Stage-1 spec-review REJECTed an
    # earlier version of this fix that reported this as an `escalate` with
    # REASON_LAYER_UNDETERMINABLE: the predicate demonstrably HOLDS here
    # (that's why we reach this branch at all), so this is not one of the
    # spec's three named undecidable cases, and that reason code's spec
    # meaning ("the highest observable layer cannot be determined from the
    # manifest") was untrue -- it WAS determined. A named skip reports the
    # same data-protection outcome honestly instead.
    node = _node(required_layers=["unit"], coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=False, live_cell_has_non_canonical_content=True)
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT,
    }


def test_promotable_evidence_with_no_residual_content_still_promotes():
    # The default (`live_cell_has_non_canonical_content=False`, and every
    # existing promote test above that never passes the kwarg at all) must
    # be unaffected -- this is an ADDITIONAL gate, not a behavior change to
    # the common, pure-canonical case.
    node = _node(required_layers=["unit"], coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=False, live_cell_has_non_canonical_content=False)
    assert decision["action"] == "promote"


# ---------------------------------------------------------------------------
# evaluate_fr — ledger says "promoted" (case 3, drift)
# ---------------------------------------------------------------------------


def test_ledger_promoted_and_spec_still_explicit_is_a_consistent_skip():
    node = _node(required_layers_source="explicit", coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=False, ledger_entry={"action": "promoted"})
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_ALREADY_EXPLICIT_CONSISTENT,
    }


def test_ledger_promoted_but_spec_reverted_escalates_contradiction():
    node = _node(required_layers_source="inferred_legacy", coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=False, ledger_entry={"action": "promoted"})
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_CONTRADICTS_DECISION


def test_ledger_promoted_but_live_cell_narrowed_escalates_contradiction():
    # external code review (openai/high + glm/spec, P3.5 round 2): the cell
    # is STILL explicit, so a bare already_explicit check alone would call
    # this a clean skip -- but it no longer includes everything the ledger
    # recorded as promoted, which is a silent hand-demotion.
    node = _node(required_layers_source="explicit", coverage={"unit": "ok"})
    decision = evaluate_fr(
        node, is_collision=False,
        ledger_entry={"action": "promoted", "required_layers": ["unit", "integration"]},
        live_required_layers=["unit"],
    )
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_CONTRADICTS_DECISION


def test_ledger_promoted_and_live_cell_widened_by_hand_is_still_a_consistent_skip():
    # Widening (not narrowing) an already-explicit cell by hand is not the
    # property this ledger exists to police -- only a narrowing is.
    node = _node(required_layers_source="explicit", coverage={"unit": "ok"})
    decision = evaluate_fr(
        node, is_collision=False,
        ledger_entry={"action": "promoted", "required_layers": ["unit"]},
        live_required_layers=["unit", "integration"],
    )
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_ALREADY_EXPLICIT_CONSISTENT,
    }


def test_ledger_promoted_with_a_corrupted_required_layers_element_fails_closed():
    # "Your call" item, Stage-5 code-review, P3.5 post-push round: a hand-
    # corrupted ledger entry (e.g. `null` where a layer name belongs) must
    # raise the fail-closed `ValueError` `load_ledger`'s docstring promises,
    # not a raw `AttributeError` from `.strip()` on a non-string element.
    node = _node(required_layers_source="explicit", coverage={"unit": "ok"})
    with pytest.raises(ValueError, match="not a string"):
        evaluate_fr(
            node, is_collision=False,
            ledger_entry={"action": "promoted", "required_layers": [None, "unit"]},
            live_required_layers=["unit"],
        )


@pytest.mark.parametrize("reformatted_cell", ["unit integration", "unit/integration"])
def test_ledger_promoted_and_a_cosmetic_reformat_is_not_a_false_narrowing(reformatted_cell):
    # Low finding, Stage-4 code-review, P3.5 post-push round:
    # `fr_layer_cell_writer.live_required_layers` splits on comma ONLY, so a
    # maintainer's purely cosmetic reformat of an already-explicit cell
    # (still canonical, still the same two layers) arrives here as ONE
    # un-split token -- `_narrowed_since_promotion` must not read that as a
    # hand-shrink of the ledger's recorded `["unit", "integration"]`.
    node = _node(required_layers_source="explicit", coverage={"unit": "ok"})
    decision = evaluate_fr(
        node, is_collision=False,
        ledger_entry={"action": "promoted", "required_layers": ["unit", "integration"]},
        live_required_layers=[reformatted_cell],
    )
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_ALREADY_EXPLICIT_CONSISTENT,
    }


# ---------------------------------------------------------------------------
# evaluate_fr — ledger says "demoted" (case 3, veto)
# ---------------------------------------------------------------------------


def test_ledger_demoted_and_no_fresh_evidence_is_a_consistent_skip():
    node = _node(required_layers_source="inferred_legacy", coverage={"unit": "MISSING"})
    decision = evaluate_fr(node, is_collision=False, ledger_entry={"action": "demoted"})
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_DEMOTED_CONSISTENT,
    }


def test_ledger_demoted_with_unchanged_evidence_since_the_veto_is_a_consistent_skip():
    """"Exitable" (spec L25/L40, Stage-1 spec-review finding): a veto recorded
    against evidence that still looks green does not re-escalate forever
    against that SAME unchanged evidence -- report the flag via the skip
    reason, never re-litigate a decision the operator already made."""
    node = _node(required_layers_source="inferred_legacy", coverage={"unit": "ok"})
    ledger_entry = {"action": "demoted", "evidence_fingerprint": evidence_fingerprint(node)}
    decision = evaluate_fr(node, is_collision=False, ledger_entry=ledger_entry)
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_DEMOTED_CONSISTENT,
    }


def test_ledger_demoted_but_evidence_drifted_since_the_veto_escalates_again():
    """A genuinely NEW evidence state the operator's veto never saw is exactly
    the case a permanent veto cannot have considered -- it escalates again,
    naming the same REASON_CONTRADICTS_DECISION as every other ledger/live
    mismatch, distinguishing "already vetoed, nothing changed" from
    "something changed since the veto"."""
    demoted_against = _node(required_layers_source="inferred_legacy", coverage={"unit": "MISSING"})
    ledger_entry = {
        "action": "demoted", "evidence_fingerprint": evidence_fingerprint(demoted_against),
    }
    node = _node(required_layers_source="inferred_legacy", coverage={"unit": "ok"})
    decision = evaluate_fr(node, is_collision=False, ledger_entry=ledger_entry)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_CONTRADICTS_DECISION


def test_ledger_demoted_but_evidence_drifted_toward_worse_stays_a_decided_skip():
    """Drift alone is not enough (Stage-1 spec-review round 2): the fingerprint
    differs, but the drift is TOWARD worse evidence (green -> MISSING, e.g. a
    tagged test got deleted) -- nothing is promotable, so this stays the plain
    decided skip it would be even without a ledger entry at all. Escalating
    here would be a 4th, unnamed undecidable case and re-interrupt an operator
    over an FR the tool could not have promoted anyway (spec L11/L21)."""
    demoted_against = _node(required_layers_source="inferred_legacy", coverage={"unit": "ok"})
    ledger_entry = {
        "action": "demoted", "evidence_fingerprint": evidence_fingerprint(demoted_against),
    }
    node = _node(required_layers_source="inferred_legacy", coverage={"unit": "MISSING"})
    decision = evaluate_fr(node, is_collision=False, ledger_entry=ledger_entry)
    assert decision == {
        "fr": "FR-01.11", "action": "skip", "reason_code": SKIP_DEMOTED_CONSISTENT,
    }


def test_ledger_demoted_but_spec_is_explicit_anyway_escalates():
    node = _node(required_layers_source="explicit", coverage={"unit": "MISSING"})
    decision = evaluate_fr(node, is_collision=False, ledger_entry={"action": "demoted"})
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_CONTRADICTS_DECISION


# ---------------------------------------------------------------------------
# Never a narrowing / never a demotion, by construction
# ---------------------------------------------------------------------------


def test_no_action_ever_removes_a_layer_or_reinstates_advisory_provenance():
    """Characterisation over every branch: nothing evaluate_fr returns ever asks
    the caller to shrink required_layers or set required_layers_source back to
    a legacy value. "Cannot silently demote" is a property of what this
    function is even ABLE to say, not a runtime check on what it says.

    Scope note (Stage-3 doubt-review HIGH finding, P3.5 post-push round):
    this operates at the PURE evaluate_fr level only -- ``node`` here is
    handed in already-built, so it cannot catch a CALLER (``promote_required_
    layers.plan_promotions``) narrowing what it builds ``node["required_
    layers"]`` FROM before ever reaching this function. That regression is
    pinned at the CLI level instead:
    ``tools/tests/test_promote_required_layers.py::
    test_stale_manifest_never_narrows_a_hand_declared_multi_layer_cell``.
    """
    cases = [
        _node(),
        _node(required_layers_source="explicit"),
        _node(coverage={"unit": "MISSING"}, tests={}),
        _node(required_layers=["unit"], tests={
            "unit": [_link(layer="unit")], "integration": [_link(layer="integration")],
        }, coverage={"unit": "ok", "integration": "ok"}),
    ]
    ledgers = [None, {"action": "promoted"}, {"action": "demoted"}]
    for node in cases:
        for ledger_entry in ledgers:
            decision = evaluate_fr(node, is_collision=False, ledger_entry=ledger_entry)
            if decision["action"] == "promote":
                assert set(decision["required_layers"]) >= set(node["required_layers"])
            else:
                assert "required_layers" not in decision


# ---------------------------------------------------------------------------
# P3.5 restart, round 2: realistic (non-empty) CI-sourced evidence shapes.
# `promote_required_layers.py`'s CI-aware caller REPLACES `node["coverage"]`/
# `node["tests"]` with what `ci_execution_evidence.resolve_execution_evidence`
# returns; "CI evidence not confirmed for this FR" becomes `coverage={}`,
# `tests={}` on `eval_node`, never the raw producer's populated-but-MISSING
# shape (see the design doc's "Why the evaluator needs no code change, round
# 2" section for the full realistic-shape trace). These tests pin the two
# ends of that trace directly against `evaluate_fr` itself.
# ---------------------------------------------------------------------------


def test_ci_evidence_unconfirmed_for_a_fresh_fr_is_a_decided_skip_not_an_escalation():
    # "CI hasn't confirmed this FR yet" as `promote_required_layers.py` builds
    # it: coverage={}, tests={} (never the raw manifest's own claimed values).
    node = _node(required_layers_source="inferred_legacy", coverage={}, tests={})
    decision = evaluate_fr(node, is_collision=False, ledger_entry=None)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_NO_EVIDENCE_YET}


def test_ci_evidence_confirmed_but_bound_test_did_not_execute_escalates_case_2():
    # Case A from the design doc's realistic-shape trace: the real CI-regen
    # producer (`_test_links_requirements.build_requirement_nodes`) yields a
    # POPULATED `tests` map with `status:"enabled", executed:"not_run"` (or any
    # non-decided value), and `coverage[layer]=="MISSING"` -- never an empty
    # dict -- for a required layer whose bound test the CI run did not execute
    # (e.g. cross_plugin-marker exclusion). This is the sub-iterate spec's own
    # named case 2 ("the binding exists but the named test did not run in the
    # CI evidence at all") firing on REAL evidence shape, not a fabricated
    # empty-dict trace.
    node = _node(
        required_layers_source="inferred_legacy",
        tests={"unit": [{"id": "t1", "path": "t1", "status": "enabled", "executed": "not_run"}]},
        coverage={"unit": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False, ledger_entry=None)
    assert decision["action"] == "escalate"
    assert decision["reason_code"] == REASON_BOUND_TEST_ABSENT


def test_ci_evidence_confirmed_bound_test_executed_and_failed_is_a_decided_skip():
    # Case B: executed AND failing is a DECIDED "not green" -- `executed=="fail"`
    # is one of the two decided values, so this never reads as "absent."
    node = _node(
        required_layers_source="inferred_legacy",
        tests={"unit": [{"id": "t1", "path": "t1", "status": "enabled", "executed": "fail"}]},
        coverage={"unit": "MISSING"},
    )
    decision = evaluate_fr(node, is_collision=False, ledger_entry=None)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_NO_EVIDENCE_YET}


def test_ci_evidence_strictly_weaker_than_committed_never_promotes_the_stronger_claim():
    # Case C, the actual adversarial case: a hand-edited/stale committed
    # manifest claims `integration` is also "ok", but CI-sourced evidence
    # (what `eval_node` now holds, REPLACING the committed values entirely)
    # only confirms `unit`. The committed file's stronger claim about
    # `integration` must never leak through -- required_before already
    # includes it (a prior explicit/inferred declaration), so the existing
    # required-layer check catches it.
    node = _node(
        required_layers=["unit", "integration"], required_layers_source="inferred_legacy",
        tests={"unit": [{"id": "t1", "path": "t1", "status": "enabled", "executed": "pass"}]},
        coverage={"unit": "ok"},  # CI never confirmed "integration" at all
    )
    decision = evaluate_fr(node, is_collision=False, ledger_entry=None)
    assert decision["action"] == "skip"
    assert decision["reason_code"] == SKIP_EXISTING_REQUIRED_NOT_VERIFIED


def test_acs_poisoning_never_changes_the_decision_fr_level_only_d12():
    # AC-R11: `acs` is one of THREE fields `compare_traceability_manifest`
    # strips as execution-tier (alongside `tests`/`coverage`), but
    # `evaluate_fr` is FR-level only (D12) and never reads it at all -- proven
    # here by giving one node a deliberately poisoned `acs` claiming a layer
    # is "ok" that the FR-level `coverage` says is "MISSING", and asserting
    # the decision is IDENTICAL to the same node with `acs` removed entirely.
    base = _node(
        required_layers_source="inferred_legacy",
        tests={"unit": [{"id": "t1", "path": "t1", "status": "enabled", "executed": "not_run"}]},
        coverage={"unit": "MISSING"},
    )
    poisoned = dict(base)
    poisoned["acs"] = {"AC01": {"tests": {"e2e": [{"id": "fake"}]}, "coverage": {"e2e": "ok"}}}

    decision_clean = evaluate_fr(base, is_collision=False, ledger_entry=None)
    decision_poisoned = evaluate_fr(poisoned, is_collision=False, ledger_entry=None)
    assert decision_clean == decision_poisoned


def test_fingerprint_noise_on_a_demoted_fr_never_reescalates_when_verdict_is_unchanged():
    # AC-R14 (fingerprint-noise finding, deferred per the design doc): two CI-
    # sourced evidence snapshots for the SAME demoted FR that differ in raw
    # tests/coverage content (marker-selection churn -- different test IDs
    # observed run to run) but agree that `predicate_holds` stays False in
    # both (still no "ok" layer either time) -- must stay SKIP_DEMOTED_
    # CONSISTENT in both, never re-escalate on the noise alone.
    demoted_against = _node(
        required_layers_source="inferred_legacy",
        tests={"unit": [{"id": "run1-test", "path": "x", "status": "enabled", "executed": "fail"}]},
        coverage={"unit": "MISSING"},
    )
    ledger_entry = {"action": "demoted", "evidence_fingerprint": evidence_fingerprint(demoted_against)}
    noisy_but_still_not_green = _node(
        required_layers_source="inferred_legacy",
        tests={"unit": [{"id": "run2-different-test-id", "path": "y", "status": "enabled", "executed": "fail"}]},
        coverage={"unit": "MISSING"},
    )
    decision = evaluate_fr(noisy_but_still_not_green, is_collision=False, ledger_entry=ledger_entry)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_DEMOTED_CONSISTENT}


def test_the_closed_escalation_list_stays_exactly_three():
    # Cheap drift-pin (AC-R7): the sub-iterate spec names exactly three
    # undecidable cases; CI-evidence unavailability (design doc's "Why the
    # evaluator needs no code change") can only ever land in the skip action
    # space, never a fourth. A future edit adding a REASON_* constant without
    # updating the spec's own closed list fails here first.
    import lib.layer_promotion as layer_promotion_module

    reason_constants = {
        name for name in dir(layer_promotion_module)
        if name.startswith("REASON_") and isinstance(getattr(layer_promotion_module, name), str)
    }
    assert reason_constants == {
        "REASON_LAYER_UNDETERMINABLE", "REASON_BOUND_TEST_ABSENT", "REASON_CONTRADICTS_DECISION",
    }
