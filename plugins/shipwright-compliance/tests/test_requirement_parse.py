"""TT1 — FR-table → ``requirement_model.Requirement`` parser (`_requirement_parse`).

Pins the header-column-aware parse so the 4-col traceability shape
(``| FR | Description | Priority | Layers |``) and the 5-col adopt shape
(``| ID | Name | Priority | Description | Source |``, ADR-031) never confuse the
Layers cell with the Description cell, and the ``required_layers`` provenance
(explicit / inferred_legacy / defaulted_legacy) is derived per Spec D2 / R4.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors._requirement_parse import parse_requirements  # noqa: E402

_4COL = """# Spec
## Functional Requirements
| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.01 | User can sign in | Must | unit, e2e |
| FR-01.02 | Dashboard shows live orders | Must | |
| FR-01.03 | Persist an order to the database | Should | |

## Removed Requirements
| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.09 | Copy the launch command | Should | e2e |
"""

# The adopt shape: Priority is col 3, the FR body is the Description col (4), there is
# NO Layers column. A naive positional parse would read the Description as "Layers".
_5COL = """# Spec
## Functional Requirements
| ID | Name | Priority | Description | Source |
|----|------|----------|-------------|--------|
| FR-02.01 | /cmd | Must | Persist rows to the database | enrichment.json |
| FR-02.02 | /view | Should | Render the dashboard page | enrichment.json |
"""


def _by_id(reqs, fr_id):
    return next(r for r in reqs if r.id == fr_id)


def test_4col_explicit_layers_and_provenance():
    reqs = parse_requirements(_4COL, namespace="app", spec_path="spec.md")
    assert {r.id for r in reqs} == {"FR-01.01", "FR-01.02", "FR-01.03", "FR-01.09"}
    r1 = _by_id(reqs, "FR-01.01")
    assert r1.required_layers == ("unit", "e2e") and r1.required_layers_source == "explicit"
    assert r1.title == "User can sign in" and r1.priority == "Must"
    # empty Layers + UI/flow title -> inferred_legacy e2e
    r2 = _by_id(reqs, "FR-01.02")
    assert r2.required_layers == ("e2e",) and r2.required_layers_source == "inferred_legacy"
    # empty Layers + no UI signal -> defaulted_legacy unit
    r3 = _by_id(reqs, "FR-01.03")
    assert r3.required_layers == ("unit",) and r3.required_layers_source == "defaulted_legacy"


def test_removed_section_marks_status_removed():
    reqs = parse_requirements(_4COL, namespace="app", spec_path="spec.md")
    removed = _by_id(reqs, "FR-01.09")
    assert removed.status == "removed" and removed.is_active is False
    assert removed.required_layers == ("e2e",)
    # active FRs stay active
    assert _by_id(reqs, "FR-01.01").status == "active"


def test_5col_adopt_shape_reads_description_as_title_not_layers():
    reqs = parse_requirements(_5COL, namespace="01-adopted", spec_path="spec.md")
    r1 = _by_id(reqs, "FR-02.01")
    # the Description cell is the title — NOT mistaken for a Layers value
    assert r1.title == "Persist rows to the database"
    assert r1.priority == "Must"
    # no Layers column -> inference; "database/persist" is not a UI signal -> unit
    assert r1.required_layers == ("unit",) and r1.required_layers_source == "defaulted_legacy"
    # a UI/flow description still infers e2e
    r2 = _by_id(reqs, "FR-02.02")
    assert r2.required_layers == ("e2e",) and r2.required_layers_source == "inferred_legacy"


def test_namespaced_key_and_spec_path():
    reqs = parse_requirements(_5COL, namespace="01-adopted", spec_path=".shipwright/planning/01-adopted/spec.md")
    r1 = _by_id(reqs, "FR-02.01")
    assert r1.key == "01-adopted::FR-02.01"
    assert r1.spec_path == ".shipwright/planning/01-adopted/spec.md"
