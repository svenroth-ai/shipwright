"""Tests for shared/scripts/tools/verifiers/common.py.

Covers the generic C1-C5 canon checks (used by future
``<phase>_checks.py`` modules) and the ADR integrity helpers imported
from the shipwright-check plan (F1 / F2 / F3).
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def _agent_docs_root(tmp: Path) -> Path:
    """Return canonical agent_docs subdir under tmp, creating parents."""
    p = tmp / ".shipwright" / "agent_docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


from tools.verifiers.common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_c4_decision_log_has_phase_adr,
    check_c5_changelog_unreleased_has_phase_entry,
    format_report,
    get_latest_phase_completed_event,
    read_events_jsonl,
    read_run_config,
    summarise,
)


# ---------------------------------------------------------------------------
# Result / severity
# ---------------------------------------------------------------------------

def test_check_result_is_skipped_when_ok_is_none():
    r = CheckResult(name="x", ok=None, severity=Severity.SKIPPED.value)
    assert r.is_skipped is True
    assert r.is_failure is False


def test_check_result_is_failure_only_on_error():
    ok = CheckResult(name="x", ok=True)
    warn = CheckResult(name="x", ok=False, severity=Severity.WARNING.value)
    err = CheckResult(name="x", ok=False, severity=Severity.ERROR.value)
    assert ok.is_failure is False
    assert warn.is_failure is True  # warnings are failures but don't block unless --strict
    assert err.is_failure is True


def test_summarise_counts_everything():
    results = [
        CheckResult("pass", ok=True),
        CheckResult("warn", ok=False, severity=Severity.WARNING.value),
        CheckResult("err", ok=False, severity=Severity.ERROR.value),
        CheckResult("skip", ok=None, severity=Severity.SKIPPED.value),
    ]
    summary = summarise(results)
    assert summary.passes == 1
    assert summary.warnings == 1
    assert summary.errors == 1
    assert summary.skipped == 1


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def test_read_run_config_missing_returns_empty(tmp_path):
    assert read_run_config(tmp_path) == {}


def test_read_run_config_malformed_returns_empty(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("not json")
    assert read_run_config(tmp_path) == {}


def test_read_events_jsonl_skips_malformed_lines(tmp_path):
    (tmp_path / "shipwright_events.jsonl").write_text(
        '{"type": "a"}\nnot json\n{"type": "b"}\n'
    )
    events = read_events_jsonl(tmp_path)
    assert [e["type"] for e in events] == ["a", "b"]


def test_get_latest_phase_completed_event_picks_newest():
    events = [
        {"type": "phase_completed", "phase": "build", "timestamp": "2026-04-14T10:00:00Z"},
        {"type": "phase_completed", "phase": "build", "timestamp": "2026-04-14T12:00:00Z"},
        {"type": "phase_completed", "phase": "test", "timestamp": "2026-04-14T13:00:00Z"},
    ]
    latest = get_latest_phase_completed_event(events, "build")
    assert latest is not None
    assert latest["timestamp"] == "2026-04-14T12:00:00Z"


def test_get_latest_phase_completed_matches_source_fallback():
    """Historical events used ``source`` instead of ``phase``; still match."""
    events = [
        {"type": "phase_completed", "source": "build", "timestamp": "2026-04-14T10:00:00Z"},
    ]
    assert get_latest_phase_completed_event(events, "build") is not None


# ---------------------------------------------------------------------------
# C1-C5 generic canon
# ---------------------------------------------------------------------------

def test_c1_passes_when_phase_completed_event_exists(tmp_path):
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "phase_completed", "phase": "project"}) + "\n"
    )
    r = check_c1_phase_event_recorded(tmp_path, "project")
    assert r.ok is True


def test_c1_fails_when_no_event(tmp_path):
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "task_created"}) + "\n"
    )
    r = check_c1_phase_event_recorded(tmp_path, "project")
    assert r.ok is False


# --- C1 fallbacks: iterate work_completed / decision-drop / phase_history ---

def test_c1_passes_for_iterate_with_work_completed_event(tmp_path):
    """Iterate records work_completed (per-change), not phase_completed —
    a work_completed event with source=iterate satisfies C1."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "work_completed", "source": "iterate",
            "ts": "2026-05-18T10:00:00Z",
        }) + "\n"
    )
    r = check_c1_phase_event_recorded(tmp_path, "iterate")
    assert r.ok is True
    assert "work_completed" in r.detail


