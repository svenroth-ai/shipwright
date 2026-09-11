"""Tests for shared/scripts/tools/verifiers/project_checks.py + common helpers.

Exercises the iterate 12.1 project-phase canon dispatcher plus the
``check_phase_history_has_run`` common helper (added in 12.1 for use by
every phase-specific verifier module going forward).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.verifiers.common import (
    Severity,
    check_phase_history_has_run,
)
from tools.verifiers._project_gate_wiring import (
    check_basis_forbids_assumed,
    check_criteria_free_of_implementation_detail,
    check_no_empty_split,
    check_starting_guidance_present,
)
from tools.verifiers.project_checks import (
    check_manifest_splits_match_dirs,
    check_project_config_status_complete,
    run_project_checks,
)


def seed_canon_project(
    root: Path,
    *,
    splits: list[str] | None = None,
    run_id: str = "project-20260414-test",
    write_canon_artifacts: bool = True,
) -> None:
    """Produce a minimally-valid project that passes every check in
    ``run_project_checks`` when ``write_canon_artifacts=True``.

    Callers selectively tear down individual artifacts in failure-path
    tests so we don't pay the seed cost every time.
    """
    splits = splits or ["01-auth", "02-dashboard"]

    # Project config — status=complete, splits populated. scope="extension"
    # so `check_starting_guidance_present` (FR-01.02 #11) is skipped here —
    # this fixture never modeled CLAUDE.md/agent_docs scaffolding, which is
    # a Full Application-only concern this generic canon fixture is not
    # about; dedicated tests below exercise that check directly.
    (root / "shipwright_project_config.json").write_text(
        json.dumps({
            "status": "complete",
            "scope": "extension",
            "splits": [{"name": s, "status": "complete"} for s in splits],
        }),
        encoding="utf-8",
    )

    # Planning dirs matching splits — each spec.md carries one clean, minimal
    # FR row so `check_no_empty_split` (FR-01.02 #10) doesn't itself turn the
    # happy path red: a split with a bare "# spec" heading and no FR table is
    # exactly the empty-split defect that check exists to catch.
    for i, s in enumerate(splits, start=1):
        split_dir = root / ".shipwright" / "planning" / s
        split_dir.mkdir(parents=True)
        (split_dir / "spec.md").write_text(
            "# spec\n\n"
            "| ID | Name | Priority | Description | Basis |\n"
            "|---|---|---|---|---|\n"
            f"| FR-{i:02d}.01 | some capability | Must | "
            "a plain-language capability description | interview |\n",
            encoding="utf-8",
        )

    if not write_canon_artifacts:
        return

    # C1 — phase_completed event
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "phase_completed",
            "phase": "project",
            "timestamp": "2026-04-14T10:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )

    # C2 — build_dashboard mentions project
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "## Phases\n\n- project: complete\n"
    )

    # C3 — fresh session_handoff
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text("fresh")

    # C4 — ADR referencing project
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Project decomposition decision\n"
        "- **Status:** accepted\n"
    )

    # C5 — CHANGELOG [Unreleased] Added bullet (root CHANGELOG)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n"
        "- Project initialized: demo (2 splits)\n"
    )

    # phase_history — seed via run_config
    (root / "shipwright_run_config.json").write_text(
        json.dumps({
            "phase_history": {
                "project": [{"run_id": run_id, "date": "2026-04-14"}]
            },
        }),
        encoding="utf-8",
    )


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

def _write_grill_trace(root: Path, *, requirement_key: str, **dimension_overrides: str) -> None:
    """Write one valid-shaped grill-trace record, applying dimension
    overrides so an individual test can push exactly one dimension into
    STOP territory while keeping the other six/seven fields shape-valid."""
    dimensions = {
        "outcome": "answered",
        "purpose": "answered",
        "boundaries": "answered",
        "failure": "answered",
        "glossary": "answered",
        "rationale": "answered",
        "out_of_scope": "answered",
    }
    dimensions.update(dimension_overrides)
    trace_dir = root / ".shipwright" / "planning" / "grill-traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / f"{requirement_key}.json").write_text(
        json.dumps({
            "requirement_key": requirement_key,
            "requirement_text": "Users can export their data",
            "surface": "project",
            "evidence": ["interview transcript line 42"],
            "dimensions": dimensions,
            "fit_criterion": "export completes in < 5s for a 10k-row account",
            "glossary_delta": [],
            "confirmed_by": "user",
            "terms_used": [],
        }),
        encoding="utf-8",
    )


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


def _write_splits_config(root: Path, names: list[str]) -> None:
    """Declares ``names`` as this project's splits manifest — the
    authoritative source ``_read_spec_texts`` now enumerates from (round 2
    fix: config-driven, not directory-enumeration; see
    ``_project_gate_wiring._declared_split_names``)."""
    (root / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": n, "status": "not_started"} for n in names]}),
        encoding="utf-8",
    )


def test_check_basis_forbids_assumed_skips_when_no_spec_yet(tmp_path):
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_check_basis_forbids_assumed_fails_on_a_bare_assumed_cell(tmp_path):
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | assumed |\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_basis_forbids_assumed_fails_loud_on_a_declared_but_missing_spec(tmp_path):
    """External code review (round 2, low): only ``no_empty_split`` had a
    missing/unreadable-spec wiring test; the other two gates sharing
    ``_read_spec_texts`` need the same proof they don't silently pass."""
    _write_splits_config(tmp_path, ["01-a"])
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "unreadable/missing" in r.detail
    assert "01-a" in r.detail


