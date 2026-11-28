"""``parse_requirements`` reads an FR table WITH and WITHOUT the optional
``Capability`` column identically (intent pyramid U1a)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.lib.collectors._requirement_parse import parse_requirements  # noqa: E402


pytestmark = pytest.mark.covers("FR-01.16/AC02")


def _spec(with_capability: bool) -> str:
    cap_h, cap_s, cap_c = (" Capability |", "---|", " CAP-01 |") if with_capability else ("", "", "")
    return (
        "# Spec\n\n## Functional Requirements\n"
        f"| ID | Area |{cap_h} Name | Priority | Description | Basis | Layers |\n"
        f"|---|---|{cap_s}---|---|---|---|---|\n"
        f"| FR-09.05 | Orders |{cap_c} Checkout | Must | Persist orders | code | unit, e2e |\n"
        f"| FR-09.06 | Orders |{cap_c} Refunds | Should | Persist refunds | code | unit (inferred) |\n"
    )


def _shape(with_capability: bool) -> list:
    invalid_layers: list = []
    invalid_ids: list = []
    reqs = parse_requirements(
        _spec(with_capability), spec_path="spec.md",
        invalid_layers=invalid_layers, invalid_ids=invalid_ids,
    )
    assert invalid_layers == [] and invalid_ids == []
    return [(r.id, r.title, r.priority, r.status, tuple(r.required_layers), r.required_layers_source) for r in reqs]


def test_both_shapes_parse_to_the_same_requirements():
    without, with_col = _shape(False), _shape(True)
    assert len(without) == 2
    assert with_col == without
    assert without[0][4] == ("unit", "e2e")