def test_c1_iterate_work_completed_requires_iterate_source(tmp_path):
    """A work_completed event from another source does not satisfy C1."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "source": "build"}) + "\n"
    )
    r = check_c1_phase_event_recorded(tmp_path, "iterate")
    assert r.ok is False


def test_c1_passes_for_iterate_with_pending_decision_drop(tmp_path):
    """A pending decision-drop satisfies C1 for iterate (mirrors C4) —
    reachable even with no event log at all."""
    drops = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iterate-20260518-x_001.json").write_text("{}")
    r = check_c1_phase_event_recorded(tmp_path, "iterate")
    assert r.ok is True
    assert "decision-drop" in r.detail


def test_c1_iterate_decision_drop_ignores_underscore_prefixed(tmp_path):
    """Underscore-prefixed files under decision-drops/ are not pending ADRs."""
    drops = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "_index.json").write_text("{}")
    r = check_c1_phase_event_recorded(tmp_path, "iterate")
    assert r.ok is False


def test_c1_passes_via_phase_history_terminal_outcome(tmp_path):
    """Adopt records completed phases in run_config.phase_history with a
    terminal outcome instead of emitting a phase_completed event."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "task_created"}) + "\n"
    )
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {
            "build": [{"run_id": "adopt-x", "outcome": "adopted"}],
        }})
    )
    r = check_c1_phase_event_recorded(tmp_path, "build")
    assert r.ok is True
    assert "phase_history" in r.detail


def test_c1_phase_history_accepts_adopted_skipped(tmp_path):
    """`adopted-skipped` — adopt's outcome for a phase with nothing to run —
    is a terminal phase_history outcome."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {
            "test": [{"run_id": "adopt-x", "outcome": "adopted-skipped"}],
        }})
    )
    r = check_c1_phase_event_recorded(tmp_path, "test")
    assert r.ok is True


def test_c1_phase_history_fallback_works_with_empty_event_log(tmp_path):
    """The phase_history fallback must run even when shipwright_events.jsonl
    is entirely absent — adopted projects record no events."""
    # No shipwright_events.jsonl written at all.
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {
            "changelog": [{"run_id": "cl-x", "outcome": "tagged"}],
        }})
    )
    r = check_c1_phase_event_recorded(tmp_path, "changelog")
    assert r.ok is True


def test_c1_phase_history_non_terminal_outcome_still_fails(tmp_path):
    """A non-terminal phase_history outcome does not satisfy C1."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {
            "build": [{"run_id": "x", "outcome": "in_progress"}],
        }})
    )
    r = check_c1_phase_event_recorded(tmp_path, "build")
    assert r.ok is False


def test_c1_still_fails_with_no_evidence(tmp_path):
    """No event, no iterate fallback, no terminal phase_history → FAIL."""
    r = check_c1_phase_event_recorded(tmp_path, "build")
    assert r.ok is False


def test_c2_passes_when_dashboard_mentions_phase(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "## Phases\n\n- project: complete\n"
    )
    r = check_c2_dashboard_reflects_phase(tmp_path, "project")
    assert r.ok is True


def test_c2_warns_when_phase_absent(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("## Phases\n")
    r = check_c2_dashboard_reflects_phase(tmp_path, "project")
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


def test_c3_passes_when_handoff_is_fresh(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")
    r = check_c3_session_handoff_fresh_after_phase(tmp_path, "project")
    assert r.ok is True


def test_c3_warns_when_handoff_stale(tmp_path):
    import os
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    handoff = tmp_path / ".shipwright" / "agent_docs" / "session_handoff.md"
    handoff.write_text("old")
    old = time.time() - 7200
    os.utime(handoff, (old, old))
    r = check_c3_session_handoff_fresh_after_phase(tmp_path, "project", max_age_seconds=600)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


def test_c4_passes_when_adr_mentions_phase_in_title(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Project initialization decision\n- **Status:** accepted\n"
    )
    r = check_c4_decision_log_has_phase_adr(tmp_path, "project")
    assert r.ok is True


def test_c4_fails_when_no_matching_adr(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Completely unrelated thing\n"
    )
    r = check_c4_decision_log_has_phase_adr(tmp_path, "project")
    assert r.ok is False


def test_c4_passes_for_iterate_with_pending_decision_drop(tmp_path):
    """H decision-drop pattern: an iterate's ADR lives as a JSON drop until
    /shipwright-changelog aggregation. A pending drop satisfies C4 even
    before decision_log.md carries the numbered ADR."""
    drops = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iterate-20260515-x_001.json").write_text("{}")
    r = check_c4_decision_log_has_phase_adr(tmp_path, "iterate")
    assert r.ok is True
    assert "decision-drop" in r.detail


def test_c4_non_iterate_phase_ignores_decision_drops(tmp_path):
    """The decision-drop fast-path is iterate-only — other phases still
    require their ADR in decision_log.md."""
    drops = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iterate-x_001.json").write_text("{}")
    r = check_c4_decision_log_has_phase_adr(tmp_path, "project")
    assert r.ok is False


def test_c5_passes_when_unreleased_category_has_bullet(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- New project\n"
    )
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "project", "Added")
    assert r.ok is True


def test_c5_fails_when_category_empty(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- bug\n"
    )
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "project", "Added")
    assert r.ok is False


