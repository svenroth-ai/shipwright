"""``traceability_layers`` takes an FR table WITH and WITHOUT the optional
``Capability`` column (intent pyramid U1a): same ambiguous FRs, and the
write-back lands in the Layers cell whichever column precedes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PLUGIN / "scripts" / "lib"))

import traceability_layers as tl  # noqa: E402


pytestmark = pytest.mark.covers("FR-01.16/AC02")


def _spec(with_capability: bool) -> str:
    cap_h, cap_s, cap_c = (" Capability |", "---|", " CAP-01 |") if with_capability else ("", "", "")
    return (
        "# Spec\n\n## Functional Requirements\n"
        f"| ID | Area |{cap_h} Name | Priority | Description | Basis | Layers |\n"
        f"|---|---|{cap_s}---|---|---|---|---|\n"
        f"| FR-01.01 | Core |{cap_c} Sign in | Must | Signs in. | code | unit, e2e |\n"
        f"| FR-01.02 | Core |{cap_c} Sign out | Must | Signs out. | code | unit (inferred) |\n"
    )


BOTH = pytest.mark.parametrize("with_capability", [False, True], ids=["no-column", "with-column"])


@BOTH
def test_only_the_non_explicit_row_is_ambiguous(with_capability):
    amb = tl.find_ambiguous_frs(_spec(with_capability), "01-core")
    assert [(a["id"], a["key"], a["title"]) for a in amb] == [("FR-01.02", "01-core::FR-01.02", "Core")]


@BOTH
def test_write_back_rewrites_the_layers_cell(with_capability, tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_spec(with_capability), encoding="utf-8", newline="\n")
    res = [tl.LayerResolution(
        key="01-core::FR-01.02", fr_id="FR-01.02", required_layers=["unit", "e2e"],
        provenance="x", resolved_from="predeclared_decision",
    )]
    assert tl.apply_layer_decisions_to_spec(spec, res) == 1
    row = [ln for ln in spec.read_text(encoding="utf-8").splitlines() if ln.startswith("| FR-01.02")][0]
    assert row.endswith("| unit, e2e (inferred) |")
    assert ("CAP-01" in row) is with_capability
    assert tl.apply_layer_decisions_to_spec(spec, res) == 0  # idempotent
