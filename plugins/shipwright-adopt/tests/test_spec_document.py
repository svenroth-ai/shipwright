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
from fr_table_reader import read_active_fr_rows  # noqa: E402

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
    section = body.split("## Functional Requirements", 1)[1].split("## Quality", 1)[0]
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
