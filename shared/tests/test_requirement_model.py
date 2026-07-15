"""Tests for the one versioned requirement model (traceability R5)."""

from __future__ import annotations

import json
from pathlib import Path

from lib.requirement_model import (
    LAYERS,
    MODEL_VERSION,
    REQUIRED_LAYERS_SOURCES,
    Requirement,
    is_canonical_fr,
    is_layer,
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
    assert schema["properties"]["schema_version"]["const"] == MODEL_VERSION == 2


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
        namespace="app",
        spec_path="mini_repos/app/spec.md",
        title="User can sign in",
        required_layers=("unit", "e2e"),
        required_layers_source="explicit",
    )
    assert r.key == "app::FR-03.01"
    assert r.is_active  # default status "active"
    removed = Requirement(id="FR-03.09", namespace="app", status="removed")
    assert not removed.is_active


def test_required_layers_source_vocabulary():
    assert REQUIRED_LAYERS_SOURCES == ("explicit", "inferred_legacy", "defaulted_legacy")
