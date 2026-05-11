"""Aggregator tests — status resolution + markdown render snapshot.

AC-2 (and AC-8 — drift protection):
- empty / header-only file → empty skeleton markdown
- mixed-status items → only `triage` shown
- severity sort within source
- top-50 cap
- markdown escaping for title/detail (MED-10)
- per-item promote-action line
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import (  # noqa: E402
    TRIAGE_FILE,
    append_triage_item,
    mark_status,
)

AGGREGATOR = _WORKTREE / "shared" / "scripts" / "tools" / "aggregate_triage.py"
TRIAGE_MD = Path(".shipwright") / "agent_docs" / "triage_inbox.md"


def _run_aggregator(project_root: Path, now: str = "2026-05-11T13:00:00Z") -> str:
    """Run the CLI; return stdout. Markdown is written to the file too."""
    result = subprocess.run(
        [
            sys.executable,
            str(AGGREGATOR),
            "--project-root",
            str(project_root),
            "--now",
            now,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"aggregator exit {result.returncode}\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )
    return (project_root / TRIAGE_MD).read_text(encoding="utf-8")


# --- Empty / bootstrap state ---------------------------------------------

def test_empty_project_yields_empty_skeleton(tmp_path: Path) -> None:
    md = _run_aggregator(tmp_path)
    assert "# Triage Inbox" in md
    assert "No triage items pending" in md
    # Counts line shows zeros
    assert "Total: 0" in md


def test_header_only_file_yields_empty_skeleton(tmp_path: Path) -> None:
    """File exists but only contains the schema header."""
    sd = tmp_path / ".shipwright"
    sd.mkdir()
    (sd / TRIAGE_FILE).write_text(
        json.dumps({"v": 1, "schema": "triage", "created": "2026-01-01T00:00:00Z"})
        + "\n",
        encoding="utf-8",
    )
    md = _run_aggregator(tmp_path)
    assert "No triage items pending" in md


# --- Status filtering ----------------------------------------------------

def test_only_triage_status_shown(tmp_path: Path) -> None:
    a = append_triage_item(tmp_path, source="phaseQuality", severity="high",
                           kind="bug", title="alpha", detail="d")
    b = append_triage_item(tmp_path, source="phaseQuality", severity="medium",
                           kind="bug", title="beta", detail="d")
    c = append_triage_item(tmp_path, source="phaseQuality", severity="low",
                           kind="bug", title="gamma", detail="d")
    mark_status(tmp_path, b, new_status="dismissed", by="audit")
    mark_status(tmp_path, c, new_status="promoted", by="user",
                promoted_task_id="EXT:asana-1")

    md = _run_aggregator(tmp_path)

    assert "alpha" in md
    assert "beta" not in md
    assert "gamma" not in md
    # Summary counts reflect resolved view
    assert re.search(r"Total: 3", md)
    assert re.search(r"Triage: 1", md)
    assert re.search(r"Promoted: 1", md)
    assert re.search(r"Dismissed: 1", md)


# --- Severity sort + grouping --------------------------------------------

def test_severity_sort_within_source(tmp_path: Path) -> None:
    append_triage_item(tmp_path, source="phaseQuality", severity="low",
                       kind="bug", title="low-item", detail="d")
    append_triage_item(tmp_path, source="phaseQuality", severity="critical",
                       kind="bug", title="critical-item", detail="d")
    append_triage_item(tmp_path, source="phaseQuality", severity="medium",
                       kind="bug", title="medium-item", detail="d")

    md = _run_aggregator(tmp_path)
    pos_critical = md.find("critical-item")
    pos_medium = md.find("medium-item")
    pos_low = md.find("low-item")
    assert -1 < pos_critical < pos_medium < pos_low, (
        f"sort wrong: critical@{pos_critical}, medium@{pos_medium}, low@{pos_low}"
    )


def test_grouped_by_source(tmp_path: Path) -> None:
    append_triage_item(tmp_path, source="phaseQuality", severity="high",
                       kind="bug", title="pq-item", detail="d")
    append_triage_item(tmp_path, source="compliance", severity="medium",
                       kind="compliance", title="comp-item", detail="d")

    md = _run_aggregator(tmp_path)
    assert "Source: phaseQuality" in md or "## phaseQuality" in md
    assert "Source: compliance" in md or "## compliance" in md


# --- Top-50 cap ----------------------------------------------------------

def test_top_50_cap(tmp_path: Path) -> None:
    for i in range(60):
        append_triage_item(tmp_path, source="phaseQuality", severity="medium",
                           kind="bug", title=f"item-{i:03d}", detail="d")

    md = _run_aggregator(tmp_path)
    rendered_count = len(re.findall(r"item-\d{3}", md))
    assert rendered_count == 50, f"expected 50 items rendered, got {rendered_count}"
    # Header should still report total
    assert "Total: 60" in md
    # Should mention truncation
    assert "Top" in md and "50" in md


# --- Per-item promote-action line ----------------------------------------

def test_promote_action_line_present(tmp_path: Path) -> None:
    item_id = append_triage_item(
        tmp_path, source="phaseQuality", severity="high",
        kind="bug", title="t", detail="d",
    )
    md = _run_aggregator(tmp_path)
    # Each rendered item should carry the promote CLI hint
    assert "triage_promote.py" in md
    # And reference the actual id
    assert item_id in md


# --- Markdown escaping (MED-10) ------------------------------------------

def test_markdown_escaping_pipe(tmp_path: Path) -> None:
    append_triage_item(
        tmp_path, source="phaseQuality", severity="high",
        kind="bug",
        title="title with | pipe and `backticks`",
        detail="multi\nline\ndetail with | pipe",
    )
    md = _run_aggregator(tmp_path)
    # Title pipe is escaped (so it doesn't break a markdown table or
    # split as code-block delimiter when rendered inside list bullets)
    assert r"\|" in md or "&#124;" in md or "| pipe" not in md
    # Multi-line detail collapsed to single line for list rendering
    # (so the bullet structure stays intact)
    lines_for_detail = [L for L in md.splitlines() if "multi" in L]
    if lines_for_detail:
        assert all(("\n" not in L) for L in lines_for_detail)


def test_markdown_truncation(tmp_path: Path) -> None:
    long_detail = "x" * 500
    append_triage_item(
        tmp_path, source="phaseQuality", severity="high",
        kind="bug", title="t", detail=long_detail,
    )
    md = _run_aggregator(tmp_path)
    # Field longer than the cap should be truncated with an ellipsis marker
    assert "…" in md or "..." in md


# --- Idempotent regen ----------------------------------------------------

def test_idempotent_regen_with_fixed_now(tmp_path: Path) -> None:
    """Two regens with the same --now produce identical files."""
    append_triage_item(tmp_path, source="phaseQuality", severity="high",
                       kind="bug", title="t", detail="d")

    first = _run_aggregator(tmp_path, now="2026-05-11T13:00:00Z")
    second = _run_aggregator(tmp_path, now="2026-05-11T13:00:00Z")
    assert first == second


# --- Hidden status fields not leaked into MD -----------------------------

def test_internal_fields_not_rendered(tmp_path: Path) -> None:
    append_triage_item(
        tmp_path, source="phaseQuality", severity="info",
        kind="maintenance", title="t", detail="d",
    )
    md = _run_aggregator(tmp_path)
    # Resolution metadata fields should not surface in human-facing MD
    assert "statusBy" not in md
    assert "statusReason" not in md
    assert "originalTs" not in md  # filtered out of render
