"""Tests for shared/scripts/tools/write_decision_drop.py."""

from __future__ import annotations

import json

import pytest

from tools.write_decision_drop import (
    DecisionDropError,
    drop_dir,
    write_decision_drop,
)


def _fields(**over):
    base = dict(
        run_id="iterate-20260515-foo",
        section="Iterate — change: foo",
        title="Foo decision",
        context="why",
        decision="what",
        consequences="impact",
    )
    base.update(over)
    return base


def test_writes_json_drop(tmp_path):
    path = write_decision_drop(tmp_path, **_fields())
    assert path.exists()
    assert path.parent == drop_dir(tmp_path)
    assert path.name == "iterate-20260515-foo_001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "iterate-20260515-foo"
    assert data["decision"] == "what"
    assert data["architecture_impact"] == "none"
    assert data["date"]  # populated by the tool


def test_two_drops_same_run_get_distinct_counters(tmp_path):
    p1 = write_decision_drop(tmp_path, **_fields())
    p2 = write_decision_drop(tmp_path, **_fields())
    assert p1.name == "iterate-20260515-foo_001.json"
    assert p2.name == "iterate-20260515-foo_002.json"


def test_empty_decision_rejected(tmp_path):
    with pytest.raises(DecisionDropError):
        write_decision_drop(tmp_path, **_fields(decision="   "))


def test_empty_run_id_rejected(tmp_path):
    with pytest.raises(DecisionDropError):
        write_decision_drop(tmp_path, **_fields(run_id=""))


def test_bad_architecture_impact_rejected(tmp_path):
    with pytest.raises(DecisionDropError):
        write_decision_drop(tmp_path, **_fields(architecture_impact="bogus"))


def test_optional_fields_persisted(tmp_path):
    path = write_decision_drop(
        tmp_path,
        **_fields(
            rationale="because",
            rejected="alt-a",
            architecture_impact="convention",
        ),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rationale"] == "because"
    assert data["rejected"] == "alt-a"
    assert data["architecture_impact"] == "convention"
