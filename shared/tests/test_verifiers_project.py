"""Tests for shared/scripts/tools/verifiers/project_checks.py + common helpers.

Exercises the iterate 12.1 project-phase canon dispatcher plus the
``check_phase_history_has_run`` common helper (added in 12.1 for use by
every phase-specific verifier module going forward).

The FR-01.02 gate-specific tests (``check_basis_forbids_assumed``,
``check_criteria_free_of_implementation_detail``, ``check_no_empty_split``,
``check_starting_guidance_present``) live in
``test_project_gate_basis_and_guidance.py`` and
``test_project_gate_no_empty_split.py`` — split out to stay under the
shared bloat gate's 300-line limit (req3-06-enforcement-mono sub-iterate e2).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verifiers.common import (  # noqa: E402
    Severity,
    check_phase_history_has_run,
)
from tools.verifiers.project_checks import (  # noqa: E402
    check_manifest_splits_match_dirs,
    check_project_config_status_complete,
    run_project_checks,
)

from _project_check_fixtures import _write_grill_trace, seed_canon_project  # noqa: E402


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def test_project_config_status_complete_passes(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"})
    )
    r = check_project_config_status_complete(tmp_path)
    assert r.ok is True


def test_project_config_status_in_progress_fails(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "in_progress"})
    )
    r = check_project_config_status_complete(tmp_path)
    assert r.ok is False


def test_project_config_missing_fails(tmp_path):
    r = check_project_config_status_complete(tmp_path)
    assert r.ok is False


def test_manifest_splits_match_dirs_passes_when_aligned(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}, {"name": "02-dashboard"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "02-dashboard").mkdir()
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is True


def test_manifest_splits_match_dirs_warns_on_missing_dir(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}, {"name": "02-dashboard"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert "02-dashboard" in r.detail


def test_manifest_splits_match_dirs_warns_on_extra_dir(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "99-rogue").mkdir()
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is False
    assert "99-rogue" in r.detail


def test_manifest_splits_match_dirs_ignores_iterate_subdir(tmp_path):
    """.shipwright/planning/iterate/ is where iterate specs live and should not
    count as an 'extra' split."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-auth"}]})
    )
    (tmp_path / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir()
    r = check_manifest_splits_match_dirs(tmp_path)
    assert r.ok is True


# ---------------------------------------------------------------------------
# check_phase_history_has_run (common helper)
# ---------------------------------------------------------------------------

def test_phase_history_check_passes_when_run_id_present(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {
            "project": [{"run_id": "project-x", "date": "2026-04-14"}],
        },
    }))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is True


def test_phase_history_check_fails_when_run_id_missing(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {"project": [{"run_id": "other"}]},
    }))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is False


def test_phase_history_check_fails_when_bucket_missing(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {},
    }))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is False


