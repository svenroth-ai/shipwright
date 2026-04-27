"""Verify validate_adoption emits soft-check warnings (3.3).

Hard errors still hard-fail validation. Soft-check warnings are
informational — surfaced but non-blocking — and meant to flag
plausibility issues like "200 commits, only 1 ADR" that an adoption
artifact-presence check otherwise misses.
"""

from __future__ import annotations

import json
from pathlib import Path

from checks.validate_adoption import validate


def _make_minimum_valid(root: Path, *, decision_log_body: str | None = None) -> None:
    """Lay down all artifacts validate_adoption requires for ok=True."""
    for name in (
        "shipwright_run_config.json",
        "shipwright_project_config.json",
        "shipwright_plan_config.json",
        "shipwright_build_config.json",
        "shipwright_compliance_config.json",
    ):
        (root / name).write_text("{}", encoding="utf-8")
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "architecture.md").write_text("# arch\n", encoding="utf-8")
    (root / ".shipwright" / "agent_docs" / "conventions.md").write_text("# conv\n", encoding="utf-8")
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("# dash\n", encoding="utf-8")
    body = decision_log_body if decision_log_body is not None else "# log\n\n## ADR-0001: x\n"
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(body, encoding="utf-8")
    (root / ".shipwright" / "planning" / "01-adopted").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "planning" / "01-adopted" / "spec.md").write_text(
        "# spec\n\nFR-01.01 placeholder.\n", encoding="utf-8",
    )
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "adopted"}) + "\n", encoding="utf-8"
    )
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"UserPromptSubmit": [{"command": "uv run suggest_iterate.py"}]}}),
        encoding="utf-8",
    )
    (root / ".shipwright" / "adopt").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "adopt" / "review.md").write_text("status: skipped", encoding="utf-8")


def _write_snapshot(root: Path, *, commits_total: int) -> None:
    snap_dir = root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / "snapshot.json"
    snap.write_text(json.dumps({"git": {"commits_total": commits_total}}), encoding="utf-8")


def test_validate_returns_dict_with_errors_and_warnings(tmp_path: Path) -> None:
    """validate() now returns a dict (was list[str]) with both errors and warnings."""
    _make_minimum_valid(tmp_path)
    result = validate(tmp_path)
    assert isinstance(result, dict)
    assert "errors" in result
    assert "warnings" in result
    assert result["errors"] == []


def test_few_adrs_for_large_repo_warns(tmp_path: Path) -> None:
    """200 commits + 1 ADR triggers the historical-data-missing warning."""
    _make_minimum_valid(tmp_path)
    _write_snapshot(tmp_path, commits_total=200)
    result = validate(tmp_path)
    assert result["errors"] == []
    assert any("ADRs" in w or "historical" in w for w in result["warnings"]), result


def test_few_adrs_for_small_repo_no_warning(tmp_path: Path) -> None:
    """Under 50 commits, the few-ADRs check is silent."""
    _make_minimum_valid(tmp_path)
    _write_snapshot(tmp_path, commits_total=10)
    result = validate(tmp_path)
    assert not any("historical" in w for w in result["warnings"])


def test_many_adrs_for_large_repo_no_warning(tmp_path: Path) -> None:
    """The check fires only on count<3 — a 4-ADR log on a 200-commit repo is fine."""
    rich = "# log\n\n" + "\n\n".join(f"## ADR-{i:04d}: x\n" for i in range(1, 5))
    _make_minimum_valid(tmp_path, decision_log_body=rich)
    _write_snapshot(tmp_path, commits_total=200)
    result = validate(tmp_path)
    assert not any("historical" in w for w in result["warnings"])


def test_no_snapshot_does_not_crash(tmp_path: Path) -> None:
    """Snapshot may legitimately be absent (e.g. analyze_codebase didn't run);
    validate must not error out — it just skips the soft-check."""
    _make_minimum_valid(tmp_path)
    result = validate(tmp_path)
    assert result["errors"] == []
    # No "historical" warning since we have no commit count to compare against
    assert not any("historical" in w for w in result["warnings"])
