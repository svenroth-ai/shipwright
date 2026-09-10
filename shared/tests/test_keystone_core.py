"""P3.6 THE KEYSTONE GATE — the pure evaluator's LINK VOCABULARY.

Covers AC-K5, AC-K6, AC-K7, AC-K8 (a/b/c) and AC-K16 of
``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md``. The FR-scoped
arms (AC-K4's added-AC arm, AC-K10's layer gap, AC-1's two arms, the divergence rule) are
in ``test_keystone_core_arms.py``.

No repo, no git, no CLI: the evaluator is pure, so every case is a manifest
fixture and a stub change set. The CLI's own git/IO seams are covered by
``shared/scripts/tools/tests/test_check_keystone_ac_gate.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)

from _keystone_fixtures import StubChangeSet  # noqa: E402
from _keystone_fixtures import bound as _acs_for  # noqa: E402
from _keystone_fixtures import link as _link  # noqa: E402
from _keystone_fixtures import manifest as _manifest  # noqa: E402
from verifiers import _keystone_core as kc  # noqa: E402  (_keystone_fixtures put tools/ on the path)


# --------------------------------------------------------------------------
# AC-K5 / AC-K6 — greenness, and the forall-not-exists rule
# --------------------------------------------------------------------------

def test_all_bound_links_green_passes():
    head = _acs_for("FR-01.01", "AC01", [_link("t1"), _link("t2")])
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert verdict.hard == []
    assert verdict.any_hard is False


def test_a_failing_bound_link_blocks():
    head = _acs_for("FR-01.01", "AC01", [_link("t1", executed="fail")])
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert [f.kind for f in verdict.hard] == [kc.FAILED]
    assert "t1" in verdict.hard[0].detail


def test_one_pass_one_fail_at_the_same_layer_blocks_forall_not_exists():
    """AC-K6 — the §2.4 defect, asserted against the verdict ``_cov_status``
    would give.

    ``_test_links_requirements._cov_status`` is ``any(...)``: with one green and
    one red link at the same layer it reports the layer ``"ok"``. D10 requires
    ALL bound tests, so this evaluator must block. Pinned by *computing* the
    ``any``-verdict here — a future "simplification" back to
    ``coverage[layer] == "ok"`` then fails loudly instead of quietly passing.
    """
    links = [_link("t_green"), _link("t_red", executed="fail")]
    head = _acs_for("FR-01.01", "AC01", links)
    any_verdict_would_be_ok = any(
        x["status"] == "enabled" and x["executed"] == "pass" for x in links
    )
    assert any_verdict_would_be_ok, "fixture must be one the exists-rule accepts"
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert [f.kind for f in verdict.hard] == [kc.FAILED]


# --------------------------------------------------------------------------
# AC-K7 — skipped / not_selected, and the node-id-space trap
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("status", "executed", "expected"), [
    ("disabled", "pass", kc.SKIPPED),
    ("quarantined", "not_run", kc.SKIPPED),
    ("enabled", "not_run", kc.NOT_SELECTED),
])
def test_non_green_outcomes_carry_distinct_reason_codes(status, executed, expected):
    head = _acs_for("FR-01.01", "AC01", [_link("t1", status=status, executed=executed)])
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert [f.kind for f in verdict.hard] == [expected]


def test_a_disabled_and_failing_link_reports_skipped_not_failed():
    """No reviewer asked for this — found during build (same honesty rule as
    deviation 3). Outcome PRECEDENCE, pinned because it is operator-facing. A
    disabled test's ``executed`` is stale by construction, so reporting
    ``failed`` ("fix the code") sends the author to debug a result nothing
    produced this run. Status first; the actionable fact is the disabling.
    """
    head = _acs_for("FR-01.01", "AC01", [_link("t1", status="disabled", executed="fail")])
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert [f.kind for f in verdict.hard] == [kc.SKIPPED]


def test_a_retired_duplicate_requirement_contributes_no_links():
    """No reviewer asked for this — found during build (NOT the same as the
    separate glm-low finding at §7 about retiring an FR while editing its
    criterion). The asymmetry was fail-OPEN: ``_links_for`` pooled every node
    carrying the display id, retired ones included, while the layer-gap arm
    restricted to active nodes. A retired duplicate silently ADDS to the head
    count — which is precisely what turns a `base >= 1, head 0`
    ``binding_removed`` into an ordinary greenness walk.
    """
    base = _acs_for("FR-01.01", "AC01", [_link("t1")])
    head = _manifest(acs_node={})
    head["requirements"]["ns::FR-01.01__old"] = {
        "id": "FR-01.01", "status": "retired",
        "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
        "acs": {"AC01": {"tests": {"unit": [_link("stale")]}}},
    }
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, base,
    )
    assert [f.kind for f in verdict.hard] == [kc.BINDING_REMOVED]


def test_class_nested_test_id_is_judged_by_executed_never_by_node_id_matching():
    """AC-K7's second half. A bound test living in a class has a pytest node id
    of ``…py::TestX::test_y`` while the manifest link may carry ``…py::test_y``.
    Six of seven "absent from CI" hits in the design's own §2.3 probe were this
    namespace mismatch, not real gaps — so the verdict must come from the
    manifest's ``executed`` field alone.
    """
    head = _acs_for(
        "FR-01.01", "AC01",
        [_link("shared/tests/test_e5.py::test_env_scaffold", executed="pass")],
    )
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, head,
    )
    assert verdict.hard == []


# --------------------------------------------------------------------------
# AC-K8 — ONE vocabulary: link counts, never node presence
# --------------------------------------------------------------------------

def test_unbound_at_both_sides_is_report_only():
    """AC-K8 — ``base_links == 0 and head_links == 0`` → exit 0, and the AC is
    handed to p3.7 through the ``unbound`` list."""
    empty = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), empty, empty,
    )
    assert verdict.hard == []
    assert verdict.unbound == [("FR-01.01", "AC01")]


def test_binding_removed_when_base_had_links_and_head_has_none():
    """AC-K8(a) / AC-K14 — the round-1 dodge: edit the criterion AND drop the
    ``/ACnn`` suffix from its ``@covers`` tag in the same PR."""
    base = _acs_for("FR-01.01", "AC01", [_link("t1")])
    head = _manifest(acs_node={})
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, base,
    )
    assert [f.kind for f in verdict.hard] == [kc.BINDING_REMOVED]
    assert "@pytest.mark.covers" in verdict.hard[0].detail


def test_head_node_present_with_empty_tests_map_is_still_binding_removed():
    """AC-K8(b) — THE input on which the node vocabulary and the link vocabulary
    disagreed.

    Head HAS an ``acs["AC01"]`` node, so a node-presence reading calls head
    "yes": neither ``binding_removed`` (needs head-no) nor ``unbound`` (needs
    base-no), so it falls through to the greenness walk, whose ∀-over-empty is
    vacuously true → a green verdict for an AC whose binding just vanished.
    Written to FAIL against that phrasing.
    """
    base = _acs_for("FR-01.01", "AC01", [_link("t1")])
    head = _manifest(acs_node={"AC01": {"tests": {}}})
    assert "AC01" in head["requirements"]["ns::FR-01.01"]["acs"], "node IS present at head"
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, base,
    )
    assert [f.kind for f in verdict.hard] == [kc.BINDING_REMOVED]
    assert verdict.unbound == []


def test_a_partial_binding_reduction_on_a_changed_ac_is_also_binding_removed():
    """Stage-3 doubt review, high: the original rule tested EMPTINESS of
    ``head_links``, never counts. Dropping one of several ``@covers`` tags on a
    fat AC (base has 2 links, head has 1) used to fall through to the ordinary
    greenness walk over the survivor -- silently discharging the obligation for
    the changed criterion with tests that were never about it. Written to FAIL
    against that phrasing: the surviving link is green, so a walk-only
    evaluator would report this PR clean."""
    base = _acs_for("FR-01.01", "AC01", [_link("t1"), _link("t2")])
    head = _acs_for("FR-01.01", "AC01", [_link("t1")])  # t2's @covers tag dropped
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, base,
    )
    assert [f.kind for f in verdict.hard] == [kc.BINDING_REMOVED]
    assert "2 link(s) at base, 1 at head" in verdict.hard[0].detail


def test_newly_bound_ac_takes_the_ordinary_greenness_walk_not_unbound():
    """AC-K8(c) — ``base_links == 0, head_links >= 1``."""
    base = _manifest(acs_node={})
    head = _acs_for("FR-01.01", "AC01", [_link("t1", executed="fail")])
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, base,
    )
    assert [f.kind for f in verdict.hard] == [kc.FAILED]
    assert verdict.unbound == []


def test_a_v3_era_manifest_without_an_acs_node_reads_as_zero_links():
    base = _manifest(acs_node=None)
    head = _manifest(acs_node=None)
    verdict = kc.evaluate_keystone(
        StubChangeSet(changed={("FR-01.01", "AC01")}), head, base,
    )
    assert verdict.hard == []
    assert verdict.unbound == [("FR-01.01", "AC01")]


# --------------------------------------------------------------------------
# AC-K16 — the forall-over-empty guard
# --------------------------------------------------------------------------

def test_the_greenness_walk_raises_on_an_empty_link_set():
    with pytest.raises(kc.EmptyLinkWalk):
        kc._walk_links([], "FR-01.01", "AC01")


def test_no_evaluate_keystone_path_can_reach_the_empty_walk():
    """The companion half of AC-K16: the raise is a bug tripwire, not a verdict,
    so no input may reach it. Drives every zero-link shape through the public
    entry point and asserts none raises."""
    empty_variants = [
        _manifest(acs_node=None),                       # no acs map at all
        _manifest(acs_node={}),                         # acs map, no such AC
        _manifest(acs_node={"AC01": {}}),               # AC node, no tests key
        _manifest(acs_node={"AC01": {"tests": {}}}),    # tests map, empty
        _manifest(acs_node={"AC01": {"tests": {"unit": []}}}),  # layer, no links
    ]
    for head in empty_variants:
        change_set = StubChangeSet(
            changed={("FR-01.01", "AC01")}, added={("FR-01.01", "AC02")},
        )
        kc.evaluate_keystone(change_set, head, head)  # must not raise
