"""The spec and its summary are written together, and agree (FR-01.13).

`write_spec` is the single writer of both `.shipwright/planning/<split>/spec.md`
and `.shipwright/adopt/derived-catalogue.json`. That is the structural guarantee
behind `trg-1aa5a8ab`: the count reported at handover cannot describe a
different table than the one handed over, because one `summarize` pass produces
both and one function writes both.

Tested at `write_spec` rather than through the whole generator on purpose — this
is the contract, and the wired-up `generate()` path goes through this same
function (its own tests fail if the wiring breaks).

@FR-01.13
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.derived_catalogue import SUMMARY_REL  # noqa: E402
from lib.spec_document import write_spec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))
from fr_table_reader import read_active_fr_rows, read_fr_rows  # noqa: E402

FEATURES = [
    {"fr_id": "FR-01.01", "label": "Sign in", "source_file": "src/auth.ts"},
    {"fr_id": "FR-01.02", "label": "Dashboard", "url": "http://localhost:5173/"},
]


def _write(root: Path, features=FEATURES) -> list[Path]:
    return write_spec(
        root, project_name="Demo", split_name="01-adopted",
        product_description="x", features=features, qr_items=[], constraints=[],
    )


def test_both_files_are_written_spec_first(tmp_path: Path) -> None:
    spec, summary = _write(tmp_path)
    assert spec == tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md"
    assert summary == tmp_path / SUMMARY_REL
    assert spec.is_file() and summary.is_file()


def test_the_spec_says_the_catalogue_is_derived_and_unconfirmed(tmp_path: Path) -> None:
    spec, _ = _write(tmp_path)
    body = spec.read_text(encoding="utf-8")
    assert "nobody has confirmed them yet" in body
    assert SUMMARY_REL in body
    assert "requirement-elicitation.md" in body


def test_the_summary_describes_the_table_that_was_actually_rendered(tmp_path: Path) -> None:
    """The anti-drift contract, end to end: the JSON is compared against the
    RENDERED spec parsed by the shared reader, not against its own input."""
    spec, summary = _write(tmp_path)
    doc = json.loads(summary.read_text(encoding="utf-8"))
    rows = read_active_fr_rows(spec.read_text(encoding="utf-8"))

    assert [r.id for r in rows] == [r["fr_id"] for r in doc["requirements"]]
    assert [r.basis_cell for r in rows] == [r["basis"] for r in doc["requirements"]]
    assert doc["total"] == len(rows) == 2
    assert doc["unconfirmed"] == 2


def test_a_zero_detection_repo_still_agrees(tmp_path: Path) -> None:
    """The placeholder row a zero-detection repo gets is a real row, so the
    summary must count it — a reported 0 beside a table with a row in it is the
    exact drift this pairing exists to prevent."""
    spec, summary = _write(tmp_path, features=[])
    doc = json.loads(summary.read_text(encoding="utf-8"))
    rows = read_active_fr_rows(spec.read_text(encoding="utf-8"))
    assert doc["total"] == len(rows) == 1
    assert doc["requirements"][0]["fr_id"] == rows[0].id


def test_the_banner_does_not_disturb_the_table(tmp_path: Path) -> None:
    """The provenance block sits between the heading and the table. Every
    FR-table consumer is line-based on a leading `|`, so the rows a reader sees
    must be byte-identical to the table alone."""
    spec, _ = _write(tmp_path)
    body = spec.read_text(encoding="utf-8")
    # Quality requirements fold into this same table (trg-8db840a6) — the next
    # heading after Functional Requirements is now Constraints.
    section = body.split("## Functional Requirements", 1)[1].split("## Constraints", 1)[0]
    banner_lines = [
        ln for ln in section.splitlines()
        if ln.strip() and not ln.strip().startswith("|")
    ]
    assert banner_lines, "the provenance block is missing"
    assert all(ln.lstrip().startswith(">") for ln in banner_lines), banner_lines
    assert len(read_active_fr_rows(body)) == 2


def test_a_re_run_overwrites_both_in_place(tmp_path: Path) -> None:
    first = [p.read_text(encoding="utf-8") for p in _write(tmp_path)]
    assert [p.read_text(encoding="utf-8") for p in _write(tmp_path)] == first


def test_pipes_in_detected_text_survive_the_round_trip(tmp_path: Path) -> None:
    spec, summary = _write(tmp_path, features=[
        {"fr_id": "FR-01.01", "label": "a | b", "description": "c | d",
         "source_file": "src/x.ts"},
    ])
    rows = read_active_fr_rows(spec.read_text(encoding="utf-8"))
    doc = json.loads(summary.read_text(encoding="utf-8"))
    assert len(rows) == doc["total"] == 1
    assert rows[0].id == doc["requirements"][0]["fr_id"] == "FR-01.01"
    assert re.search(r"^\| FR-01\.01 \|", spec.read_text(encoding="utf-8"), re.MULTILINE)


# ---------------------------------------------------------------------------
# QR items fold into the FR table (trg-8db840a6)
# ---------------------------------------------------------------------------
#
# Adopt used to render a quality requirement as a prose bullet under its own
# `QR-{i:02d}` label — a row `fr_gates.collect_known_fr_ids` (a FR-table
# reader) never parses, so `--affected-frs QR-02` at finalize was rejected
# with "declared FR id(s) exist in no spec" for every iterate that implemented
# one (measured on leadwright, trg-8db840a6). A QR item now becomes an
# ordinary FR row instead, continuing the same id sequence.


def test_qr_items_become_fr_rows_continuing_the_sequence(tmp_path: Path) -> None:
    spec, summary = write_spec(
        tmp_path, project_name="Demo", split_name="01-adopted",
        product_description="x", features=FEATURES,
        qr_items=["CI pipeline (github-actions) must pass on pull requests."],
        constraints=[],
    )
    body = spec.read_text(encoding="utf-8")
    rows = read_active_fr_rows(body)
    doc = json.loads(summary.read_text(encoding="utf-8"))

    # Continues past the 2 detected features (FR-01.01, FR-01.02) — never a
    # separate `QR-` id space.
    assert [r.id for r in rows] == ["FR-01.01", "FR-01.02", "FR-01.03"]
    qr_row = rows[-1]
    assert "CI pipeline (github-actions) must pass" in qr_row.text
    # No source_file/url on a QR row: falls back to `assumed`, same as any
    # other feature with no evidence (spec_table.basis_for).
    assert qr_row.basis_cell == "assumed"
    # No surface signal to infer from: falls back to `unit`-only, still
    # carrying the `(inferred)` marker that keeps it advisory (SPEC §9).
    assert "unit" in qr_row.layers_cell and "(inferred)" in qr_row.layers_cell
    # The summary is derived from the SAME folded list the table renders
    # (trg-1aa5a8ab) — the QR row is not a blind spot in the count either.
    assert doc["total"] == len(rows) == 3
    assert "FR-01.03" in {r["fr_id"] for r in doc["requirements"]}
    # No separate section — the fold IS the whole point.
    assert "## Quality Requirements" not in body


def test_a_spec_with_no_qrs_is_unchanged(tmp_path: Path) -> None:
    spec, summary = _write(tmp_path)  # qr_items=[] via the module default
    body = spec.read_text(encoding="utf-8")
    doc = json.loads(summary.read_text(encoding="utf-8"))
    assert len(read_active_fr_rows(body)) == doc["total"] == 2
    assert "## Quality Requirements" not in body


def test_regeneration_over_an_existing_spec_does_not_renumber(tmp_path: Path) -> None:
    """trg-8db840a6's ONE REAL HAZARD, reproduced directly: a re-run whose
    fresh detection finds FEWER features than the run that is already on disk
    must not let a QR id fall into the range an id from the prior run's spec
    still means elsewhere (events.jsonl / the RTM / a test tag / a closed PR).
    """
    first_spec, _ = write_spec(
        tmp_path, project_name="Demo", split_name="01-adopted",
        product_description="x", features=FEATURES,  # 2 features
        qr_items=["CI must pass."], constraints=[],
    )
    first_ids = [r.id for r in read_active_fr_rows(first_spec.read_text(encoding="utf-8"))]
    assert first_ids == ["FR-01.01", "FR-01.02", "FR-01.03"]

    # A later run detects only ONE feature (e.g. a route no longer reachable)
    # — naive positional numbering would place the new QR row at FR-01.02,
    # reusing the id the FIRST run's FR-01.02 ("Dashboard") already means.
    second_spec, _ = write_spec(
        tmp_path, project_name="Demo", split_name="01-adopted",
        product_description="x", features=FEATURES[:1],  # 1 feature
        qr_items=["Lint must pass."], constraints=[],
    )
    second_rows = read_active_fr_rows(second_spec.read_text(encoding="utf-8"))
    second_ids = [r.id for r in second_rows]
    assert second_ids == ["FR-01.01", "FR-01.04"]
    assert "FR-01.02" not in second_ids  # never reused for a different row
    assert "Lint must pass." in second_rows[-1].text


def test_regeneration_does_not_reuse_a_retired_id_either(tmp_path: Path) -> None:
    """Code-review finding: a retired FR row (moved under `## Removed
    Requirements` by an unrelated `/shipwright-iterate` REMOVE) still means
    something to events.jsonl / the RTM / a test tag / a closed PR — the same
    "never reused" rule as a live row. `_existing_fr_ids` must read it via
    `read_fr_rows` (active AND removed), not `read_active_fr_rows`, or a QR
    fold on regeneration could silently reassign a retired id."""
    split = tmp_path / ".shipwright" / "planning" / "01-adopted"
    split.mkdir(parents=True)
    spec = split / "spec.md"
    spec.write_text(
        "# Specification — Demo / 01-adopted\n\n"
        "## Functional Requirements\n\n"
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Adopted | Sign in | Must | x | code | unit (inferred) |\n"
        "\n"
        "### Removed Requirements\n\n"
        "| FR-01.05 | Adopted | Old feature | Must | retired | code | unit (inferred) |\n"
        "\n"
        "## Constraints\n\n_No constraints inferred._\n",
        encoding="utf-8",
    )
    # Sanity: the fixture really does carry a removed row read_active_fr_rows
    # would drop, at an id HIGHER than the single live row.
    assert [r.id for r in read_active_fr_rows(spec.read_text(encoding="utf-8"))] == ["FR-01.01"]
    all_rows = read_fr_rows(spec.read_text(encoding="utf-8"))
    assert {r.id: r.status for r in all_rows} == {"FR-01.01": "active", "FR-01.05": "removed"}

    new_spec, _ = write_spec(
        tmp_path, project_name="Demo", split_name="01-adopted",
        product_description="x", features=FEATURES[:1],  # 1 feature: FR-01.01
        qr_items=["CI must pass."], constraints=[],
    )
    new_ids = [r.id for r in read_active_fr_rows(new_spec.read_text(encoding="utf-8"))]
    # The QR id must continue past the retired FR-01.05, not the naive FR-01.02.
    assert new_ids == ["FR-01.01", "FR-01.06"]
