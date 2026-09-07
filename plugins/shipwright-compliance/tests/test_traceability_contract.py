"""CONTRACT GATE for the test-traceability manifest -- schema v3/v4 (campaign S3/P3.2).

Pins the WIRE SHAPE and the key form across versions. The fixture repo, the git-baseline
machinery and the constants live in ``traceability_contract_support``; the rationale for
freezing against ``origin/main`` rather than an in-repo pin is documented there.

Companion to ``test_traceability_fixtures.py`` (schema validity) and
``test_test_links_collector.py`` (collector behaviour).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The support half is a sibling test-dir module, and `tests/` is not importable by
# default (the plugin's conftest adds only fixtures). Mirrors the `_HERE.parent` insert
# other tests in this directory already use.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from traceability_contract_support import (
    ARTIFACT,
    CB,
    CE,
    CONSUMER,
    CONTRACTS_DIR,
    FIXTURE_VERSION,
    LOAD_BEARING,
    SCHEMA_VERSION,
    STEM,
    _manifest_for,
    _materialize,
    _REPO_ROOT,
    fixture_path,
    live_contract,
    published_anywhere,
    repo,
    require_baseline_ref,
)

__all__ = ["repo"]  # re-exported pytest fixture


class TestPublishedFixture:
    def test_a_fixture_exists_for_the_declared_version(self):
        assert fixture_path(FIXTURE_VERSION).is_file(), (
            f"schema_version is {SCHEMA_VERSION} but there is no "
            f"{STEM}-{FIXTURE_VERSION}.json. A version the consumer cannot look up "
            "is not a contract."
        )

    def test_the_live_manifest_matches_the_fixture_for_that_version(self, repo: Path):
        pinned = json.loads(fixture_path(FIXTURE_VERSION).read_text(encoding="utf-8"))
        assert pinned["contract"] == live_contract(repo), (
            "The emitted manifest no longer matches the contract fixture for "
            f"schema_version {SCHEMA_VERSION}. Do not 'fix' this by editing the "
            "published fixture — add a new versioned one and bump the version."
        )

    def test_the_fixture_declares_the_version_its_filename_claims(self):
        pinned = json.loads(fixture_path(FIXTURE_VERSION).read_text(encoding="utf-8"))
        assert pinned["schema_version"] == FIXTURE_VERSION

    def test_the_pin_has_no_unpinned_arrays(self, repo: Path):
        # An empty array in the pin says nothing about its elements — a weak pin that
        # would let a nested change through while looking like coverage.
        #
        # One path is STRUCTURALLY empty rather than under-exercised: an FR that trips
        # `invalid_layers` is precisely an FR whose Layers cell resolved to ZERO valid
        # layers, so its `required_layers` cannot be both non-empty and exercise that
        # arm. Its element type is pinned by the sibling nodes, which do carry layers.
        structurally_empty = {"requirements.03::FR-03.02.required_layers"}
        weak = set(CE.empty_array_paths(live_contract(repo)["skeleton"]))
        assert weak <= structurally_empty, (
            f"these arrays pin no element type: {sorted(weak - structurally_empty)}"
        )
        siblings = CE.flatten(live_contract(repo)["skeleton"])
        assert siblings["requirements.03::FR-03.01.required_layers[]"] == "string"




class TestTheGate:
    """The half that cannot be satisfied by editing a file in the same PR."""

    def test_published_fixtures_are_frozen_against_main(self):
        # Driven from what origin/main PUBLISHED, not from a glob over local files: a
        # glob would skip a DELETED fixture and pass vacuously.
        require_baseline_ref()
        for version in CB.published_fixtures(_REPO_ROOT, CONTRACTS_DIR, STEM):
            reason = CB.frozen_fixture_diff(
                _REPO_ROOT, f"{CONTRACTS_DIR}/{STEM}-{version}.json")
            assert reason is None, reason

    def test_the_shape_change_forces_the_bump_it_obliges(self, repo: Path):
        """Enforces the bump SIZE, and refuses to disarm itself quietly.

        Without this, `test_published_fixtures_are_frozen_against_main` is the only gate
        — and it iterates over `published_fixtures`, so renaming CONTRACTS_DIR or STEM
        makes it loop zero times and pass forever. A skipped gate is green."""
        require_baseline_ref()
        baseline = CB.published_baseline(_REPO_ROOT, CONTRACTS_DIR, STEM)
        if baseline is None:
            # "Nothing published yet" is a real state exactly once — the commit that
            # introduces this contract. Afterwards it means someone renamed
            # CONTRACTS_DIR or STEM and silently disarmed the gate.
            stranded = published_anywhere(STEM)
            assert not stranded, (
                f"origin/main publishes {STEM} fixtures at {stranded}, but none under "
                f"{CONTRACTS_DIR}/{STEM}-*.json. The gate is looking in the wrong place "
                "and has disarmed itself — fix the constants, do not skip."
            )
            # Local fixture must exist, or the bootstrap claim is itself unfounded.
            assert fixture_path(FIXTURE_VERSION).is_file()
            pytest.skip("origin/main publishes no traceability contract yet (bootstrap)")  # test-hygiene: allow-silent-skip: bootstrap-only, guarded by the disarm assertions above
        base_version, base_fixture = baseline
        diff = CE.require_bump(
            base_fixture["contract"], live_contract(repo),
            base_version, FIXTURE_VERSION,
            consumer=CONSUMER, artifact=ARTIFACT,
        )
        assert diff is not None

    def test_v4_stays_additive_over_the_frozen_v3_shape(self, repo: Path):
        """AC-3 (P3.2, corrected 2026-09-07): the v4 manifest must stay readable by a
        v3-shaped consumer -- additive nodes only, nothing removed or retyped.

        `test_the_shape_change_forces_the_bump_it_obliges` only proves a bump of
        adequate SIZE happened; `required_bump` returns "major" for a BREAKING diff
        too, so a major-bumped breaking change would satisfy that test as well. This
        pins the narrower, stronger claim against the frozen v3.0 fixture directly --
        not against whatever `origin/main` happens to currently publish -- because the
        promise is about v3 shape survival specifically, not about the immediately
        preceding version.
        """
        v3 = json.loads(fixture_path("3.0").read_text(encoding="utf-8"))
        diff = CE.diff_skeletons(v3["contract"], live_contract(repo))
        assert diff.removed == [], f"v3 fields dropped in v4: {diff.removed}"
        assert diff.retyped == [], f"v3 fields retyped in v4: {diff.retyped}"
        assert not diff.is_breaking


class TestLoadBearingFields:
    def test_every_documented_field_is_on_the_wire(self, repo: Path):
        paths = set(CE.flatten(live_contract(repo)["skeleton"]))
        missing = sorted(LOAD_BEARING - paths)
        assert not missing, (
            "The Command Center WebUI renders these and they are gone: "
            f"{missing}"
        )


class TestKeyFormIsIdDerived:
    """S3's actual claim, pinned at the collector — not asserted in prose."""

    def test_keys_are_group_digits_not_the_split_directory(self, repo: Path):
        keys = sorted(_manifest_for(repo)["requirements"])
        assert keys == ["03::FR-03.01", "03::FR-03.02", "03::FR-03.09"]

    def test_keys_survive_a_split_directory_rename(self, tmp_path: Path):
        """THE point of id-derivation, proven by renaming rather than by assertion.

        Two repos identical but for the directory holding the spec. Under v2 every key
        moved with the directory (``01-adopted::`` -> ``99-renamed::``); under v3 the
        manifests must agree on every key AND on every inner field the WebUI reads."""
        before_root, after_root = tmp_path / "before", tmp_path / "after"
        _materialize(before_root, "01-adopted")
        _materialize(after_root, "99-totally-renamed")
        before, after = _manifest_for(before_root), _manifest_for(after_root)

        # Guard the guard: an empty dict on both sides would satisfy every assertion
        # below while proving nothing at all.
        assert len(before["requirements"]) == 3
        assert list(before["requirements"]) == list(after["requirements"])
        for key, node in before["requirements"].items():
            other = after["requirements"][key]
            for field in ("id", "tests", "title", "status",
                          "required_layers", "required_layers_source"):
                assert node[field] == other[field], f"{key}.{field} moved on a rename"

    def test_spec_path_still_records_where_the_row_was_found(self, tmp_path: Path):
        """The rename must be INVISIBLE in the key and VISIBLE in the provenance —
        otherwise the manifest would have stopped recording where an FR lives."""
        _materialize(tmp_path, "99-totally-renamed")
        node = _manifest_for(tmp_path)["requirements"]["03::FR-03.01"]
        assert node["spec_path"] == ".shipwright/planning/99-totally-renamed/spec.md"


# Identity/integrity tests (duplicate-id refusal, key<->id agreement, tombstone
# ordering) live in test_traceability_contract_integrity.py -- split there purely to
# keep this file under the 300-LOC bloat-baseline threshold after AC-3's additive-shape
# gate test (P3.2) was added, same subject family, not a different one.