def test_check_basis_forbids_assumed_skips_extension_scope(tmp_path):
    """External code review (round 5, medium, both reviewers
    independently): the ban is explicitly greenfield-only per the
    ledger's own #4/#15 text — an extension project's pre-existing,
    honestly-unconfirmed ``assumed`` row must not be relitigated, mirroring
    #11's existing scope carve-out."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({
            "scope": "extension",
            "splits": [{"name": "01-a", "status": "not_started"}],
        }),
        encoding="utf-8",
    )
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | assumed |\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_check_basis_forbids_assumed_fails_loud_on_non_object_config(tmp_path):
    """External code review (round 5, medium, openai): syntactically valid
    but non-object JSON (a bare list) must not crash ``.get('scope')``."""
    (tmp_path / "shipwright_project_config.json").write_text("[]", encoding="utf-8")
    r = check_basis_forbids_assumed(tmp_path)  # must not raise
    assert r.ok is False
    assert "not a JSON object" in r.detail


def test_check_criteria_free_of_implementation_detail_fails_on_a_symbol(tmp_path):
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | interview |\n\n"
        "### FR-01.01\n"
        "- (E) Given write_export_batch runs, when it completes, then a "
        "receipt is written.\n",
        encoding="utf-8",
    )
    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_no_empty_split_fails_when_a_split_has_zero_fr_rows(tmp_path):
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text("# spec\n\nNothing here yet.\n", encoding="utf-8")
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "01-a" in r.detail


def test_check_starting_guidance_present_skips_extension_scope(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"scope": "extension"}), encoding="utf-8",
    )
    r = check_starting_guidance_present(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_check_starting_guidance_present_fails_on_missing_files_full_app(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8",
    )
    r = check_starting_guidance_present(tmp_path)
    assert r.ok is False
    assert "missing" in r.detail


def test_check_starting_guidance_present_fails_loud_on_non_object_config(tmp_path):
    """External code review (round 5, medium, openai): ``null`` is valid
    JSON but has no ``.get`` — must not crash."""
    (tmp_path / "shipwright_project_config.json").write_text("null", encoding="utf-8")
    r = check_starting_guidance_present(tmp_path)  # must not raise
    assert r.ok is False
    assert "not a JSON object" in r.detail


def test_check_no_empty_split_fails_loud_when_names_are_all_null_or_empty(tmp_path):
    """External code review (round 5, medium, openai): a FALSY name
    (``null``, ``""``) used to be filtered out before being counted as
    rejected, so an all-null manifest read as "declared zero splits"
    (SKIPPED) instead of "every declared split was invalid" (loud)."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": None}, {"name": ""}, {"status": "x"}]}),
        encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "invalid/unsafe" in r.detail


def test_check_starting_guidance_present_fails_loud_on_malformed_config(tmp_path):
    """External code review (round 4, low, GLM): a corrupt project config
    used to fall through to scope=None, which then silently ENFORCED the
    full-application guidance check instead of reporting the config as
    unverifiable — the one gate in this module that broke the
    fail-loud-on-unparseable-manifest pattern the other three follow."""
    (tmp_path / "shipwright_project_config.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    r = check_starting_guidance_present(tmp_path)
    assert r.ok is False
    assert "could not be parsed" in r.detail


def test_check_no_empty_split_fails_on_an_unreadable_spec_md(tmp_path):
    """External plan review (e2-checks-project-elicitation, round 1, medium):
    a declared split whose spec.md EXISTS but cannot be read must not
    silently drop out of every spec-text-keyed check as though the split
    didn't exist — that reads as a pass, not the unverifiable state it is.
    A directory named ``spec.md`` is the portable (cross-platform, unlike
    os.chmod on Windows) way to force a real read failure — same trick
    ``test_grill_trace_glossary.py`` already uses for this exact class of
    regression."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").mkdir()  # a directory, not a file — read_text() fails
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "unreadable/missing" in r.detail
    assert "01-a" in r.detail


def test_check_no_empty_split_fails_loud_on_a_malformed_project_config(tmp_path):
    """External code review (round 3, medium, GLM): a malformed
    ``shipwright_project_config.json`` used to fall through to "zero
    splits declared" and every spec-text gate passed vacuously — exactly
    the silent-pass failure mode round 1 closed for an unreadable
    spec.md, just one layer up (the manifest itself)."""
    (tmp_path / "shipwright_project_config.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "could not be parsed" in r.detail


def test_check_basis_forbids_assumed_catches_a_qualified_assumed_cell(tmp_path):
    """External code review (round 3, low, GLM): ``fr_basis.classify``
    returns ``kind='malformed'`` (not ``known``/``assumed``) for
    ``assumed: <reason>`` — a naive known/assumed check misses it, which
    is exactly the qualifier-smuggling loophole the "no exceptions"
    wording on #4/#15 exists to close."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | "
        "assumed: nobody could answer |\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_no_empty_split_ignores_an_unsafe_split_name(tmp_path):
    """External code review (round 3, medium, openai): a malformed
    manifest naming a non-string, absolute, or traversal split name must
    not crash the validator — a MIXED manifest (one valid name alongside
    several unsafe ones) filters the unsafe entries and keeps checking the
    valid subset, rather than reaching ``planning_dir / name`` with a bad
    value. (An all-unsafe manifest is a different, louder case — see
    ``test_check_no_empty_split_fails_loud_when_every_declared_name_is_unsafe``.)"""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [
            {"name": "01-a"},
            {"name": "../escape"},
            {"name": "/absolute"},
            {"name": 42},
            {"name": None},
        ]}),
        encoding="utf-8",
    )
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n",
        encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is True


