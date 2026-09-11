"""``binding_predates_rollout`` / the trg-aedcfe7b transition rule: pure-evaluator
cases for check_binding_completeness's one-time transition grace, so an
``explicit`` binding that predates the gate's own rollout is not held to a
standard it never knew about. Split from ``test_layer_coverage_binding.py``
(same 300-LOC precedent that module's own docstring documents) the moment
this landed — the pure evaluator + wrapper cases predating this rule stay
there; only the transition-specific cases live here.

**Why the "behaviour changed" trigger here is a required_layers diff, not a
forced title edit** (external code review, P3.3 follow-up, glm, HIGH): the
sibling pure-evaluator file forces ``head[...]["title"] = "changed"`` to
trigger :func:`behavior_changed_keys` without needing a real semantic edit —
harmless there because no rollout snapshot is in play. Here it is NOT
harmless: :func:`binding_predates_rollout` requires the rollout snapshot's
title to match head's, so forcing only head's title while leaving the
rollout node's title at its unrelated default would make every "grace
granted" case here either fail outright or (worse) prove nothing about the
title-match guard, since title mismatch on its own already denies grace for
an unrelated reason. Every test below instead diffs ``required_layers``
between base and head as the change signal (already meaningful to the
scenario under test in every case — see per-test comments) and keeps title
identical across base/rollout/head, EXCEPT the one test that deliberately
exercises a title MISMATCH as its own subject.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_binding import (  # noqa: E402
    binding_predates_rollout,
    evaluate_binding_completeness,
)


def _node(disp, *, status="active", layers=("unit",), source="explicit",
          coverage=None, priority="Must", title=None):
    return {
        "id": disp, "spec_path": "", "title": title or f"t-{disp}", "priority": priority,
        "status": status, "required_layers": list(layers),
        "required_layers_source": source, "tests": {}, "coverage": coverage or {},
    }


def _manifest(nodes: dict, *, spec_hash="sha256:x"):
    return {
        "schema_version": 3, "spec_hash": spec_hash, "requirements": nodes,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


def _rollout_manifest(nodes: dict) -> dict:
    return _manifest(nodes, spec_hash="sha256:rollout")


def test_transition_grace_downgrades_an_unchanged_explicit_binding():
    # The literal motivating case: an `explicit` binding whose required_layers
    # value already existed, unchanged, at the resolved rollout snapshot. The
    # change trigger is base's required_layers differing from head's (an
    # earlier, undeclared state widened to `unit` at head) — head's value
    # then exactly matches the rollout snapshot, title held constant.
    base = _manifest({"a::FR-09.20": _node("FR-09.20", layers=())})
    head = _manifest({
        "a::FR-09.20": _node("FR-09.20", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    rollout = _rollout_manifest({"a::FR-09.20": _node("FR-09.20", layers=("unit",))})
    v = evaluate_binding_completeness(base, head, rollout=rollout)
    assert not v.any_fail
    assert v.advisory and v.advisory[0].reason == "BINDING_INCOMPLETE_TRANSITION"


def test_transition_grace_is_source_agnostic_for_a_promoted_binding():
    # External plan review (P3.3 follow-up, glm): the measured motivating population
    # (shipwright-webui's 9 FRs) were PROMOTED inferred_legacy -> explicit around the
    # gate's own rollout day, value unchanged. Grace must not require the rollout
    # snapshot's source to already be "explicit" — only that the VALUE matches.
    base = _manifest({"a::FR-09.21": _node("FR-09.21", layers=(), source="explicit")})
    head = _manifest({
        "a::FR-09.21": _node("FR-09.21", layers=("unit",), source="explicit",
                              coverage={"unit": "ok", "e2e": "ok"}),
    }, spec_hash="sha256:y")
    # Rollout snapshot: same FR, same value, but still `inferred_legacy` at that point
    # (the promotion to `explicit` happened after the resolved rollout commit).
    rollout = _rollout_manifest(
        {"a::FR-09.21": _node("FR-09.21", layers=("unit",), source="inferred_legacy")}
    )
    v = evaluate_binding_completeness(base, head, rollout=rollout)
    assert not v.any_fail
    assert v.advisory and v.advisory[0].reason == "BINDING_INCOMPLETE_TRANSITION"


def test_transition_grace_survives_a_widening_edit_since_rollout():
    # internal plan review (opus): grace must not punish partial improvement harder
    # than inaction — a WIDENING edit (base narrower than head) keeps grace as long
    # as the rollout value is still a subset of head's widened value. The widening
    # from base to head IS the change trigger here — no title force needed.
    base = _manifest({"a::FR-09.22": _node("FR-09.22", layers=("unit",))})
    head = _manifest({
        "a::FR-09.22": _node("FR-09.22", layers=("unit", "integration"),
                              coverage={"unit": "ok", "e2e": "ok"}),
    }, spec_hash="sha256:y")
    rollout = _rollout_manifest({"a::FR-09.22": _node("FR-09.22", layers=("unit",))})
    v = evaluate_binding_completeness(base, head, rollout=rollout)
    assert not v.any_fail
    assert v.advisory and v.advisory[0].reason == "BINDING_INCOMPLETE_TRANSITION"


def test_transition_grace_withheld_when_binding_narrowed_since_rollout():
    # A binding NARROWED since rollout (or replaced with an unrelated value) is
    # judged normally — grace only ever protects a value that already existed.
    # The narrowing from base to head is itself the change trigger.
    base = _manifest({"a::FR-09.23": _node("FR-09.23", layers=("unit", "e2e"))})
    head = _manifest({
        "a::FR-09.23": _node("FR-09.23", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    rollout = _rollout_manifest(
        {"a::FR-09.23": _node("FR-09.23", layers=("unit", "e2e"))}
    )
    v = evaluate_binding_completeness(base, head, rollout=rollout)
    assert v.any_fail and v.hard[0].reason == "BINDING_INCOMPLETE"


def test_transition_grace_withheld_when_rollout_value_was_empty():
    # External code review (P3.3 follow-up, openai, HIGH): an FR that existed at
    # rollout with NO declared required_layers at all must not vacuously satisfy
    # the subset check (the empty set is a subset of everything) — that would grant
    # grace to a binding that is, in substance, brand new. Only a NON-EMPTY
    # pre-existing value counts as "already existed".
    base = _manifest({"a::FR-09.29": _node("FR-09.29", layers=())})
    head = _manifest({
        "a::FR-09.29": _node("FR-09.29", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    rollout = _rollout_manifest({"a::FR-09.29": _node("FR-09.29", layers=())})
    v = evaluate_binding_completeness(base, head, rollout=rollout)
    assert v.any_fail and v.hard[0].reason == "BINDING_INCOMPLETE"


def test_transition_grace_withheld_when_fr_absent_from_rollout_snapshot():
    # A genuinely new FR (minted after rollout) is not in the rollout snapshot at
    # all — no grace, matching the documented no-legacy-valve-for-greenfield case.
    base = _manifest({"a::FR-09.24": _node("FR-09.24", layers=())})
    head = _manifest({
        "a::FR-09.24": _node("FR-09.24", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    v = evaluate_binding_completeness(base, head, rollout=_rollout_manifest({}))
    assert v.any_fail and v.hard[0].reason == "BINDING_INCOMPLETE"


def test_transition_grace_withheld_with_no_rollout_snapshot_at_all():
    # rollout=None (no snapshot resolvable — see _layer_coverage_rollout's own
    # docstring for why that is the safe default) behaves exactly like today,
    # pre-existing behaviour — every test above this one omits `rollout` entirely.
    base = _manifest({"a::FR-09.25": _node("FR-09.25", layers=())})
    head = _manifest({
        "a::FR-09.25": _node("FR-09.25", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    v = evaluate_binding_completeness(base, head, rollout=None)
    assert v.any_fail and v.hard[0].reason == "BINDING_INCOMPLETE"


def test_transition_grace_withheld_when_title_shows_fr_was_repurposed():
    # internal plan review (opus): a manifest key can outlive the requirement it
    # names (a folded/repurposed FR keeping its id). The rollout node's title must
    # match head's — an unrelated predecessor's value must not carry grace forward.
    # Here the title IS the deliberate mismatch under test, so it is also what
    # triggers the behaviour-change signal (base's title differs from head's).
    base = _manifest({"a::FR-09.26": _node("FR-09.26", layers=("unit",), title="original")})
    head = _manifest({
        "a::FR-09.26": _node("FR-09.26", layers=("unit",), title="repurposed",
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    stale = _node("FR-09.26", layers=("unit",), title="an unrelated, since-repurposed requirement")
    v = evaluate_binding_completeness(base, head, rollout=_rollout_manifest({"a::FR-09.26": stale}))
    assert v.any_fail and v.hard[0].reason == "BINDING_INCOMPLETE"


def test_transition_grace_never_applies_to_a_collision_gap():
    # A collision gap is already routed advisory before the transition check is
    # ever reached — `binding_predates_rollout` must not even be consulted, so an
    # ABSENT rollout snapshot (None) must not change a collision's outcome.
    base = _manifest({
        "a::FR-09.27": _node("FR-09.27", layers=()), "b::FR-09.27": _node("FR-09.27"),
    })
    head = _manifest({
        "a::FR-09.27": _node("FR-09.27", layers=("unit",), coverage={"unit": "ok", "e2e": "ok"}),
        "b::FR-09.27": _node("FR-09.27"),
    }, spec_hash="sha256:y")
    v = evaluate_binding_completeness(base, head, rollout=None)
    assert not v.any_fail
    assert v.advisory and v.advisory[0].reason == "ambiguous_fanout"


def test_binding_predates_rollout_pure_helper_matrix():
    head_node = _node("FR-09.28", layers=("unit", "integration"))
    # exact match, source-agnostic
    assert binding_predates_rollout(
        _rollout_manifest({"a::FR-09.28": _node("FR-09.28", layers=("unit", "integration"),
                                                 source="inferred_legacy")}),
        "a::FR-09.28", head_node,
    ) is True
    # widening since rollout: still a superset relationship -> grace
    assert binding_predates_rollout(
        _rollout_manifest({"a::FR-09.28": _node("FR-09.28", layers=("unit",))}),
        "a::FR-09.28", head_node,
    ) is True
    # narrowing since rollout: rollout is NOT a subset of head -> no grace
    narrower_head = _node("FR-09.28", layers=("unit",))
    assert binding_predates_rollout(
        _rollout_manifest({"a::FR-09.28": _node("FR-09.28", layers=("unit", "e2e"))}),
        "a::FR-09.28", narrower_head,
    ) is False
    # rollout's OWN value was empty -> no grace, even though set() <= anything
    assert binding_predates_rollout(
        _rollout_manifest({"a::FR-09.28": _node("FR-09.28", layers=())}),
        "a::FR-09.28", head_node,
    ) is False
    # key absent from rollout snapshot -> no grace
    assert binding_predates_rollout(_rollout_manifest({}), "a::FR-09.28", head_node) is False
    # rollout is None -> no grace
    assert binding_predates_rollout(None, "a::FR-09.28", head_node) is False
    # title mismatch -> no grace even though the layer value would otherwise qualify
    mismatched_title = _rollout_manifest(
        {"a::FR-09.28": _node("FR-09.28", layers=("unit", "integration"), title="unrelated")}
    )
    assert binding_predates_rollout(mismatched_title, "a::FR-09.28", head_node) is False
