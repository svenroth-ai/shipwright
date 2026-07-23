"""iterate-2026-07-23-tests-skipped-tracking — the build dashboard reads and
renders a work_completed event's ``tests.skipped`` count.

Before this iterate the dashboard rendered only ``passed/total``, so a green run
with host-gated skips either looked like a partial pass (skips folded into total)
or lost the disclosure entirely (executed totals). The renderer now appends
`` (N skipped)`` when an explicit positive skip count is present, and leaves
legacy rows (no skipped key) byte-unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from tools.update_build_dashboard import generate_dashboard  # noqa: E402


def _write_min_project(project_root: Path, *, events: list[dict]) -> None:
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete",
                    "completed_steps": ["project", "plan", "build", "test"],
                    "current_step": None}),
        encoding="utf-8",
    )
    (project_root / "shipwright_build_config.json").write_text(
        json.dumps({"splits": []}), encoding="utf-8",
    )
    (project_root / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8",
    )


def _iterate_event(**tests) -> dict:
    return {
        "type": "work_completed", "source": "iterate",
        "ts": "2026-07-23T12:00:00+00:00", "intent": "change",
        "description": "green run with host-gated skips",
        "tests": tests, "commit": "abcdef0123456789",
        "affected_frs": ["FR-01.10"],
    }


def test_recent_changes_renders_explicit_skip_count(tmp_path: Path) -> None:
    """Executed totals (passed==total) + explicit skips: disclosure survives."""
    _write_min_project(tmp_path, events=[_iterate_event(passed=831, total=831, skipped=3)])
    rendered = generate_dashboard(tmp_path)
    assert "831/831 (3 skipped)" in rendered


def test_recent_changes_folded_skips_render_count(tmp_path: Path) -> None:
    """Fold-into-total (passed<total) + explicit skips: the count is shown."""
    _write_min_project(tmp_path, events=[_iterate_event(passed=828, total=831, skipped=3)])
    rendered = generate_dashboard(tmp_path)
    assert "828/831 (3 skipped)" in rendered


def test_legacy_row_without_skipped_unchanged(tmp_path: Path) -> None:
    """No skipped key → no suffix (byte-unchanged legacy rendering)."""
    _write_min_project(tmp_path, events=[_iterate_event(passed=7, total=7)])
    rendered = generate_dashboard(tmp_path)
    assert "7/7" in rendered
    assert "skipped" not in rendered


def test_zero_skips_render_no_suffix(tmp_path: Path) -> None:
    """An explicit skipped=0 adds nothing (only positive counts disclose)."""
    _write_min_project(tmp_path, events=[_iterate_event(passed=10, total=10, skipped=0)])
    rendered = generate_dashboard(tmp_path)
    assert "10/10" in rendered
    assert "skipped" not in rendered


def test_build_history_row_renders_explicit_skip_count(tmp_path: Path) -> None:
    """The Build History render site (source=="build") mirrors Recent Changes —
    a build event's explicit skip count is disclosed there too."""
    build_event = {
        "type": "work_completed", "source": "build",
        "ts": "2026-07-23T12:00:00+00:00", "split": "01-foundation",
        "section": "01-setup", "commit": "abcdef0123456789",
        "affected_frs": ["FR-01.10"],
        "tests": {"passed": 40, "total": 43, "skipped": 3},
    }
    _write_min_project(tmp_path, events=[build_event])
    rendered = generate_dashboard(tmp_path)
    assert "## Build History" in rendered
    assert "40/43 (3 skipped)" in rendered
