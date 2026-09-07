"""Pure-evaluator cases for the binding-completeness F11 gate (P3.3): a
behaviour-changed FR's declared binding must name the highest layer this run's
own evidence proves executed-passing — "a binding that names only unit tests is
rejected when a higher layer exists". Split from ``test_layer_coverage_core.py``
(same file-size precedent that module documents for itself) — this gate's pure
evaluator lives in its own sibling module (:mod:`_layer_coverage_binding`).

The CheckResult wrapper (``check_binding_completeness``/``_binding_result``) and
its ``run_all_checks`` wiring live in the sibling
``test_layer_coverage_binding_wrapper.py`` — split out when this file crossed
the 300-LOC guideline (external code review test additions), same precedent
p3.2 already set for ``test_traceability_contract*.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import tools.verifiers._layer_coverage_binding as _lcb_core  # noqa: E402
from tools.verifiers._layer_coverage_binding import (  # noqa: E402
    _highest_ok_layer,
    evaluate_binding_completeness,
)
from tools.verifiers._layer_coverage_core import route_gap_severity  # noqa: E402


def _node(disp, *, status="active", layers=("unit",), source="explicit",
          coverage=None, priority="Must"):
    return {
        "id": disp, "spec_path": "", "title": f"t-{disp}", "priority": priority,
        "status": status, "required_layers": list(layers),
        "required_layers_source": source, "tests": {}, "coverage": coverage or {},
    }


def _manifest(nodes: dict, *, spec_hash="sha256:x"):
    return {
        "schema_version": 3, "spec_hash": spec_hash, "requirements": nodes,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }


def test_highest_ok_layer_ranks_e2e_over_integration_over_unit():
    assert _highest_ok_layer({"unit": "ok", "integration": "ok", "e2e": "MISSING"}) == "integration"
    assert _highest_ok_layer({"unit": "ok", "e2e": "ok"}) == "e2e"
    assert _highest_ok_layer({"unit": "MISSING"}) is None
    assert _highest_ok_layer({}) is None


def test_binding_naming_only_unit_is_rejected_when_integration_passes():
    # The literal AC: a binding that names only unit is rejected once a higher
    # layer (integration) has executed-passing evidence for the SAME requirement.
    base = _manifest({"a::FR-09.01": _node("FR-09.01", layers=("unit",))})
    head = _manifest({
        "a::FR-09.01": _node("FR-09.01", layers=("unit",),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.01"]["title"] = "changed"  # force behaviour change
    v = evaluate_binding_completeness(base, head)
    assert v.any_fail
    assert v.hard[0].display == "FR-09.01" and v.hard[0].layer == "integration"


def test_binding_naming_the_highest_layer_already_is_clean():
    base = _manifest({"a::FR-09.02": _node("FR-09.02", layers=("unit", "e2e"))})
    head = _manifest({
        "a::FR-09.02": _node("FR-09.02", layers=("unit", "e2e"),
                              coverage={"unit": "ok", "e2e": "ok"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.02"]["title"] = "changed"
    v = evaluate_binding_completeness(base, head)
    assert not v.any_fail and not v.advisory


def test_binding_gap_on_legacy_provenance_is_advisory_not_hard():
    base = _manifest({"a::FR-09.03": _node("FR-09.03", source="inferred_legacy")})
    head = _manifest({
        "a::FR-09.03": _node("FR-09.03", source="inferred_legacy",
                              coverage={"unit": "ok", "e2e": "ok"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.03"]["title"] = "changed"
    v = evaluate_binding_completeness(base, head)
    assert not v.any_fail and v.advisory  # pre-rollout legacy valve, same as cross-layer


def test_binding_gap_on_collision_id_is_advisory():
    base = _manifest({
        "a::FR-09.04": _node("FR-09.04"), "b::FR-09.04": _node("FR-09.04"),
    })
    head = _manifest({
        "a::FR-09.04": _node("FR-09.04", coverage={"unit": "ok", "e2e": "ok"}),
        "b::FR-09.04": _node("FR-09.04"),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.04"]["title"] = "changed"
    v = evaluate_binding_completeness(base, head)
    assert not v.any_fail and v.advisory


def test_no_gap_without_a_behaviour_change():
    # An FR with a real evidence/binding gap but NO row/AC delta must not fire —
    # this gate shares the exact behaviour-change trigger as evaluate_cross_layer.
    node = _node("FR-09.05", coverage={"unit": "ok", "e2e": "ok"})
    base = _manifest({"a::FR-09.05": node})
    head = _manifest({"a::FR-09.05": dict(node)})  # identical — no change
    v = evaluate_binding_completeness(base, head)
    assert not v.changed_keys and not v.any_fail and not v.advisory


def test_no_gap_when_no_layer_has_executed_passing_evidence():
    base = _manifest({"a::FR-09.06": _node("FR-09.06")})
    head = _manifest({
        "a::FR-09.06": _node("FR-09.06", coverage={"unit": "MISSING"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.06"]["title"] = "changed"
    v = evaluate_binding_completeness(base, head)
    assert not v.any_fail and not v.advisory  # nothing to judge yet — cross-layer gate owns this


def test_severity_routing_is_the_shared_function_not_a_mirror():
    # External plan review (P3.3, glm): a copy of evaluate_cross_layer's severity
    # table would drift from the original silently. Pin that BOTH gates route
    # through the ONE shared function, on every (ambiguous, source) combination.
    assert route_gap_severity(ambiguous=True, source="explicit") == "advisory"
    assert route_gap_severity(ambiguous=False, source="inferred_legacy") == "advisory"
    assert route_gap_severity(ambiguous=False, source="defaulted_legacy") == "advisory"
    assert route_gap_severity(ambiguous=False, source="explicit") == "hard"
    assert route_gap_severity(ambiguous=False, source="__missing__") == "hard"


def test_binding_multiple_required_layers_credits_the_highest_named():
    # required=[unit, e2e]; evidence only at integration (ranked BETWEEN the two
    # named layers) — e2e already covers it, so no gap (external review, openai).
    base = _manifest({"a::FR-09.07": _node("FR-09.07", layers=("unit", "e2e"))})
    head = _manifest({
        "a::FR-09.07": _node("FR-09.07", layers=("unit", "e2e"),
                              coverage={"unit": "ok", "integration": "ok"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.07"]["title"] = "changed"
    v = evaluate_binding_completeness(base, head)
    assert not v.any_fail and not v.advisory


def test_binding_declared_higher_than_any_evidence_is_clean():
    # required=[e2e], evidence only at unit — the binding already asks for MORE
    # than the run proved; nothing to reject (external review, openai). Whether a
    # DECLARED-but-unproven higher layer should itself be flagged is the sibling
    # `evaluate_cross_layer` gate's job (it already fails a required layer with no
    # executed-passing evidence) — division of labor re-affirmed at code-review
    # (finding #2, rejected-with-reason: see the ADR's External-Code-Review table).
    base = _manifest({"a::FR-09.08": _node("FR-09.08", layers=("e2e",))})
    head = _manifest({
        "a::FR-09.08": _node("FR-09.08", layers=("e2e",), coverage={"unit": "ok"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-09.08"]["title"] = "changed"
    v = evaluate_binding_completeness(base, head)
    assert not v.any_fail and not v.advisory


def test_highest_ok_layer_ranks_an_unrecognised_layer_label_below_every_canonical_one():
    # Defense-in-depth: `coverage` keys are always a subset of the canonical
    # `_LAYER_ORDER` by construction (`build_requirement_nodes`), so this case is
    # unreachable from a real manifest — but the ranking helper must not crash or
    # mis-rank an unrecognised label if one ever leaked through (external review,
    # glm). A real canonical layer ("unit", rank 0) always outranks it (-1):
    assert _highest_ok_layer({"unit": "ok", "manual": "ok"}) == "unit"
    # With no canonical layer present at all, the unrecognised one is all there is:
    assert _highest_ok_layer({"manual": "ok"}) == "manual"


def test_defensive_guard_skips_a_changed_key_missing_from_head_active(monkeypatch):
    # Mirrors evaluate_cross_layer's own unreachable-by-construction defensive line
    # (both `behavior_changed_keys`/`criteria_changed_keys` already filter to head's
    # active nodes) — proven here by forcing a `changed` key head_active does not have.
    base = _manifest({})
    head = _manifest({})
    monkeypatch.setattr(_lcb_core, "behavior_changed_keys", lambda b, h: ["ghost::FR-00.00"])
    monkeypatch.setattr(_lcb_core, "criteria_changed_keys", lambda h, ids: [])
    v = evaluate_binding_completeness(base, head)
    assert v.changed_keys == ["ghost::FR-00.00"]
    assert not v.any_fail and not v.advisory
