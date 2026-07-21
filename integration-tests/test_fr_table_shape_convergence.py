"""Both producers emit ONE table shape — and the live catalog stays advisory.

Campaign "Requirements Catalog", sub-iterate S5. Two things are pinned here, and
the second is the one that matters most to the campaign.

**Convergence.** "Byte-compatible headers" is otherwise checkable only by eye: a
column renamed in the adopt writer and not in the greenfield template looks
correct in both files independently, and the reader resolves by NAME, so a
renamed column is not a cosmetic difference — it is a column that stopped
existing. The header is one constant and every producer is compared to it.

**The hard blocker (SPEC §6.2).** A requirement's provenance becomes ``explicit``
the moment a header-named ``Layers`` cell is non-empty WITHOUT the literal
``(inferred)`` marker, and ``explicit`` routes a coverage gap from advisory to
hard → ``sys.exit(1)``, unbypassably. Ten of the fifteen live requirements have
zero test links, so unmarked cells would hard-abort against ten guaranteed gaps.
The census test below is the guard, and the counter-probe beside it proves the
guard is load-bearing rather than vacuously true.

@FR-01.02
@FR-01.10
@FR-01.13
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_table_shape import FR_TABLE_HEADER, render_layers  # noqa: E402

LIVE_SPEC = REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"
GREENFIELD_REF = (
    REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project"
    / "references" / "spec-generation.md"
)

#: Run the compliance parser in its OWN process. `shared/scripts` and the
#: compliance plugin BOTH ship a top-level `lib` package, so importing the
#: collectors after `shared/scripts/lib` is on the path resolves the wrong one
#: (ADR-045). The corpus harness isolates by subprocess for the same reason.
_CENSUS = """
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / "plugins" / "shipwright-compliance" / "scripts"))
from lib.collectors._requirement_parse import parse_requirements
reqs = parse_requirements(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"),
                          spec_path="spec.md")