def test_check_no_empty_split_fails_loud_when_every_declared_name_is_unsafe(tmp_path):
    """External code review (round 4, low+medium, both reviewers): a
    manifest whose split names are ALL invalid/unsafe must not silently
    read as "zero splits declared" (SKIPPED) — that is a corrupt manifest,
    not an empty project, and deserves the same loud failure a totally
    unparseable config already gets."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "../escape"}, {"name": 42}, {"name": "."}]}),
        encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "invalid/unsafe" in r.detail


def test_check_no_empty_split_fails_loud_on_non_object_config(tmp_path):
    """External code review (round 6, medium, both reviewers
    independently): a syntactically valid but non-object config (``[]``)
    used to fall through to "zero splits declared" here even though the
    SAME case already failed loud in ``_read_project_scope`` — the
    inconsistency both reviewers independently caught."""
    (tmp_path / "shipwright_project_config.json").write_text("[]", encoding="utf-8")
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is False
    assert "expected a JSON object" in r.detail


def test_is_safe_split_name_rejects_windows_drive_and_root_relative_names():
    """External code review (round 6, low+medium, both reviewers
    independently): ``is_absolute()`` alone misses Windows DRIVE-relative
    (``"C:foo"``) and ROOT-relative (``"\\\\outside"``) names — neither
    counts as absolute to pathlib (it requires BOTH drive and root), but
    either re-anchors ``planning_dir / name`` away from the planning tree."""
    from tools.verifiers._project_gate_wiring import _is_safe_split_name
    assert _is_safe_split_name("C:foo") is False
    assert _is_safe_split_name("\\outside\\spec") is False
    assert _is_safe_split_name("01-a") is True


def test_check_no_empty_split_fails_loud_when_splits_is_not_a_list(tmp_path):
    """External code review (round 4, medium, openai): ``"splits": 1``
    (a scalar) used to raise ``TypeError`` iterating a non-iterable during
    manifest reading instead of producing a failing ``CheckResult``."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": 1}), encoding="utf-8",
    )
    r = check_no_empty_split(tmp_path)  # must not raise
    assert r.ok is False
    assert "expected a list" in r.detail


def test_check_no_empty_split_fails_on_a_declared_split_with_no_spec_md_at_all(tmp_path):
    """External CODE review (e2-checks-project-elicitation, round 2, medium):
    the round-1 fix only made an UNREADABLE spec.md fail loud — a DECLARED
    split that never got a spec.md written at all was still silently
    absent from ``_read_spec_texts``'s old ``*/spec.md`` glob, so a second
    populated split made this gate pass vacuously over the empty one."""
    _write_splits_config(tmp_path, ["01-a", "02-b"])
    populated = tmp_path / ".shipwright" / "planning" / "01-a"
    populated.mkdir(parents=True)
    (populated / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n",
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "planning" / "02-b").mkdir(parents=True)  # declared, spec.md never written
    r = check_no_empty_split(tmp_path)
    assert r.ok is False
    assert "02-b" in r.detail
    assert "missing" in r.detail
    assert "01-a" not in r.detail


def test_check_no_empty_split_ignores_undeclared_planning_dirs(tmp_path):
    """External CODE review (e2-checks-project-elicitation, round 2, high,
    both reviewers independently): a raw directory-enumeration design
    cannot tell a real split from a reserved non-split dir under
    ``.shipwright/planning/`` (``campaigns/``, ``adr/``, ``grill-traces/``,
    ``iterate/``, ``01-adopted/`` — this very repo's own layout has all
    five) — an exclusion list chases every new one forever. The round-2
    redesign enumerates from the project's OWN declared ``splits``
    manifest instead, so an undeclared dir is invisible to this check
    regardless of its name, proven here with the two reserved dirs that
    actually broke it during review."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget | Must | export widgets | interview |\n",
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "planning" / "grill-traces").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "campaigns").mkdir(parents=True)
    r = check_no_empty_split(tmp_path)
    assert r.ok is True


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
