"""Identity/integrity half of the test-traceability contract gate.

Split out of ``test_traceability_contract.py`` purely to keep that file under the
300-LOC bloat-baseline threshold once P3.2's additive-shape gate test (AC-3, PR #686)
was added -- same subject family (S3's key-derivation and duplicate-id refusal rules),
not a different one. The wire-shape/version gate (``TestPublishedFixture``,
``TestTheGate``, ``TestLoadBearingFields``, ``TestKeyFormIsIdDerived``) stays in the
original file; everything below pins the id<->key relationship and its failure modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scripts.lib.collectors._test_links_requirements import (
    DuplicateRequirementId,
    KeyNotDerivedFromId,
    ManifestIntegrityError,
    assert_keys_derive_from_ids,
    build_requirement_index,
)
from traceability_contract_support import _manifest_for, _materialize, _SPEC, _TEST


class TestDuplicateIdsFailClosed:
    """A v3 key is a pure function of the id, so two specs CAN claim one key. Resolving
    that by keeping either node would silently delete a requirement from the artifact
    whose job is to reveal traceability gaps, so generation refuses instead."""

    def test_two_specs_claiming_one_id_raise_and_name_both(self, tmp_path: Path):
        _materialize(tmp_path, "01-a")
        second = tmp_path / ".shipwright" / "planning" / "02-b" / "spec.md"
        second.parent.mkdir(parents=True, exist_ok=True)
        second.write_text(_SPEC, encoding="utf-8")
        with pytest.raises(DuplicateRequirementId) as excinfo:
            _manifest_for(tmp_path)
        message = str(excinfo.value)
        assert "FR-03.01" in message
        # Actionable or it is not a usable error: it must name BOTH contributing specs.
        assert "01-a" in message and "02-b" in message

    def test_two_rows_in_ONE_spec_sharing_an_id_also_raise(self, tmp_path: Path):
        """v2 collapsed this silently too (same namespace ⇒ same key), so v3 is not
        inventing a failure here — it is making an already-silent loss visible."""
        spec = tmp_path / ".shipwright" / "planning" / "01-a" / "spec.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(_SPEC.replace("| FR-03.02 | Reporting rollup | Should | int, db |",
                                      "| FR-03.01 | Duplicated row | Should | unit |"),
                        encoding="utf-8")
        (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
        (tmp_path / "tests" / "test_auth.py").write_text(_TEST, encoding="utf-8")
        with pytest.raises(DuplicateRequirementId):
            _manifest_for(tmp_path)


class TestKeyAgreesWithItsNodeId:
    """The schema pins the key SHAPE; only this pins that the two halves AGREE."""

    def test_a_numerically_named_directory_cannot_smuggle_a_path_namespace(self):
        """The regex alone would wave ``02::FR-03.01`` through — a repo whose split
        directories are numbered (``02/``) is exactly where a reintroduced path-derived
        namespace would look plausible and pass shape validation."""
        manifest = {"requirements": {"02::FR-03.01": {"id": "FR-03.01"}}}
        with pytest.raises(KeyNotDerivedFromId, match="disagrees with its node id"):
            assert_keys_derive_from_ids(manifest)

    def test_an_id_derived_key_passes(self):
        assert_keys_derive_from_ids(
            {"requirements": {"03::FR-03.01": {"id": "FR-03.01"}}})


class TestIntegrityErrorsReachTheOperator:
    """Both integrity errors must NOT be ValueErrors.

    `_layer_coverage_regen` regenerates a base+head manifest inside
    `except (OSError, ValueError)` and degrades to None, which the removal / cross-layer
    verifiers render as the fixed string "git unavailable / no base ref / collector
    unavailable". A ValueError subclass is therefore swallowed and reported as an
    INFRASTRUCTURE fault -- sending an operator to check git, the base ref and the
    collector while the real cause is a duplicate FR id in their own spec. Subclassing
    Exception lets it reach the outer `except Exception`, which names the type."""

    def test_neither_error_is_a_valueerror(self):
        for exc in (DuplicateRequirementId, KeyNotDerivedFromId):
            assert issubclass(exc, ManifestIntegrityError)
            assert not issubclass(exc, ValueError), (
                f"{exc.__name__} would be swallowed by _layer_coverage_regen's "
                "except (OSError, ValueError) and misreported as a git/collector fault"
            )

    def test_the_regen_swallow_clause_does_not_catch_them(self):
        # The literal clause, exercised rather than described.
        for exc in (DuplicateRequirementId("x"), KeyNotDerivedFromId("x")):
            try:
                raise exc
            except (OSError, ValueError):  # noqa: B014 - mirrors _layer_coverage_regen
                raise AssertionError(f"{type(exc).__name__} was swallowed") from None
            except ManifestIntegrityError:
                pass


class TestActiveWinsTheKeyRegardlessOfOrder:
    """A tombstone must never displace a live row, whichever spec is discovered first."""

    _ACTIVE = (
        "# S\n\n"
        "| ID | Requirement | Priority | Layers |\n"
        "| --- | --- | --- | --- |\n"
        "| FR-03.01 | Live | Must | unit |\n"
    )
    _REMOVED = (
        "# S\n\n"
        "## Removed Requirements\n\n"
        "| ID | Requirement | Priority |\n"
        "| --- | --- | --- |\n"
        "| FR-03.01 | Tombstone | Must |\n"
    )

    def test_active_first_then_removed(self):
        index = build_requirement_index([
            (self._ACTIVE, ".shipwright/planning/01-a/spec.md"), (self._REMOVED, ".shipwright/planning/02-b/spec.md")])
        assert index.by_key["03::FR-03.01"].is_active
        assert [r.is_active for r in index.by_display_id["FR-03.01"]] == [True]

    def test_removed_first_then_active(self):
        index = build_requirement_index([
            (self._REMOVED, ".shipwright/planning/02-b/spec.md"), (self._ACTIVE, ".shipwright/planning/01-a/spec.md")])
        assert index.by_key["03::FR-03.01"].is_active
        assert [r.is_active for r in index.by_display_id["FR-03.01"]] == [True]
