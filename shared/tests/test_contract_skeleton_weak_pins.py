"""A published contract shape that never exercised part of the data.

Split out of ``test_contract_skeleton.py`` to stay under the test-file LOC
budget (req3-05 t9).

@covers FR-01.15/AC05 — "Given the published shape was derived from data
that never exercised part of it — a list that happened to be empty, a value
only ever seen absent — when it is published, then that weakness is stated
rather than passing as a full description." ``null_only_paths`` and
``empty_array_paths`` are what turns that weakness into a reportable,
machine-checkable fact instead of something that silently ships as an
ordinary, fully-observed pin.

**Seam, not scope (external code review, openai, medium):** unlike
FR-01.15/AC02/AC03/AC06 (seam survey Exception 2 — no CLI gate script exists
yet, so a library unit test does NOT prove the whole AC), the seam survey's
own quick-decide table names these two functions themselves as AC05's real
seam ("fixture provenance") — there is no wired "publish" call site to drive
end-to-end yet, and inventing one here would be new production wiring, not
test backfill. Proving the functions directly IS what t0 assigned for this
specific AC; it is a different ruling from AC02/03/06's, not an inconsistency.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.contract_skeleton import empty_array_paths, null_only_paths, skeleton_of  # noqa: E402


class TestNullOnlyPaths:
    """The null twin of the empty-array guard: a leaf no sample ever exercised."""

    @pytest.mark.covers("FR-01.15/AC05")
    def test_a_leaf_seen_only_as_null_is_reported(self):
        assert null_only_paths(skeleton_of({"e2e": None, "unit": {"f": "x"}})) == ["e2e"]

    @pytest.mark.covers("FR-01.15/AC05")
    def test_a_leaf_with_a_real_arm_is_not_reported(self):
        merged = skeleton_of([{"e2e": None}, {"e2e": "playwright"}])[0]
        assert null_only_paths(merged) == []


class TestEmptyArrayPaths:
    """The other half of the same weakness: a list that happened to be empty
    in every sample pins nothing about its element type."""

    @pytest.mark.covers("FR-01.15/AC05")
    def test_an_unobserved_list_element_is_reported_as_weak(self):
        assert empty_array_paths(skeleton_of({"xs": []})) == ["xs"]

    @pytest.mark.covers("FR-01.15/AC05")
    def test_a_populated_list_is_not_reported(self):
        assert empty_array_paths(skeleton_of({"xs": ["a"]})) == []

    @pytest.mark.covers("FR-01.15/AC05")
    def test_a_nested_empty_list_is_found_by_dotted_path(self):
        assert empty_array_paths(skeleton_of({"d": {"xs": []}})) == ["d.xs"]