def test_phase_history_check_fails_when_phase_history_field_missing(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    r = check_phase_history_has_run(tmp_path, "project", "project-x")
    assert r.ok is False


def test_phase_history_check_skips_when_run_id_blank(tmp_path):
    """Callers that don't pass --run-id get a neutral pass — the check
    is about matching a specific id, not about the bucket existing."""
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    r = check_phase_history_has_run(tmp_path, "project", "")
    assert r.ok is True
    assert "skipped" in r.detail.lower()


# ---------------------------------------------------------------------------
# run_project_checks — orchestrator
# ---------------------------------------------------------------------------

def test_run_project_checks_returns_green_on_happy_path(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    results = run_project_checks(tmp_path, run_id="project-happy")

    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


def test_run_project_checks_detects_missing_c1_event(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Remove the events.jsonl
    (tmp_path / "shipwright_events.jsonl").unlink()
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C1" in r.name for r in red)


def test_run_project_checks_detects_missing_c5_changelog_entry(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Replace CHANGELOG with empty Added section
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- bug\n"
    )
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C5" in r.name for r in red)


def test_run_project_checks_detects_missing_phase_history(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Wipe phase_history
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and "phase_history" in r.name]
    assert len(red) == 1


def test_run_project_checks_with_empty_run_id_skips_phase_history(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    # Empty phase_history but caller doesn't pass run_id — check is neutral
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    results = run_project_checks(tmp_path, run_id="")
    phase_history_results = [r for r in results if "phase_history" in r.name]
    assert len(phase_history_results) == 1
    assert phase_history_results[0].ok is True  # skipped → neutral pass


def test_run_project_checks_detects_missing_c4_adr(tmp_path):
    """External plan review (e2-checks-project-elicitation, round 1): the
    #8 ledger citation claims C4 (``check_c4_decision_log_has_phase_adr``)
    already blocks on a missing phase ADR — proven here, not merely
    asserted, mirroring the existing C1/C5/phase_history regression tests
    in this same file."""
    seed_canon_project(tmp_path, run_id="project-happy")
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "# Decision Log\n\nNo entries yet.\n", encoding="utf-8",
    )
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok]
    assert any("C4" in r.name for r in red), [f"{r.name}: {r.detail}" for r in results]


# ---------------------------------------------------------------------------
# Grill-trace completeness gate (P4.2) — genuinely wired, not prose-only.
#
# Spec-reviewer REJECTed the first P4.2.2 round on AC2: the gate existed
# (verify_grill_trace_completeness.py) but was reachable only via Step-8
# prose telling the agent to run it and decide for itself — never through
# `run_project_checks()`, the actual code-level dispatcher C1-C5 use to
# genuinely block `update-step --step project`. These tests prove the fix:
# a failing grill-trace surfaces as an ERROR-severity CheckResult INSIDE
# `run_project_checks()` itself, the same list `_run_canon_checks`
# (`phase_validators.py`) already iterates for every other canon check.
# ---------------------------------------------------------------------------

def test_run_project_checks_detects_grill_trace_greenfield_assumed(tmp_path):
    """AC2 fix: an 'assumed' dimension in the project surface (no
    exceptions permitted there) surfaces as an ERROR-severity result
    inside run_project_checks() itself — genuinely code-enforced, not
    merely described in Step-8 prose."""
    seed_canon_project(tmp_path, run_id="project-happy")
    _write_grill_trace(
        tmp_path, requirement_key="export-data",
        boundaries="assumed:only CSV export was discussed",
    )
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert any("greenfield_assumed" in r.name for r in red), [
        f"{r.name}: {r.detail}" for r in results
    ]


def test_run_project_checks_detects_grill_trace_blank_dimension(tmp_path):
    """A second, independently-triggerable STOP condition — proves the
    wiring carries every one of the four closed-vocabulary STOPs, not
    just the first one a hand-rolled fixture happens to hit."""
    seed_canon_project(tmp_path, run_id="project-happy")
    _write_grill_trace(
        tmp_path, requirement_key="export-data",
        failure="not answered, not assumed, not n/a",
    )
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert any("blank_dimension" in r.name for r in red), [
        f"{r.name}: {r.detail}" for r in results
    ]


def test_run_project_checks_passes_with_a_clean_grill_trace(tmp_path):
    """A fully-answered, no-'assumed' trace must not itself turn the
    canon suite red — the gate blocks bad traces, not the mere presence
    of a trace."""
    seed_canon_project(tmp_path, run_id="project-happy")
    _write_grill_trace(tmp_path, requirement_key="export-data")
    results = run_project_checks(tmp_path, run_id="project-happy")
    red = [r for r in results if not r.is_skipped and not r.ok
           and r.severity == Severity.ERROR.value]
    assert red == [], [f"{r.name}: {r.detail}" for r in red]


# ---------------------------------------------------------------------------
# FR-01.02 #4/#15, #5, #10, #11 (req3-06-enforcement-mono sub-iterate e2) —
# wired into run_project_checks() via _project_gate_wiring.py.
# ---------------------------------------------------------------------------

def test_run_project_checks_includes_all_four_new_gates(tmp_path):
    seed_canon_project(tmp_path, run_id="project-happy")
    results = run_project_checks(tmp_path, run_id="project-happy")
    names = [r.name for r in results]
    assert any("FR-01.02 #4/#15" in n for n in names)
    assert any("FR-01.02 #5" in n for n in names)
    assert any("FR-01.02 #10" in n for n in names)
    assert any("FR-01.02 #11" in n for n in names)
