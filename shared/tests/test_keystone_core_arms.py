"""P3.6 THE KEYSTONE GATE — the evaluator's FR-scoped arms.

Second half of ``test_keystone_core.py`` (split to keep both modules under the
300-line source limit rather than baselining a brand-new file). Covers AC-K4
(the ADDED-AC arm, deviation 3), AC-K10 (highest-layer-mandatory: reused
ranking + routing, new predicate) and AC-1's two arms plus the
reader-divergence precedence rule.

Fixture builders are shared via ``_keystone_fixtures`` so the two halves cannot
drift into testing different manifest shapes.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)

from _keystone_fixtures import StubChangeSet  # noqa: E402
from _keystone_fixtures import bound as _acs_for  # noqa: E402
from _keystone_fixtures import link as _link  # noqa: E402
from _keystone_fixtures import manifest as _manifest  # noqa: E402
from verifiers import _keystone_core as kc  # noqa: E402  (_keystone_fixtures put tools/ on the path)
from verifiers import _keystone_layer_gap as klg  # noqa: E402
from verifiers import _layer_coverage_binding as lcb  # noqa: E402
from verifiers import _layer_coverage_core as lcc  # noqa: E402


# --------------------------------------------------------------------------
# AC-K10 — highest layer mandatory: ranking + routing reused, predicate new
# --------------------------------------------------------------------------

def test_layer_gap_is_advisory_for_a_legacy_required_layers_source():
    head = _acs_for(
        "FR-01.01", "AC01", [_link("t1", layer="unit")],
        required_layers=("unit", "integration"), source="inferred_legacy",
    )
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert verdict.hard == []
    assert [f.kind for f in verdict.advisory] == [kc.LAYER_GAP]
    assert "integration" in verdict.advisory[0].detail


def test_layer_gap_is_hard_when_required_layers_source_is_explicit():
    head = _acs_for(
        "FR-01.01", "AC01", [_link("t1", layer="unit")],
        required_layers=("unit", "integration"), source="explicit",
    )
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert [f.kind for f in verdict.hard] == [kc.LAYER_GAP]


def test_no_layer_gap_when_the_binding_reaches_the_highest_required_layer():
    head = _manifest(
        "FR-01.01", "AC01",
        {"unit": [_link("t1", layer="unit")],
         "integration": [_link("t2", layer="integration")]},
        required_layers=("unit", "integration"), source="explicit",
    )
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert verdict.hard == []
    assert verdict.advisory == []


def test_layer_ranking_and_routing_come_from_the_shared_helpers_not_local_copies():
    """AC-K10's drift pin. Two gates must not drift on what "higher layer" means
    or on how a gap is routed, and ``evaluate_binding_completeness`` must NOT be
    reached for: it tests the INVERSE direction (evidence outranking the
    declared layers) and would implement the wrong predicate.
    """
    assert klg._LAYER_RANK is lcb._LAYER_RANK
    assert klg.route_gap_severity is lcc.route_gap_severity
    # AST, not a substring scan: the module's own docstrings NAME the function in
    # order to explain why it is the wrong one, so a text search would either
    # fail here or force deleting the explanation. Only real references count.
    tree = ast.parse(Path(klg.__file__).read_text(encoding="utf-8"))
    referenced = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        alias.asname or alias.name
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "evaluate_binding_completeness" not in referenced


# --------------------------------------------------------------------------
# AC-1's two arms + the reader-divergence precedence rule
# --------------------------------------------------------------------------

def test_unminted_changed_criterion_blocks_and_names_the_real_minter_command():
    verdict = kc.evaluate_keystone(
        StubChangeSet(unminted_changed=[("FR-01.01", "the widget must fizz")]),
        _manifest(), _manifest(),
    )
    assert [f.kind for f in verdict.hard] == [kc.UNMINTED_CHANGED]
    detail = verdict.hard[0].detail
    assert "mint_ac_ids.py" in detail and "--write" in detail
    assert "shipwright_ac_registry.json" in detail
    assert "the widget must fizz" in detail


def test_a_new_fr_without_criteria_blocks():
    verdict = kc.evaluate_keystone(
        StubChangeSet(new_frs_without_criteria=["FR-02.01"]), _manifest(), _manifest(),
    )
    assert [f.kind for f in verdict.hard] == [kc.NEW_FR_NO_CRITERIA]


def test_reader_divergence_suppresses_the_new_fr_arm_for_the_same_fr():
    """Both arms fire on a brand-new FR whose bullets follow an intro sentence.
    Arm 2's remedy ("state at least one criterion") is the WRONG advice there —
    the criteria exist, this reader cannot see them — so the divergence finding
    wins and arm 2 stays silent for that FR.
    """
    verdict = kc.evaluate_keystone(
        StubChangeSet(reader_divergence=["FR-02.01"], new_frs_without_criteria=["FR-02.01"]),
        _manifest(), _manifest(),
    )
    assert [f.kind for f in verdict.hard] == [kc.READER_DIVERGENCE]


def test_a_different_new_fr_still_gets_arm_2():
    verdict = kc.evaluate_keystone(
        StubChangeSet(reader_divergence=["FR-02.01"], new_frs_without_criteria=["FR-03.01"]),
        _manifest(), _manifest(),
    )
    assert sorted(f.kind for f in verdict.hard) == [kc.NEW_FR_NO_CRITERIA, kc.READER_DIVERGENCE]


def test_warnings_from_the_change_set_survive_into_the_verdict():
    verdict = kc.evaluate_keystone(
        StubChangeSet(warnings=["base markers unparseable"]), _manifest(), _manifest(),
    )
    assert verdict.warnings == ["base markers unparseable"]


def test_an_inactive_requirement_contributes_no_layer_gap():
    """``_fr_node`` walks ``_active_nodes``, so a retired FR cannot raise a
    layer-gap finding — the same scope every sibling gate has."""
    head = _acs_for(
        "FR-01.01", "AC01", [_link("t1", layer="unit")],
        required_layers=("unit", "e2e"), source="explicit", status="retired",
    )
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert verdict.hard == []
    assert verdict.advisory == []


# --------------------------------------------------------------------------
# AC-K4 — the ADDED-AC arm: report-only when unbound, walked when it is not
# --------------------------------------------------------------------------

def test_added_minted_ac_without_a_binding_is_reported_not_blocked():
    head = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(added={("FR-01.01", "AC09")}), head, head,
    )
    assert verdict.hard == []
    assert verdict.unbound == [("FR-01.01", "AC09")]


def test_a_removed_ac_that_had_a_binding_is_reported_under_its_own_key():
    """External plan review, BOTH reviewers, from opposite directions (glm
    medium: "deleting a minted AC entirely is exit 0"; openai high: "AC identity
    rotation bypasses the greenness check").

    Same root cause: `binding_removed` walks `changed` only, so deleting a
    criterion — or rotating `[AC01] foo` to `[AC55] foo TWICE`, which reads as
    removed+added — discards an AC-to-test obligation in ONE PR. Report-only
    here by deliberate scope call (the remediable predicate is p3.7(b)'s orphan
    detector), but VISIBLE in every PR rather than only in a design document.
    """
    base = _acs_for("FR-01.01", "AC01", [_link("t1")])
    head = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(removed={("FR-01.01", "AC01")}), head, base,
    )
    assert verdict.hard == []
    assert verdict.removed_with_bindings == [("FR-01.01", "AC01")]


def test_a_removed_ac_that_never_had_a_binding_is_not_reported_there():
    """The discriminator: 259 of 268 ACs are unbound today, so reporting every
    deletion would bury the nine that matter."""
    empty = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(removed={("FR-01.01", "AC01")}), empty, empty,
    )
    assert verdict.removed_with_bindings == []


def test_an_id_rotation_is_visible_as_a_removal_with_a_binding_plus_an_add():
    """openai's exact scenario, end to end through the evaluator."""
    base = _acs_for("FR-01.01", "AC01", [_link("t1")])
    head = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(removed={("FR-01.01", "AC01")}, added={("FR-01.01", "AC55")}),
        head, base,
    )
    assert verdict.hard == [], "still not blocking — that is p3.7(b)'s"
    assert verdict.removed_with_bindings == [("FR-01.01", "AC01")]
    assert verdict.unbound == [("FR-01.01", "AC55")]


