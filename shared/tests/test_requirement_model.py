"""Tests for the one versioned requirement model (traceability R5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.requirement_model import (
    LAYERS,
    MODEL_VERSION,
    REQUIRED_LAYERS_SOURCES,
    Requirement,
    is_canonical_fr,
    is_layer,
    key_for_id,
    namespace_for_id,
    namespaced_key,
    split_namespaced_key,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = (
    _REPO_ROOT
    / "plugins/shipwright-compliance/scripts/lib/traceability_schema.json"
)


def test_model_version_tracks_manifest_schema_version():
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == MODEL_VERSION == 3


def test_layers_are_the_closed_vocabulary():
    assert LAYERS == ("unit", "integration", "e2e")
    assert is_layer("unit") and is_layer("e2e")
    assert not is_layer("smoke") and not is_layer("pgtap")


def test_is_canonical_fr():
    assert is_canonical_fr("FR-01.03")
    assert not is_canonical_fr("FR-1.3")     # single-digit segments
    assert not is_canonical_fr("FR-7")       # legal spec heading id, not a canonical token
    assert not is_canonical_fr("FR01.03")    # missing the dash
    assert not is_canonical_fr("@FR-01.03")  # tag token, not a bare id


def test_namespaced_key_round_trips():
    key = namespaced_key("01-adopted", "FR-01.03")
    assert key == "01-adopted::FR-01.03"
    assert split_namespaced_key(key) == ("01-adopted", "FR-01.03")


def test_namespaced_key_splits_on_last_delimiter():
    # A namespace that itself contains '::' still yields the trailing FR id.
    key = namespaced_key("a::b", "FR-09.09")
    assert split_namespaced_key(key) == ("a::b", "FR-09.09")


def test_requirement_key_and_status():
    r = Requirement(
        id="FR-03.01",
        spec_path="mini_repos/app/spec.md",
        title="User can sign in",
        required_layers=("unit", "e2e"),
        required_layers_source="explicit",
    )
    assert r.key == "03::FR-03.01"
    assert r.is_active  # default status "active"
    removed = Requirement(id="FR-03.09", status="removed")
    assert not removed.is_active


def test_namespace_derives_from_the_id_not_the_path():
    """v3: the group digits of the id ARE the namespace, whatever the spec path says."""
    assert namespace_for_id("FR-01.03") == "01"
    assert namespace_for_id("FR-42.99") == "42"
    assert key_for_id("FR-07.02") == "07::FR-07.02"


def test_namespace_is_not_a_constructor_field():
    """The whole point of v3: a caller CANNOT hand a directory name in.

    A regression that restores the field would make this pass silently, so assert
    the constructor rejects it rather than merely asserting the derived value."""
    with pytest.raises(TypeError):
        Requirement(id="FR-03.01", namespace="01-adopted")  # type: ignore[call-arg]


def test_namespace_survives_a_spec_path_change():
    """Rename the split directory; the key must not move (the S3 rationale)."""
    before = Requirement(id="FR-03.01", spec_path=".shipwright/planning/01-adopted/spec.md")
    after = Requirement(id="FR-03.01", spec_path=".shipwright/planning/99-renamed/spec.md")
    assert before.key == after.key == "03::FR-03.01"


def test_non_canonical_id_has_no_derivable_namespace():
    """A silent fallback would INVENT a key; refusing is the fail-closed choice."""
    for bad in ("FR-7", "FR-1.3", "not-an-fr", ""):
        with pytest.raises(ValueError):
            namespace_for_id(bad)


def test_required_layers_source_vocabulary():
    assert REQUIRED_LAYERS_SOURCES == ("explicit", "inferred_legacy", "defaulted_legacy")
