"""``rtm.collect_requirements`` reads every historical FR-table shape.

Replaces ``test_rtm_fr_table_redos.py``. That file pinned the private
``_FR_TABLE_RE`` — a positional regex whose "further columns, ignored" tail had
to be hand-hardened against CodeQL ``py/redos``. Campaign S4 deleted the regex:
the shared reader splits on unescaped pipes, so catastrophic backtracking is
gone by construction rather than by a careful pattern, and there is no private
attribute left to assert against.

What survives is the part that was always the real contract — the shapes an
adopted or greenfield spec can carry must all reach the RTM — asserted through
the PUBLIC seam instead of the regex. Plus the linearity probe, kept because
"the scan stays linear" is still a claim worth failing on.
"""

from __future__ import annotations

import time
from pathlib import Path

from scripts.lib.collectors.rtm import collect_requirements


def _spec(root: Path, split: str, body: str) -> None:
    d = root / ".shipwright" / "planning" / split
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")


def test_three_column_greenfield_row_parses(tmp_path: Path) -> None:
    _spec(tmp_path, "01-a", (
        "| ID | Requirement | Priority |\n"
        "|----|-------------|----------|\n"
        "| FR-01.01 | login | Must |\n"
    ))
    (req,) = collect_requirements(tmp_path)
    assert (req.id, req.text, req.priority) == ("FR-01.01", "login", "Must")


def test_five_column_adopt_row_takes_the_description_as_body(tmp_path: Path) -> None:
    _spec(tmp_path, "01-a", (
        "| ID | Name | Priority | Description | Source |\n"
        "|----|------|----------|-------------|--------|\n"
        "| FR-02.03 | /run | Should | Orchestrate the pipeline | spec.md |\n"
    ))
    (req,) = collect_requirements(tmp_path)
    assert (req.id, req.text, req.priority) == (
        "FR-02.03", "Orchestrate the pipeline", "Should",
    )


def test_six_column_adopt_row_still_takes_the_description(tmp_path: Path) -> None:
    # Adopt specs append e.g. a Confidence column after Source. Under the old
    # regex the extra column was matched-and-discarded positionally; now the
    # header names the body column, so appending columns is simply safe.
    _spec(tmp_path, "01-a", (
        "| ID | Name | Priority | Description | Source | Confidence |\n"
        "|----|------|----------|-------------|--------|------------|\n"
        "| FR-01.01 | /run | Must | Orchestrate | enrichment.json | 0.82 |\n"
    ))
    (req,) = collect_requirements(tmp_path)
    assert req.text == "Orchestrate"


def test_reordered_columns_no_longer_yield_zero_rows(tmp_path: Path) -> None:
    """The FV-1 trigger: the old regex pinned the priority to data column 3."""
    _spec(tmp_path, "01-a", (
        "| ID | Priority | Requirement | Layers |\n"
        "|----|----------|-------------|--------|\n"
        "| FR-06.01 | Must | Reordered but still a requirement | unit |\n"
    ))
    (req,) = collect_requirements(tmp_path)
    assert (req.id, req.text, req.priority) == (
        "FR-06.01", "Reordered but still a requirement", "Must",
    )


def test_non_fr_row_rejected(tmp_path: Path) -> None:
    _spec(tmp_path, "01-a", (
        "| ID | Requirement | Priority |\n"
        "| not-an-fr | x | Must |\n"
    ))
    assert collect_requirements(tmp_path) == []


def test_scan_stays_linear_on_many_blank_cells(tmp_path: Path) -> None:
    evil = "| FR-01.01 | x | Must |" + "   |" * 4000 + "x"
    _spec(tmp_path, "01-a", f"| ID | Requirement | Priority |\n{evil}\n")
    start = time.perf_counter()
    collect_requirements(tmp_path)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"scan took {elapsed:.2f}s — linearity regression"