def test_c5_warns_when_changelog_missing(tmp_path):
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "project", "Added")
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


# --- C5 drop-directory model (write_changelog_drop.py) ---

def _make_changelog_drop(tmp_path, category: str, filename: str) -> None:
    """Stage a CHANGELOG-unreleased.d/<category>/<filename> drop file."""
    d = tmp_path / "CHANGELOG-unreleased.d" / category
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text("- a staged changelog bullet\n", encoding="utf-8")


def test_c5_passes_via_changelog_drop_directory(tmp_path):
    """Drop-directory model: [Unreleased] empty between releases, entries
    staged as files under CHANGELOG-unreleased.d/<category>/."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n"
    )
    _make_changelog_drop(tmp_path, "Added", "iterate-x_001.md")
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "iterate", "Added")
    assert r.ok is True
    assert "drop file" in r.detail


def test_c5_drop_directory_is_category_agnostic(tmp_path):
    """A drop in a different category than the one C5 was called with still
    satisfies C5 — a bug-only iterate writes only a Fixed/ drop."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n"
    )
    _make_changelog_drop(tmp_path, "Fixed", "iterate-x_001.md")
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "iterate", "Added")
    assert r.ok is True


def test_c5_drop_directory_works_when_changelog_absent(tmp_path):
    """The drop directory is authoritative independent of CHANGELOG.md state."""
    _make_changelog_drop(tmp_path, "Added", "iterate-x_001.md")
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "iterate", "Added")
    assert r.ok is True


def test_c5_inline_bullets_win_without_drop_directory(tmp_path):
    """Existing behaviour preserved: an inline bullet satisfies C5 with no
    drop directory present."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- New project\n"
    )
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "project", "Added")
    assert r.ok is True
    assert "bullet" in r.detail


def test_c5_ignores_gitkeep_in_drop_directory(tmp_path):
    """A drop dir containing only a .gitkeep placeholder does not satisfy C5."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n"
    )
    d = tmp_path / "CHANGELOG-unreleased.d" / "Added"
    d.mkdir(parents=True)
    (d / ".gitkeep").write_text("")
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "iterate", "Added")
    assert r.ok is False


def test_c5_fails_when_neither_inline_nor_drops(tmp_path):
    """No inline bullet in the target category and no drop file → FAIL."""
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- bug\n"
    )
    r = check_c5_changelog_unreleased_has_phase_entry(tmp_path, "project", "Added")
    assert r.ok is False


# ---------------------------------------------------------------------------
# ADR integrity helpers (F1 / F2 / F3)
# ---------------------------------------------------------------------------

def test_f1_adr_ids_sequential_passes(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: First\n### ADR-002: Second\n### ADR-003: Third\n"
    )
    r = check_adr_ids_sequential(tmp_path)
    assert r.ok is True


def test_f1_adr_ids_detects_duplicates(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: First\n### ADR-001: Duplicate\n"
    )
    r = check_adr_ids_sequential(tmp_path)
    assert r.ok is False
    assert "duplicate" in r.detail.lower()


def test_f1_adr_ids_warns_on_gaps(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: First\n### ADR-003: Third\n"
    )
    r = check_adr_ids_sequential(tmp_path)
    # Gaps are warnings: ok=True, severity=warning
    assert r.ok is True
    assert r.severity == Severity.WARNING.value


def test_f2_adr_status_valid_passes(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: A\n- **Status:** accepted\n"
    )
    r = check_adr_status_valid(tmp_path)
    assert r.ok is True


def test_f2_adr_status_rejects_bogus(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: A\n- **Status:** totally-made-up\n"
    )
    r = check_adr_status_valid(tmp_path)
    assert r.ok is False


def test_f3_supersession_resolved(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-001: Old\n- **Status:** superseded\n\n"
        "### ADR-002: New\n- **Status:** accepted\n- **Supersedes:** ADR-001\n"
    )
    r = check_adr_supersession_exists(tmp_path)
    assert r.ok is True


def test_f3_supersession_dangling(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-002: New\n- **Supersedes:** ADR-999\n"
    )
    r = check_adr_supersession_exists(tmp_path)
    assert r.ok is False
    assert "ADR-999" in r.detail


# ---------------------------------------------------------------------------
# format_report — smoke test
# ---------------------------------------------------------------------------

def test_format_report_renders_without_errors():
    results = [
        CheckResult("pass check", ok=True, detail="fine"),
        CheckResult("skip check", ok=None, severity=Severity.SKIPPED.value, detail="stub"),
    ]
    report = format_report("test title", results)
    assert "pass check" in report
    assert "skip check" in report
    assert "test title" in report