@pytest.mark.parametrize(("status", "executed", "expected"), [
    ("enabled", "fail", kc.FAILED),
    ("enabled", "not_run", kc.NOT_SELECTED),
    ("disabled", "pass", kc.SKIPPED),
])
def test_added_minted_ac_that_HAS_a_binding_is_greenness_walked(status, executed, expected):
    """**DEVIATION 3** from the ratified design (design §7's third-deviation
    bullet, §8's ruling row, AC-K4). This test REPLACES one that asserted the
    opposite, so read the deviation before "fixing" it back.

    Attribution, corrected after a Stage-1 spec review found the first version of
    this docstring miscited it: **no reviewer asked for this — it was found during
    build.** The external code review's openai-high finding is the Track R / Q2
    scope objection, dispositioned REJECTED in §12.1; the plan review's
    AC-id-rotation finding is dispositioned "reported, not blocked" and still is.

    The design excluded ``added`` from the greenness walk on the stated ground
    that "a new criterion has no binding". That is an assumption, not a property:
    when the new criterion arrives WITH a ``@covers`` tag the premise fails and
    the exclusion has no basis left. Source AC-2 — "a named AC whose bound test
    did not run green blocks" — names a newly added AC too, and unlike a removed
    AC's binding this one is remediable INSIDE the PR.
    """
    head = _acs_for("FR-01.01", "AC09", [_link("t1", status=status, executed=executed)])
    verdict = kc.evaluate_keystone(
        StubChangeSet(added={("FR-01.01", "AC09")}), head, head,
    )
    assert [f.kind for f in verdict.hard] == [expected]
    assert verdict.unbound == []


