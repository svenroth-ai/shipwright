"""Regression test: build dashboard renders pipe/newline-laden event fields
into well-formed markdown tables.

Reproduces the bug observed in the shipwright-webui repo where a literal
``|`` in an iterate event's ``description`` shifted the Recent-Changes
row by 3 columns. The fix wraps every cell in
``markdown_table.escape_cell()``; this test drives the renderer with a
synthetic event and asserts the rendered row, when split on un-escaped
``|``, has exactly 6 data cells.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Imported after sys.path mutation so the parent-package layout matches the
# canonical import path used by callers of update_build_dashboard.py.
from tools.update_build_dashboard import generate_dashboard  # noqa: E402


# Regex that splits on a `|` NOT preceded by a `\\`. The escape_cell
# helper renders `|` as `\\|` and a literal backslash as `\\\\`, so a
# single-backslash lookbehind is unambiguous for any cell we produce.
_UN_ESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _write_min_project(project_root: Path, *, events: list[dict]) -> None:
    """Materialise the minimum on-disk shape ``generate_dashboard`` needs."""
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "completed_steps": ["project", "plan", "build", "test"],
            "current_step": None,
        }),
        encoding="utf-8",
    )
    (project_root / "shipwright_build_config.json").write_text(
        json.dumps({"splits": []}),
        encoding="utf-8",
    )
    (project_root / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _recent_changes_rows(rendered: str) -> list[str]:
    """Return the data rows of the Recent Changes table.

    Skips the heading row and the separator row.
    """
    in_table = False
    rows: list[str] = []
    for line in rendered.splitlines():
        if line.startswith("## Recent Changes"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                # Table ended.
                if rows:
                    break
                continue
            # Skip header and separator (`| ----- |...`).
            if line.lstrip("| ").startswith("Type") or set(line) <= set("|-: "):
                continue
            rows.append(line)
    return rows


def test_recent_changes_row_has_six_cells_when_description_contains_pipes(
    tmp_path: Path,
) -> None:
    """The bug repro: description = "A (x|y|z) B" must not shift columns."""
    event = {
        "type": "work_completed",
        "source": "iterate",
        "ts": "2026-05-20T12:00:00+00:00",
        "intent": "change",
        "description": "A (x|y|z) B",
        "tests": {"passed": 7, "total": 7, "new": 1},
        "commit": "abcdef0123456789",
        "affected_frs": ["FR-1.1"],
    }
    _write_min_project(tmp_path, events=[event])

    rendered = generate_dashboard(tmp_path)
    rows = _recent_changes_rows(rendered)
    assert rows, "Recent Changes table should have at least one data row"

    [row] = rows
    segments = _UN_ESCAPED_PIPE.split(row)

    # `| A | B | C | D | E | F |` → 8 segments: empty + 6 cells + empty.
    assert len(segments) == 8, (
        f"Expected 8 split segments (6 data cells), got {len(segments)}: "
        f"{segments!r}\nFull row: {row!r}"
    )
    assert segments[0] == ""
    assert segments[-1] == ""

    cells = [s.strip() for s in segments[1:-1]]
    # Order from update_build_dashboard.py: intent, desc, tests, commit, frs, date
    assert cells[0] == "change"
    # The pipes in description must survive as `\|` in the rendered cell.
    assert cells[1] == "A (x\\|y\\|z) B"
    assert cells[2] == "+1 new, 7/7"
    assert cells[3] == "abcdef0"
    assert cells[4] == "FR-1.1"
    assert cells[5] == "2026-05-20"


def test_recent_changes_row_stays_single_line_when_description_has_newline(
    tmp_path: Path,
) -> None:
    """Newlines in event fields must collapse to a single space."""
    event = {
        "type": "work_completed",
        "source": "iterate",
        "ts": "2026-05-20T12:00:00+00:00",
        "intent": "fix",
        "description": "first line\nsecond line",
        "tests": {"passed": 5, "total": 5},
        "commit": "0000111122223333",
        "affected_frs": [],
    }
    _write_min_project(tmp_path, events=[event])

    rendered = generate_dashboard(tmp_path)
    rows = _recent_changes_rows(rendered)
    assert len(rows) == 1, (
        f"Expected exactly 1 physical row in Recent Changes, got {len(rows)}: "
        f"{rows!r}"
    )

    segments = _UN_ESCAPED_PIPE.split(rows[0])
    assert len(segments) == 8
    cells = [s.strip() for s in segments[1:-1]]
    assert cells[1] == "first line second line"


def test_recent_changes_intent_with_pipe_is_escaped(tmp_path: Path) -> None:
    """Defence-in-depth: a literal pipe in intent must not break the row.

    (Real events shouldn't have a pipe in `intent`, but the renderer
    must not assume that — every event-derived cell goes through
    `escape_cell`.)"""
    event = {
        "type": "work_completed",
        "source": "iterate",
        "ts": "2026-05-20T12:00:00+00:00",
        "intent": "feat|hack",  # synthetic — escape_cell must handle
        "description": "ok",
        "tests": {"passed": 1, "total": 1},
        "commit": "f0f0f0f0",
        "affected_frs": [],
    }
    _write_min_project(tmp_path, events=[event])

    rendered = generate_dashboard(tmp_path)
    rows = _recent_changes_rows(rendered)
    [row] = rows
    segments = _UN_ESCAPED_PIPE.split(row)
    assert len(segments) == 8
    assert [s.strip() for s in segments[1:-1]][0] == "feat\\|hack"
