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
    reqs = parse_requirements(_4COL, spec_path="spec.md")
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
    reqs = parse_requirements(_4COL, spec_path="spec.md")
    removed = _by_id(reqs, "FR-01.09")
    assert removed.status == "removed" and removed.is_active is False
    assert removed.required_layers == ("e2e",)
    # active FRs stay active
    assert _by_id(reqs, "FR-01.01").status == "active"


def test_5col_adopt_shape_reads_description_as_title_not_layers():
    reqs = parse_requirements(_5COL, spec_path="spec.md")
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
    """v3: the key namespace comes from the FR id's group digits (``FR-02.01`` -> ``02``),
    while ``spec_path`` still records WHERE the row was found. The directory in that path
    (``01-adopted``) deliberately disagrees with the namespace — proving the key no longer
    reads it."""
    reqs = parse_requirements(_5COL, spec_path=".shipwright/planning/01-adopted/spec.md")
    r1 = _by_id(reqs, "FR-02.01")
    assert r1.key == "02::FR-02.01"
    assert r1.namespace == "02"
    assert r1.spec_path == ".shipwright/planning/01-adopted/spec.md"


# TT3 — the greenfield project/plan template FR table (a `Requirement`-named body
# column + an explicit `Layers` column). Pins AC1's "a CRUD FR gets integration"
# via an explicit Layers value, and the empty-cell provenance regime for AC3.
_GREENFIELD = """# Spec
## 2. Functional Requirements
| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-03.01 | The system SHALL persist orders to the database | Must | unit, integration |
| FR-03.02 | The system SHALL show a dashboard | Should | |
"""


def test_greenfield_requirement_col_with_explicit_integration_layer():
    reqs = parse_requirements(_GREENFIELD, spec_path="spec.md")
    r1 = _by_id(reqs, "FR-03.01")
    assert r1.title == "The system SHALL persist orders to the database"
    assert r1.required_layers == ("unit", "integration")
    assert r1.required_layers_source == "explicit"


def test_greenfield_empty_layers_is_legacy_provenance_not_explicit():
    # AC3: an FR authored without the field must NOT read as "explicit" — the two
    # regimes (post-rollout omission vs legacy-missing) must stay distinguishable.
    reqs = parse_requirements(_GREENFIELD, spec_path="spec.md")
    r2 = _by_id(reqs, "FR-03.02")
    assert r2.required_layers_source == "inferred_legacy"   # "dashboard" ⇒ e2e
    assert r2.required_layers == ("e2e",)


# An adopt-generated spec annotates its surface-inferred layers with `(inferred)`.
# The set is still read, but the provenance is downgraded to advisory so a
# brownfield repo's FRs do NOT collapse into the `explicit` hard-gate (Spec §9 /
# R4). This is the producer(adopt)→spec.md→parser round-trip the review flagged.
_ADOPT_INFERRED = """# Spec
## Functional Requirements
| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-04.01 | /orders | Must | Orders page | src/app/orders/page.tsx | unit, e2e (inferred) |
| FR-04.02 | schema | Must | Persist orders | db/migrations/001.sql | unit, integration (inferred) |
"""


_INVALID_LAYERS = """# Spec
## Functional Requirements
| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-09.03 | Persist orders | Must | int, db |
| FR-09.04 | Checkout page | Must | |
"""


def test_nonempty_but_noncanonical_layers_cell_is_flagged_not_demoted():
    # MUST-FIX 1 (§11-R4 collapse): an author typo/synonym in a HEADED Layers cell
    # must stay `explicit` (so D-layer's post-rollout hard gate still fires) and be
    # recorded — NOT silently demoted to advisory `defaulted_legacy` (which would both
    # escape the gate and discard the author's intended integration layer).
    invalid: list = []
    reqs = parse_requirements(
        _INVALID_LAYERS, spec_path="s.md", invalid_layers=invalid)
    r = _by_id(reqs, "FR-09.03")
    assert r.required_layers == ()                 # "int"/"db" are not canonical layers
    assert r.required_layers_source == "explicit"  # kept explicit, NOT demoted to legacy
    assert any(x["fr"] == "FR-09.03" and x["raw"] == "int, db"
               and x["reason"] == "no_canonical_layer" for x in invalid)
    # an EMPTY cell still takes the legacy path unchanged (and is NOT flagged)
    r2 = _by_id(reqs, "FR-09.04")
    assert r2.required_layers_source == "inferred_legacy"   # "page" ⇒ e2e
    assert not any(x["fr"] == "FR-09.04" for x in invalid)


def test_only_the_exact_inferred_marker_downgrades_not_auto_or_adopt():
    # MUST-FIX 2: only the exact ` (inferred)` marker (what adopt emits) downgrades to
    # advisory. A post-rollout author writing `(auto)`/`(adopted)` must stay `explicit`
    # (hard-gated) — the marker regex is narrowed to `(inferred)` only.
    spec = (
        "## Functional Requirements\n"
        "| ID | Requirement | Priority | Layers |\n"
        "|----|-------------|----------|--------|\n"
        "| FR-09.05 | Store orders | Must | unit, e2e (auto) |\n"
        "| FR-09.06 | Store items | Must | unit, e2e (inferred) |\n"
    )
    reqs = parse_requirements(spec, spec_path="s.md")
    assert _by_id(reqs, "FR-09.05").required_layers_source == "explicit"        # (auto) not downgraded
    assert _by_id(reqs, "FR-09.06").required_layers_source == "inferred_legacy"  # (inferred) advisory


def test_adopt_inferred_marker_reads_as_advisory_not_explicit():
    reqs = parse_requirements(_ADOPT_INFERRED, spec_path="spec.md")
    r1 = _by_id(reqs, "FR-04.01")
    assert r1.required_layers == ("unit", "e2e")
    assert r1.required_layers_source == "inferred_legacy"   # NOT "explicit"
    r2 = _by_id(reqs, "FR-04.02")
    assert r2.required_layers == ("unit", "integration")
    assert r2.required_layers_source == "inferred_legacy"


_NOISY = """# Spec
## Functional Requirements
| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-05.01 | Store an order | Must | E2E, unit, unit, foo, none |
"""


def test_layers_are_normalized_lowercased_deduped_and_unknown_dropped():
    # AC1 robustness: an author-typed Layers cell is case-folded, de-duplicated, and
    # non-layer tokens (foo/none) are dropped — the manifest never carries junk.
    reqs = parse_requirements(_NOISY, spec_path="spec.md")
    r = _by_id(reqs, "FR-05.01")
    assert r.required_layers == ("e2e", "unit")   # order preserved, deduped, valid-only
    assert r.required_layers_source == "explicit"