print(json.dumps([
    {"id": r.id, "source": r.required_layers_source,
     "layers": list(r.required_layers)} for r in reqs
]))
"""


def _census(spec_path: Path) -> list[dict]:
    import json
    out = subprocess.run(
        [sys.executable, "-c", _CENSUS, str(REPO_ROOT), str(spec_path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


# ---------------------------------------------------------------------------
# Convergence — one header, every producer
# ---------------------------------------------------------------------------


def test_the_live_catalog_carries_the_canonical_header() -> None:
    assert FR_TABLE_HEADER in LIVE_SPEC.read_text(encoding="utf-8")


def test_the_greenfield_template_and_example_both_carry_it() -> None:
    """The EXAMPLE is the more copyable of the two and was the one missing a
    mandated column (SPEC §2.1) — so it is asserted, not assumed."""
    text = GREENFIELD_REF.read_text(encoding="utf-8")
    assert text.count(FR_TABLE_HEADER) >= 2, (
        "both the FR-table template and the worked example must carry the "
        "canonical header"
    )


# Held in a named constant rather than inline in the argv list below. Adjacent
# string literals inside a list read as a missing comma -- the difference
# between one program and several arguments is a single character -- so the
# program is assembled where it is unambiguous and the argv list stays four
# plain elements.
_RENDER_ADOPT_FR_TABLE = (
    "import sys, pathlib\n"
    "root = pathlib.Path(sys.argv[1])\n"
    "sys.path.insert(0, str(root / 'plugins' / 'shipwright-adopt' / 'scripts'))\n"
    "from lib.spec_table import render_fr_table\n"
    "print(render_fr_table([], split_name='01-adopted'))\n"
)


def test_the_adopt_generator_emits_it() -> None:
    """Rendered through the real producer, not asserted against its source."""
    out = subprocess.run(
        [sys.executable, "-c", _RENDER_ADOPT_FR_TABLE, str(REPO_ROOT)],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.splitlines()[0] == FR_TABLE_HEADER


def test_no_producer_still_emits_the_retired_source_column() -> None:
    """`Source` held a file path — implementation detail (D3). Its absence is
    what makes `Basis` the single provenance answer rather than a second one."""
    for path in (LIVE_SPEC, GREENFIELD_REF):
        assert "| Priority | Description | Source |" not in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The hard blocker
# ---------------------------------------------------------------------------


def test_every_live_requirement_stays_on_legacy_provenance() -> None:
    """ZERO ``explicit``. If this fails, the next gate run hard-aborts."""
    rows = _census(LIVE_SPEC)
    assert len(rows) == 15
    explicit = [r["id"] for r in rows if r["source"] == "explicit"]
    assert explicit == [], (
        f"{len(explicit)} requirement(s) flipped to `explicit` provenance: "
        f"{explicit}. Ten of fifteen have zero test links, so this hard-aborts "
        f"the layer-coverage gate (SPEC §6.2). Every Layers cell must carry the "
        f"literal (inferred) marker."
    )
    assert {r["source"] for r in rows} <= {"inferred_legacy", "defaulted_legacy"}


def test_every_live_layers_cell_carries_the_marker() -> None:
    """The AC, asserted on the artifact rather than on the intent."""
    rows = [
        line for line in LIVE_SPEC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| FR-")
    ]
    assert len(rows) == 15
    for line in rows:
        layers_cell = line.rstrip("|").rsplit("|", 1)[-1].strip()
        assert "(inferred)" in layers_cell, f"unmarked Layers cell: {line[:60]}…"


def test_an_unmarked_cell_really_would_flip_to_explicit(tmp_path: Path) -> None:
    """The counter-probe: proves the marker is what holds the gate open.

    Without this, the census test above passes just as happily against a build
    where provenance can no longer reach ``explicit`` at all — a guard that
    cannot fail is not a guard.
    """
    spec = tmp_path / "spec.md"
    spec.write_text(
        LIVE_SPEC.read_text(encoding="utf-8").replace(" (inferred)", ""),
        encoding="utf-8",
    )
    rows = _census(spec)
    assert [r["id"] for r in rows if r["source"] == "explicit"], (
        "stripping the marker did NOT produce explicit provenance — the census "
        "test is vacuous and the hard blocker is unguarded"
    )


#: What ``_infer_layers`` derived for each requirement BEFORE the shape change,
#: measured on the pre-migration table. The migrated ``Layers`` cells write these
#: values down; they do not introduce new ones. Pinned per ID rather than as a
#: distribution: a 12/3 count is also satisfied by a migration that swaps
#: FR-01.01 and FR-01.04, which would violate the AC while looking correct.
_PRE_MIGRATION_LAYERS = {
    "FR-01.01": ["unit"], "FR-01.02": ["unit"], "FR-01.03": ["unit"],
    "FR-01.04": ["e2e"],  "FR-01.05": ["unit"], "FR-01.06": ["unit"],
    "FR-01.07": ["unit"], "FR-01.08": ["unit"], "FR-01.09": ["unit"],
    "FR-01.10": ["unit"], "FR-01.11": ["unit"], "FR-01.12": ["e2e"],
    "FR-01.13": ["unit"], "FR-01.14": ["unit"], "FR-01.15": ["e2e"],
}


#: The `Basis` each live requirement was migrated to, per FR (decision D-S5-1).
#: Per-FR rather than aggregate: "13x enrichment.json all map to code" cannot
#: catch a later hand edit that changes ONE row's provenance, and the migration
#: script that made the decision was a throwaway and is not in the tree. This
#: fixture is the durable record of it. Raised by external review on this head.
_EXPECTED_BASIS = {f"FR-01.{n:02d}": "code" for n in range(1, 16)}


def test_every_live_requirement_carries_its_decided_basis() -> None:
    rows = {
        line.split("|")[1].strip(): line.split("|")[6].strip()
        for line in LIVE_SPEC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| FR-")
    }
    assert rows == _EXPECTED_BASIS


def test_no_persisted_area_cell_disagrees_with_its_own_id() -> None:
    """`Area` is RENDERED from the group digit (D7), so a stored cell can drift.

    The ID stays authoritative for every parser, which is why drift is not a
    correctness bug — but the wrong label is still what a human reads, and
    "the ID wins" does not help someone looking at a table that says otherwise.
    Raised by external review on this head.
    """
    from fr_table_shape import area_for

    mismatched = [
        (cells[1].strip(), cells[2].strip(), expected)
        for line in LIVE_SPEC.read_text(encoding="utf-8").splitlines()
        if line.startswith("| FR-")
        for cells in [line.split("|")]
        for expected in [area_for(cells[1].strip(), "01-adopted")]
        if cells[2].strip() != expected
    ]
    assert mismatched == [], f"Area cells disagreeing with their own id: {mismatched}"


def test_the_migration_did_not_change_any_required_layers() -> None:
    """The marked cells record the inference that already ran; they add no claim.

    Per requirement, not in aggregate — the AC is that every row kept its value,
    and a distribution check cannot see a swap between two rows.
    """
    assert {r["id"]: r["layers"] for r in _census(LIVE_SPEC)} == _PRE_MIGRATION_LAYERS


@pytest.mark.parametrize("layers,inferred,expected_source", [
    (("unit",), True, "inferred_legacy"),
    (("unit", "e2e"), True, "inferred_legacy"),
    (("unit",), False, "explicit"),
])
def test_render_layers_round_trips_to_the_provenance_it_promises(
    tmp_path: Path, layers: tuple, inferred: bool, expected_source: str,
) -> None:
    """Producer → file → consumer, for both sides of the marker (ADR-024)."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        f"{FR_TABLE_HEADER}\n|---|---|---|---|---|---|---|\n"
        f"| FR-01.01 | Adopted | Login | Must | Users sign in | code | "
        f"{render_layers(layers, inferred=inferred)} |\n",
        encoding="utf-8",
    )
    (row,) = _census(spec)
    assert row["source"] == expected_source
    assert tuple(row["layers"]) == layers