def test_added_minted_ac_with_a_green_binding_passes():
    head = _acs_for("FR-01.01", "AC09", [_link("t1")])
    verdict = kc.evaluate_keystone(
        StubChangeSet(added={("FR-01.01", "AC09")}), head, head,
    )
    assert verdict.hard == []
    assert verdict.unbound == []


def test_an_added_ac_is_NOT_layer_gap_checked_even_with_explicit_provenance():
    """The SCOPE half of deviation 3, and the half most likely to be "tidied" into
    symmetry with the ``changed`` arm.

    Greenness of a binding that already exists is what AC-2 says. Layer BREADTH
    for a brand-new criterion is *coverage* — p3.7's — and it is the arm that
    would start false-redding the moment p3.5 promotes an FR to ``explicit``: add
    one criterion with a unit test to an FR requiring e2e, and a symmetric
    implementation blocks the PR for work the design never asked for. A deviation
    should be exactly as wide as its justification, so the identical fixture that
    yields a HARD layer gap under ``changed`` must yield NOTHING under ``added``.
    """
    head = _acs_for(
        "FR-01.01", "AC09", [_link("t1", layer="unit")],
        required_layers=("unit", "e2e"), source="explicit",
    )
    changed_verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC09")}), head, head,
    )
    assert [f.kind for f in changed_verdict.hard] == [kc.LAYER_GAP], (
        "fixture must be one the changed arm HARD-blocks, or this proves nothing"
    )

    added_verdict = kc.evaluate_keystone(
        StubChangeSet(added={("FR-01.01", "AC09")}), head, head,
    )
    assert added_verdict.hard == []
    assert added_verdict.advisory == []


def test_an_added_ac_is_never_reported_as_binding_removed():
    """The gate on the walk is ``head_links >= 1``, never a base comparison: an
    added AC has no base side to have been removed from, so a base manifest that
    happens to carry links for the same id must not manufacture a finding."""
    base = _acs_for("FR-01.01", "AC09", [_link("t1")])
    head = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(added={("FR-01.01", "AC09")}), head, base,
    )
    assert verdict.hard == []
    assert verdict.unbound == [("FR-01.01", "AC09")]
