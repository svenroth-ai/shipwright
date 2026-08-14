"""QR-/C- id spaces are retired from the greenfield spec-generation reference.

Pair of trg-a51e7502 (the adopt half; that producer mints its own ids and is
covered separately). This is the GREENFIELD entry path: `/shipwright-project`
follows `spec-generation.md` when it writes a fresh split's `spec.md`.

Before this change the reference instructed the spec writer to mint
`QR-{NN}.{YY}` (quality requirement) and `C-{NN}.{YY}` (constraint) ids in a
`## 3. Quality Requirements` / `## 4. Constraints` section. Nothing in the
framework read either id — not `fr_table_reader` (canonical id regex is
`FR-\\d{2}\\.\\d{2}` only), not compliance, not the RTM. A numbered row nothing
can address looked referenceable and was not.

Operator decision 2026-08-14: one requirement id space (`FR`). Quality targets
become ordinary FR rows in the existing table; Constraints keep their section
but lose their ids (prose, since they are not testable requirements). The
`FR_TABLE_HEADER` shape (`shared/scripts/lib/fr_table_shape.py`) is
UNCHANGED — no new column — see `integration-tests/test_fr_table_shape_convergence.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_PATH = (
    REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project"
    / "references" / "spec-generation.md"
)

sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_table_reader import read_active_fr_rows  # noqa: E402


def _reference_text() -> str:
    return REFERENCE_PATH.read_text(encoding="utf-8")


def _worked_example() -> str:
    """The fenced `Example: Filled spec.md` code block."""
    text = _reference_text()
    marker = text.index("## Example: Filled spec.md")
    fence_start = text.index("```markdown", marker) + len("```markdown")
    fence_end = text.index("```", fence_start)
    return text[fence_start:fence_end]


def test_reference_no_longer_mints_qr_or_c_ids() -> None:
    """The old id-schema examples and section tables are gone. `C-{NN}.{YY}`
    still appears exactly once — inside the prose explaining WHY constraints
    have no id — which `test_no_line_mints_a_live_qr_or_c_id` pins."""
    text = _reference_text()
    retired_patterns = (
        "QR-{NN}",
        "`QR-01.01`",
        "| ID | Requirement | Category |",
        "| ID | Constraint | Type |",
        "C-{NN}.01",
    )
    present = [p for p in retired_patterns if p in text]
    assert present == [], f"reference still instructs a retired id shape: {present}"
    assert not re.search(r"^#{1,6}\s*\d+\.\s*Quality Requirements", text, re.M), (
        "a Quality Requirements section survived under some other number"
    )
    assert text.count("C-{NN}") == 1, (
        "C-{NN} should appear exactly once, in the retirement explanation"
    )


def test_no_line_mints_a_live_qr_or_c_id() -> None:
    """`QR-`/`C-` may appear only inside the prose explaining they are retired,
    never as a live id anywhere — table row (`| QR-01.01 |`), backtick example
    (`` `C-01.01` ``), or bare mention. Unanchored on purpose: the most likely
    reintroduction is a markdown table cell, where the id is never adjacent to
    a backtick or pipe."""
    for lineno, line in enumerate(_reference_text().splitlines(), start=1):
        if re.search(r"QR-\d|\bC-\d", line):
            raise AssertionError(
                f"line {lineno} still mints a live QR-/C- id, not just names "
                f"the retired space: {line.strip()!r}"
            )


def test_constraints_render_as_prose_bullets() -> None:
    text = _reference_text()
    assert "## 3. Constraints\n\n**Technical:**" in text


def test_worked_example_folds_quality_targets_into_the_fr_table() -> None:
    """A spec built per the updated reference parses quality rows as ordinary
    FR rows via the shared FR-table reader — the actual consumer this whole
    change exists to make honest."""
    rows = {row.id: row for row in read_active_fr_rows(_worked_example())}

    assert "FR-01.08" in rows, "quality-target row (response time) missing"
    assert "FR-01.09" in rows, "quality-target row (password storage) missing"

    response_time = rows["FR-01.08"]
    assert response_time.priority == "Must"
    assert "500ms" in response_time.text

    password_storage = rows["FR-01.09"]
    assert password_storage.priority == "Must"
    assert "bcrypt" in password_storage.text

    # The full active set, pinned — catches drift in the worked example
    # (an added/removed/renumbered row) that a per-id `in` check would miss.
    assert set(rows) == {f"FR-01.{n:02d}" for n in (1, 2, 3, 4, 5, 6, 8, 9)}


def test_worked_example_still_carries_the_canonical_fr_header() -> None:
    """No new column: quality targets fold into the SAME table shape.

    Duplicates part of `integration-tests/test_fr_table_shape_convergence.py`
    deliberately — that root does not run in the same pytest invocation as
    this plugin's `tests/` (ADR-044, one test root per process), so this
    plugin keeps its own copy of the invariant rather than depending on a
    sibling root to catch a regression here.
    """
    from fr_table_shape import FR_TABLE_HEADER

    assert FR_TABLE_HEADER in _worked_example()
