"""Tests for contract_skeleton — the cross-repo output-contract engine.

The engine backs the per-producer contract gates (shipwright-grade's ReportModel
JSON, shipwright-adopt's snapshot.json). Its whole job is to make a shape change
impossible to ship without the version bump it implies, so these tests pin the
classification and the bump algebra rather than any one producer's fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.contract_skeleton import (  # noqa: E402
    KIND,
    ContractViolation,
    bump_performed,
    diff_skeletons,
    flatten,
    null_only_paths,
    require_bump,
    required_bump,
    skeleton_of,
)


class TestSkeletonOf:
    """The skeleton is the JSON *wire* shape — the thing the consumer parses."""

    def test_scalars_collapse_to_json_types(self):
        assert skeleton_of({"a": "x", "b": 1, "c": 1.5, "d": True, "e": None}) == {
            "a": "string", "b": "number", "c": "number",
            "d": "boolean", "e": "null",
        }

    def test_int_and_float_are_one_number_type(self):
        # JSON (and the JS consumer) have ONE number type. Pinning Python's
        # int/float split would fire a false "retype" on a 1 -> 1.0 change that
        # no consumer can even observe.
        assert skeleton_of({"n": 1}) == skeleton_of({"n": 1.0})

    def test_bool_is_not_a_number(self):
        # bool is a subclass of int in Python — a naive isinstance check would
        # silently type booleans as numbers.
        assert skeleton_of({"b": True}) != skeleton_of({"b": 1})

    def test_tuples_serialize_as_arrays(self):
        # dataclasses.asdict keeps tuples; json.dumps writes them as arrays. The
        # skeleton must describe what lands on the wire, not what Python held.
        assert skeleton_of({"t": ("a", "b")}) == skeleton_of({"t": ["a", "b"]})

    def test_nested_structures_recurse(self):
        payload = {"dimensions": [{"key": "sec", "score": 0.5}]}
        assert skeleton_of(payload) == {
            "dimensions": [{"key": "string", "score": "number"}]
        }

    def test_list_elements_merge_into_a_union(self):
        # A scored dimension and an n/a dimension in the same list must yield
        # score: number|null — otherwise the fixture over-constrains to whichever
        # element happened to come first.
        payload = {"dims": [{"score": 0.5}, {"score": None}]}
        assert skeleton_of(payload) == {"dims": [{"score": "number|null"}]}

    def test_union_parts_are_sorted_for_determinism(self):
        a = skeleton_of({"d": [{"s": None}, {"s": 1}]})
        b = skeleton_of({"d": [{"s": 1}, {"s": None}]})
        assert a == b == {"d": [{"s": "number|null"}]}

    def test_list_elements_with_differing_keys_union_their_keys(self):
        payload = {"d": [{"a": 1}, {"b": "x"}]}
        assert skeleton_of(payload) == {"d": [{"a": "number", "b": "string"}]}

    def test_empty_list_is_an_unknown_element_type(self):
        assert skeleton_of({"xs": []}) == {"xs": []}

    def test_an_optional_object_keeps_its_shape_and_records_the_null_arm(self):
        # A field that is null in one sample and an object in another (adopt's
        # test_frameworks.unit: absent in a bare repo, populated in a real one) must KEEP
        # the object's shape — collapsing it to "null|object" would erase the pin on
        # everything inside — AND record that it can arrive null, because the consumer
        # indexes into it.
        payload = {"d": [{"unit": None}, {"unit": {"framework": "vitest"}}]}
        assert skeleton_of(payload) == {
            "d": [{"unit": {KIND: "object|null", "framework": "string"}}]
        }

    def test_a_nullable_object_is_flattened_as_its_own_retypeable_leaf(self):
        skeleton = skeleton_of({"d": [{"unit": None}, {"unit": {"f": "x"}}]})
        leaves = flatten(skeleton)
        assert leaves["d[].unit"] == "object|null"
        assert leaves["d[].unit.f"] == "string"

    def test_a_non_nullable_object_flattens_as_a_plain_object_leaf(self):
        assert flatten(skeleton_of({"unit": {"f": "x"}}))["unit"] == "object"


class TestDiffAndRequiredBump:
    BASE = {"grade": "string", "dims": [{"key": "string", "score": "number|null"}]}

    def test_identical_shape_requires_no_bump(self):
        d = diff_skeletons(self.BASE, dict(self.BASE))
        assert (d.added, d.removed, d.retyped) == ([], [], [])
        assert required_bump(d) == "none"

    def test_added_field_is_additive_and_requires_minor(self):
        live = {**self.BASE, "schema_version": "string"}
        d = diff_skeletons(self.BASE, live)
        assert d.added == ["schema_version"]
        assert not d.removed and not d.retyped
        assert required_bump(d) == "minor"

    def test_removed_field_is_breaking_and_requires_major(self):
        live = {"dims": self.BASE["dims"]}
        d = diff_skeletons(self.BASE, live)
        assert d.removed == ["grade"]
        assert required_bump(d) == "major"

    def test_retyped_field_is_breaking_and_requires_major(self):
        live = {**self.BASE, "grade": "number"}
        d = diff_skeletons(self.BASE, live)
        assert d.retyped == ["grade"]
        assert required_bump(d) == "major"

    def test_a_rename_reads_as_a_removal_plus_an_addition_and_is_breaking(self):
        live = {"verdict": "string", "dims": self.BASE["dims"]}
        d = diff_skeletons(self.BASE, live)
        assert d.removed == ["grade"] and d.added == ["verdict"]
        assert required_bump(d) == "major"

    def test_nested_change_is_seen_through_a_list(self):
        # The failure both external reviewers flagged: a top-level-only pin would
        # call this "unchanged" while the consumer's per-row render breaks.
        live = {"grade": "string", "dims": [{"key": "string", "score": "string"}]}
        d = diff_skeletons(self.BASE, live)
        assert d.retyped == ["dims[].score"]
        assert required_bump(d) == "major"

    def test_a_dropped_nested_field_is_breaking(self):
        live = {"grade": "string", "dims": [{"key": "string"}]}
        d = diff_skeletons(self.BASE, live)
        assert d.removed == ["dims[].score"]
        assert required_bump(d) == "major"

    def test_breaking_wins_over_additive_when_both_are_present(self):
        live = {"dims": self.BASE["dims"], "extra": "string"}
        d = diff_skeletons(self.BASE, live)
        assert d.added and d.removed
        assert required_bump(d) == "major"


class TestBumpPerformed:
    def test_same_version_is_no_bump(self):
        assert bump_performed("1.0", "1.0") == "none"

    def test_minor_advance(self):
        assert bump_performed("1.0", "1.1") == "minor"

    def test_major_advance(self):
        assert bump_performed("1.4", "2.0") == "major"

    def test_versions_compare_numerically_not_lexically(self):
        # "1.10" < "1.2" as strings — a string compare would call this a regression.
        assert bump_performed("1.2", "1.10") == "minor"

    def test_a_regression_is_rejected(self):
        with pytest.raises(ContractViolation, match="regress"):
            bump_performed("2.0", "1.0")

    def test_a_malformed_version_is_rejected(self):
        with pytest.raises(ContractViolation, match="major.minor"):
            bump_performed("1.0", "v2")


class TestRequireBump:
    """The gate itself: the bump the diff demands must actually have happened."""

    BASE = {"grade": "string"}

    def test_unchanged_shape_and_unchanged_version_passes(self):
        require_bump(self.BASE, dict(self.BASE), "1.0", "1.0", consumer="WebUI")

    def test_breaking_change_without_a_bump_fails(self):
        live = {"verdict": "string"}
        with pytest.raises(ContractViolation) as exc:
            require_bump(self.BASE, live, "1.0", "1.0", consumer="WebUI")
        msg = str(exc.value)
        assert "major" in msg and "WebUI" in msg
        assert "grade" in msg and "verdict" in msg

    def test_breaking_change_with_only_a_minor_bump_fails(self):
        # The bug the whole design exists to prevent: the shape broke, the version
        # moved just enough to look diligent, and the consumer trusts the major.
        live = {"verdict": "string"}
        with pytest.raises(ContractViolation, match="major"):
            require_bump(self.BASE, live, "1.0", "1.1", consumer="WebUI")

    def test_breaking_change_with_a_major_bump_passes(self):
        live = {"verdict": "string"}
        require_bump(self.BASE, live, "1.0", "2.0", consumer="WebUI")

    def test_additive_change_without_a_bump_fails(self):
        live = {**self.BASE, "extra": "string"}
        with pytest.raises(ContractViolation, match="minor"):
            require_bump(self.BASE, live, "1.0", "1.0", consumer="WebUI")

    def test_additive_change_with_a_minor_bump_passes(self):
        live = {**self.BASE, "extra": "string"}
        require_bump(self.BASE, live, "1.0", "1.1", consumer="WebUI")

    def test_additive_change_may_be_bundled_into_a_major_release(self):
        # performed >= required, not equality: an additive field riding along in an
        # already-breaking release must not fail the gate.
        live = {**self.BASE, "extra": "string"}
        require_bump(self.BASE, live, "1.0", "2.0", consumer="WebUI")

    def test_unchanged_shape_may_take_a_deliberate_major_bump(self):
        # The escape hatch for a SEMANTIC break with an identical field graph — e.g.
        # DimensionView.status growing a 4th value beyond ok|gap|n/a. The gate is
        # structurally blind to that, so the manual bump must stay available.
        require_bump(self.BASE, dict(self.BASE), "1.0", "2.0", consumer="WebUI")


class TestNullabilityIsBreaking:
    """A container that BECOMES nullable adds no field — but the consumer indexes it.

    This is the hole a field-graph-only diff leaves wide open: `test_frameworks.unit`
    goes from always-an-object to sometimes-null, the key set is unchanged, the naive
    diff says "no change", the version stands, and the WebUI is told "keep rendering"
    right before it dereferences null. It must read as a RETYPE ⇒ major.
    """

    def test_an_object_gaining_a_null_arm_demands_a_major(self):
        base = skeleton_of({"unit": {"framework": "vitest"}})
        live = skeleton_of([{"unit": None}, {"unit": {"framework": "vitest"}}])[0]

        diff = diff_skeletons(base, live)

        assert diff.retyped == ["unit"], "the nullable object must retype, not vanish"
        assert required_bump(diff) == "major"

    def test_an_object_losing_its_null_arm_also_demands_a_major_conservatively(self):
        # NARROWING nullability (object|null -> object) cannot actually break a consumer
        # that already null-checks, so a perfectly precise gate would call this additive.
        # This one reads it as a retype and demands a major anyway. That is a deliberate
        # over-approximation, recorded here rather than dressed up: it fails SAFE (the
        # consumer refuses to render until it is updated), and teaching the algebra
        # subset-aware union comparison would buy precision in a case that is rare, at
        # the cost of the one property that makes this gate trustworthy — that it is
        # simple enough to be obviously right.
        base = skeleton_of([{"unit": None}, {"unit": {"f": "x"}}])[0]
        live = skeleton_of({"unit": {"f": "x"}})

        assert required_bump(diff_skeletons(base, live)) == "major"

    def test_the_gate_rejects_a_newly_nullable_object_without_a_major(self):
        base = skeleton_of({"unit": {"framework": "vitest"}})
        live = skeleton_of([{"unit": None}, {"unit": {"framework": "vitest"}}])[0]
        with pytest.raises(ContractViolation, match="major"):
            require_bump(base, live, "1.0", "1.1", consumer="WebUI")
        require_bump(base, live, "1.0", "2.0", consumer="WebUI")

    def test_an_array_gaining_a_null_arm_is_breaking(self):
        # A nullable ARRAY degrades to a scalar union token, so the element leaves are
        # removed. Loses the element pin, but it fails SAFE — breaking, not silent.
        base = skeleton_of({"tags": ["a"]})
        live = skeleton_of([{"tags": None}, {"tags": ["a"]}])[0]
        assert required_bump(diff_skeletons(base, live)) == "major"


class TestNullOnlyPaths:
    """The null twin of the empty-array guard: a leaf no sample ever exercised."""

    def test_a_leaf_seen_only_as_null_is_reported(self):
        assert null_only_paths(skeleton_of({"e2e": None, "unit": {"f": "x"}})) == ["e2e"]

    def test_a_leaf_with_a_real_arm_is_not_reported(self):
        merged = skeleton_of([{"e2e": None}, {"e2e": "playwright"}])[0]
        assert null_only_paths(merged) == []
