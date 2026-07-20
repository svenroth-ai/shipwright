"""The ``(inferred)`` marker cell: what its malformations report, and what they don't.

Campaign S5. Three diagnostics over one cell, each added after a review round
found the previous one blind, and each carrying a decision worth keeping visible:

* a GLUED marker (``unit,e2e(inferred)``) swallows the layer it touches —
  detected differentially, by re-parsing with the marker split off;
* a marked cell whose tokens are not layer names at all (``ui (inferred)``)
  resolves to nothing and is recorded as ``unknown_layer_token``;
* a typo'd layer BESIDE a valid one (``unit, e2ee``) is deliberately NOT
  reported — a known blind spot, characterized rather than fixed, because a
  token in that position is either prose or a misspelling and its shape does not
  say which.

Provenance stays ``inferred_legacy`` throughout: these cells genuinely are
tool-derived, so the marker is doing its job. Only the LOSS is at issue.

Split out of ``test_requirement_parse.py``, which reached 322 lines with these
included — a real extraction this time, unlike the module note I had to correct
in ``test_group_d_invalid_layers.py``: the three blocks below were removed from
that file in the same change, not merely written here.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors._requirement_parse import parse_requirements  # noqa: E402
from tests.test_requirement_parse import _by_id  # noqa: E402


_GLUED_MARKER = """# Spec

## Functional Requirements
| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-09.05 | Orders | Checkout | Must | Persist orders | code | unit,e2e(inferred) |
| FR-09.06 | Orders | Refunds | Must | Persist refunds | code | unit, e2e (inferred) |
| FR-09.07 | Orders | Audit | Must | Persist audit rows | code | (inferred) |
"""


def test_a_glued_inferred_marker_records_the_layer_it_swallowed():
    """Campaign S5 follow-up. `render_layers` is the only sanctioned writer, but a
    spec.md is hand-edited by design and the iterate ADD path writes rows by hand,
    so sanction is not enforcement.

    `unit,e2e(inferred)` tokenises to `["unit", "e2e(inferred)"]`: the second is
    not a layer, so `e2e` is silently dropped while the row still LOOKS healthy —
    advisory provenance, a plausible layer list, no complaint anywhere. Provenance
    stays advisory (the cell IS tool-derived, so that part is correct); what the
    fix adds is that the LOSS becomes visible.
    """
    invalid: list = []
    reqs = parse_requirements(_GLUED_MARKER, spec_path="s.md", invalid_layers=invalid)

    glued = _by_id(reqs, "FR-09.05")
    assert glued.required_layers == ("unit",)              # e2e was swallowed
    assert glued.required_layers_source == "inferred_legacy"  # provenance unchanged
    entry = next(x for x in invalid if x["fr"] == "FR-09.05")
    assert entry["reason"] == "marker_glued"
    assert entry["lost"] == ["e2e"]

    # A correctly separated marker is silent -- no false positive on the normal cell.
    assert _by_id(reqs, "FR-09.06").required_layers == ("unit", "e2e")
    assert not any(x["fr"] == "FR-09.06" for x in invalid)

    # A BARE marker is legitimate (advisory, no required layers) and stays silent:
    # both sides of the differential parse to (), so there is nothing lost.
    assert _by_id(reqs, "FR-09.07").required_layers == ()
    assert not any(x["fr"] == "FR-09.07" for x in invalid)


_UNKNOWN_TOKEN = """# Spec

## Functional Requirements
| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-09.08 | Orders | Checkout | Must | Persist orders | code | ui (inferred) |
| FR-09.09 | Orders | Refunds | Must | Persist refunds | code | unit (inferred) |
"""


def test_a_marked_cell_whose_tokens_are_not_layers_is_recorded():
    """A second silent-loss route into the same regime, found by the Codex leg.

    `ui (inferred)` keeps advisory provenance (correct — it IS tool-derived) and
    its token resolves to nothing, so the requirement ends up with NO coverage
    obligation. The glued-marker differential cannot see it: both sides of that
    comparison parse to the same empty tuple. Recorded as `unknown_layer_token`
    so the loss is visible, with provenance deliberately unchanged.
    """
    invalid: list = []
    reqs = parse_requirements(_UNKNOWN_TOKEN, spec_path="s.md", invalid_layers=invalid)

    bad = _by_id(reqs, "FR-09.08")
    assert bad.required_layers == ()
    assert bad.required_layers_source == "inferred_legacy"
    entry = next(x for x in invalid if x["fr"] == "FR-09.08")
    assert entry["reason"] == "unknown_layer_token"
    assert entry["lost"] == ["ui"]

    # A valid marked cell must NOT be flagged -- no false positive on the norm.
    assert _by_id(reqs, "FR-09.09").required_layers == ("unit",)
    assert not any(x["fr"] == "FR-09.09" for x in invalid)


_TYPO_BESIDE_VALID = """# Spec

## Functional Requirements
| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-09.10 | Orders | Checkout | Must | Persist orders | code | unit, e2ee (inferred) |
| FR-09.11 | Orders | Refunds | Must | Persist refunds | code | unit and e2e (inferred) |
"""


def test_a_typod_layer_beside_a_valid_one_is_not_reported():
    """CHARACTERIZATION of a known blind spot — not an endorsement of it.

    The `not layers` guard suppresses `unknown_layer_token` whenever the cell
    resolved to at least one real layer. That removes a wrong-cause message on
    prose connectives (`unit and e2e`, second row below), and it costs a true
    positive: `unit, e2ee` silently carries only `unit`, and the misspelled
    `e2ee` is reported nowhere. The glued differential cannot catch it either —
    both sides of that comparison agree.

    A token in this position is either prose or a misspelling and its shape does
    not say which, so one of the two errors is unavoidable. Silence on a partial
    cell was chosen over a false report on every correct one. This test exists so
    the choice is visible and a future change to it is deliberate.
    """
    invalid: list = []
    reqs = parse_requirements(_TYPO_BESIDE_VALID, spec_path="s.md",
                              invalid_layers=invalid)

    typo = _by_id(reqs, "FR-09.10")
    assert typo.required_layers == ("unit",)          # e2ee silently dropped
    assert not any(x["fr"] == "FR-09.10" for x in invalid)   # ...and not reported

    # The false positive the guard exists to remove: this one parses correctly.
    prose = _by_id(reqs, "FR-09.11")
    assert prose.required_layers == ("unit", "e2e")
    assert not any(x["fr"] == "FR-09.11" for x in invalid)


