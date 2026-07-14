"""CROSS-REPO CONTRACT GATE — the Command Center WebUI renders this report.

``grade.py --format json`` is ``json.dumps(dataclasses.asdict(model))``, and the WebUI's
"Grade your repo" screen renders that model **field-for-field** so the screen and the
downloadable HTML report cannot tell different stories. A field renamed or dropped here
does not fail loudly over there — it renders a half-empty card, or a plausible-but-wrong
one. Nobody in this repo would otherwise have a reason to know the WebUI is watching.

**Why the baseline is git and not a pin in this file.** A pin is editable in the same
change: rename a field, update the pin, and the diff is empty — the required bump becomes
"none" and any version passes. *Editing the pin erases the evidence.* So the published
fixture is frozen against ``origin/main`` (which a PR cannot rewrite) and the gate derives
the bump the diff obliges from THAT.

The subject it pins, and the loader/baseline machinery, live in ``contract_support``.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from contract_support import (
    ARTIFACT,
    CB,
    CE,
    CONSUMER,
    CONTRACTS_DIR,
    LOAD_BEARING,
    STEM,
    _PLUGIN_ROOT,
    _REPO_ROOT,
    fixture_path,
    live_contract,
    require_baseline_ref,
)
from report_model import SCHEMA_VERSION, STATUS_VOCABULARY
from support import mixed_model


class TestPublishedFixture:
    def test_a_fixture_exists_for_the_declared_version(self):
        assert fixture_path(SCHEMA_VERSION).is_file(), (
            f"report_model.SCHEMA_VERSION is {SCHEMA_VERSION!r} but there is no "
            f"{STEM}-{SCHEMA_VERSION}.json. A version the consumer cannot look up is "
            "not a contract."
        )

    def test_the_live_payload_matches_the_fixture_for_that_version(self):
        pinned = json.loads(fixture_path(SCHEMA_VERSION).read_text(encoding="utf-8"))
        assert pinned["contract"] == live_contract(), (
            "The emitted report no longer matches the contract fixture for "
            f"schema_version {SCHEMA_VERSION}. Do not 'fix' this by editing the "
            "published fixture — add a new versioned one and bump the version."
        )

    def test_the_fixture_declares_the_version_its_filename_claims(self):
        pinned = json.loads(fixture_path(SCHEMA_VERSION).read_text(encoding="utf-8"))
        assert pinned["schema_version"] == SCHEMA_VERSION

    def test_the_pin_has_no_unpinned_arrays(self):
        # An empty array in the pin says nothing about its elements — a weak pin that
        # would let a nested change through while looking like coverage.
        weak = CE.empty_array_paths(live_contract()["skeleton"])
        assert weak == [], f"these arrays pin no element type: {weak}"


class TestTheGate:
    """The half that cannot be satisfied by editing a file in the same PR."""

    def test_published_fixtures_are_frozen_against_main(self):
        # Driven from what origin/main PUBLISHED, not from what the working tree still
        # has: a glob over local files would skip a deleted fixture and pass vacuously.
        require_baseline_ref()
        for version in CB.published_fixtures(_REPO_ROOT, CONTRACTS_DIR, STEM):
            reason = CB.frozen_fixture_diff(
                _REPO_ROOT, f"{CONTRACTS_DIR}/{STEM}-{version}.json")
            assert reason is None, reason

    def test_the_shape_change_forces_the_bump_it_obliges(self):
        require_baseline_ref()
        baseline = CB.published_baseline(_REPO_ROOT, CONTRACTS_DIR, STEM)
        if baseline is None:
            # "Nothing published yet" is a real state exactly once — the commit that
            # introduces the contract. Afterwards it means someone renamed CONTRACTS_DIR
            # or STEM and silently disarmed the gate, because a skipped gate is green.
            assert not CB.any_published_contract(_REPO_ROOT), (
                f"origin/main publishes contract fixtures, but none under "
                f"{CONTRACTS_DIR}/{STEM}-*.json. The gate is looking in the wrong place "
                "and has disarmed itself — fix the constants, do not skip."
            )
            pytest.skip("origin/main publishes no contract yet (bootstrap commit)")
        base_version, base_fixture = baseline
        CB_diff = CE.require_bump(
            base_fixture["contract"], live_contract(),
            base_version, SCHEMA_VERSION,
            consumer=CONSUMER, artifact=ARTIFACT,
        )
        assert CB_diff is not None


class TestLoadBearingFields:
    def test_every_documented_field_is_on_the_wire(self):
        paths = set(CE.flatten(live_contract()["skeleton"]))
        missing = sorted(LOAD_BEARING - paths)
        assert not missing, (
            f"{CONSUMER} renders these and they are gone: {missing}"
        )

    def test_schema_version_reaches_the_json_output(self):
        payload = dataclasses.asdict(mixed_model())
        assert payload["schema_version"] == SCHEMA_VERSION

    def test_an_na_dimension_carries_no_score(self):
        # The consumer must never synthesize a number for absent evidence. If this
        # model ever coerced n/a to 0.0, the WebUI would draw a zero-score bar and
        # blame the user's repo for a gap in OUR evidence.
        payload = dataclasses.asdict(mixed_model())
        na = [d for d in payload["dimensions"] if d["status"] == "n/a"]
        assert na, "fixture must exercise at least one n/a dimension"
        assert all(d["score"] is None for d in na)


def real_dimension_result():
    """The ENGINE's DimensionResult — the class that actually computes ``status``.

    It lives in shipwright-compliance (``scripts/lib/_grade_types.py``) and reaches this
    plugin at runtime through ``engine_bridge``. Imported here by the same mechanism the
    bridge uses, because probing anything else would be probing ourselves.
    """
    from engine_bridge import _compliance_root
    root = _compliance_root()
    if root is None:
        pytest.fail("cannot locate shipwright-compliance — the status probe is blind")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.lib._grade_types import DimensionResult  # type: ignore
    return DimensionResult


class TestStatusVocabulary:
    """`status` is a CLOSED value domain the consumer branches on — and the one break
    the structural skeleton cannot see (a 4th value changes no field name or type).
    """

    def test_the_real_engine_only_ever_emits_the_pinned_vocabulary(self):
        # An EMPIRICAL probe of the real property, not a restatement of the constant.
        # The obvious version of this test drives `support._dim`, which RE-IMPLEMENTS the
        # rule inside the fixture — so it would agree with itself while the engine grew a
        # fourth value and the WebUI's ok|gap|n/a branch broke.
        dimension = real_dimension_result()
        seen = {
            dimension(key="k", label="L", weight=0.1, score=score,
                      anchor="a", detail="d").status
            for score in (None, 0.0, 0.5, 0.89, 0.9, 0.95, 1.0)
        }
        assert seen == set(STATUS_VOCABULARY), (
            "the engine's status domain no longer matches report_model.STATUS_VOCABULARY "
            f"(engine: {sorted(seen)}, pinned: {sorted(STATUS_VOCABULARY)}). The WebUI "
            "branches on these values: a new one breaks its rendering while every field "
            "name and type stays put. Bump the MAJOR and update the consumer."
        )

    def test_live_dimensions_stay_inside_the_vocabulary(self):
        payload = dataclasses.asdict(mixed_model())
        assert {d["status"] for d in payload["dimensions"]} <= set(STATUS_VOCABULARY)


class TestRealCliConformance:
    """Ties the pin to the artifact the consumer ACTUALLY fetches.

    The unit pin is a statement about dataclasses; this is a statement about the bytes
    ``grade.py --format json`` writes. Without it, a custom encoder or a wrapper could
    change the wire shape while every structural test stayed green.
    """

    def test_the_real_cli_conforms_to_the_pin(self, well_run_repo: Path):
        grade_py = _PLUGIN_ROOT / "scripts" / "tools" / "grade.py"
        done = subprocess.run(
            [sys.executable, str(grade_py), str(well_run_repo), "--format", "json"],
            capture_output=True, text=True, check=False, timeout=180,
            cwd=str(_PLUGIN_ROOT),
        )
        if done.returncode != 0:
            pytest.fail(f"grade.py --format json failed:\n{done.stderr[-2000:]}")
        real = json.loads(done.stdout)
        assert real["schema_version"] == SCHEMA_VERSION
        # Values, not just types: the real CLI is in hand here, so check the one closed
        # domain the consumer branches on while we have actual output to look at.
        assert {d["status"] for d in real["dimensions"]} <= set(STATUS_VOCABULARY)

        pinned = CE.flatten(live_contract()["skeleton"])
        actual = CE.flatten(CE.skeleton_of(real))
        # A real repo need not exercise every arm of the pin: it may score every
        # dimension (so `score` is `number` where the pin allows `number|null`), and with
        # network off it emits `network_enrichments: []`. Conformance is therefore the
        # SUBSET direction — every path it emits is pinned, and every type it emits is
        # one the pin allows — not equality.
        for path, token in sorted(actual.items()):
            if token == "array<unpinned>":
                # An empty array is a legitimate instance of a pinned array (nothing
                # left the machine, so there are no enrichments to list).
                assert any(key.startswith(f"{path}[]") for key in pinned), (
                    f"the real CLI emits the array {path!r}, which the contract "
                    "does not pin"
                )
                continue
            assert path in pinned, (
                f"the real CLI emits {path!r}, which the contract does not pin"
            )
            allowed = set(pinned[path].split("|"))
            assert set(token.split("|")) <= allowed, (
                f"{path}: CLI emits {token!r}, contract allows {pinned[path]!r}"
            )
