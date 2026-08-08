"""Coverage-envelope aggregate tests for event_context_index.

Split out of test_event_context_backfill.py (iterate-2026-08-08-coverage-
envelope-split) once that file crossed the 300-line guideline. These tests
cover `coverage.fields.<key>` aggregation (declared/derived/not_applicable/
missing) and `coverage.missing_work_completed`; per-entry `provenance`
backfill behaviour stays in test_event_context_backfill.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.area_catalog import seed_brownfield  # noqa: E402
from lib.event_context_coverage import MISSING_ELIGIBLE_FIELDS  # noqa: E402
from lib.event_context_index import PROVENANCE_FIELDS, build_index  # noqa: E402
from tests._event_context_fixtures import commit as _commit  # noqa: E402
from tests._event_context_fixtures import git as _git  # noqa: E402
from tests._event_context_fixtures import init_repo as _init_repo  # noqa: E402
from tests._event_context_fixtures import write_events as _write_events  # noqa: E402


def test_coverage_envelope_present_with_per_field_counts(tmp_path: Path) -> None:
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "x.py", "1", "chore: no run id trailer")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "commit": "declared-sha",
         "changed_files": ["src/x.py"], "affected_frs": ["FR-01.01"],
         "supersedes": "evt-earlier"},
        {"event_id": "e2", "type": "work_completed", "change_type": "internal-tooling"},
        {"event_id": "e3", "type": "grade_snapshot"},
    ])
    payload = build_index(tmp_path)
    coverage = payload["coverage"]
    assert coverage["commit_map"]["status"] == "ok"
    assert set(coverage["fields"]) == {
        "commit", "changed_files", "area_ids", "affected_frs", "supersedes_event_id",
    }
    for field_counts in coverage["fields"].values():
        assert set(field_counts) == {"derived", "declared", "not_applicable", "missing"}
        assert sum(field_counts.values()) == 3  # three events written above
    # e2/e3 both carry no run_id and no commit, so their "unavailable" fields are
    # not_applicable (structurally ineligible), not missing -- neither is a
    # work_completed record with a linkage the git-trailer join could have used.
    assert coverage["fields"]["affected_frs"]["declared"] == 2  # e1 (list) + e2 (change_type)
    assert coverage["fields"]["affected_frs"]["not_applicable"] == 1  # e3
    assert coverage["fields"]["affected_frs"]["missing"] == 0
    assert coverage["fields"]["supersedes_event_id"]["declared"] == 1  # e1 only
    assert coverage["fields"]["supersedes_event_id"]["not_applicable"] == 2  # e2, e3
    assert coverage["fields"]["commit"]["declared"] == 1  # e1 only
    assert coverage["fields"]["commit"]["not_applicable"] == 2  # e2, e3 (no linkage at all)
    assert coverage["fields"]["commit"]["missing"] == 0
    e1 = next(e for e in payload["entries"] if e["event_id"] == "e1")
    assert e1["supersedes_event_id"] == "evt-earlier"
    assert e1["provenance"]["supersedes_event_id"] == "declared"
    assert coverage["missing_work_completed"] == {"count": 0, "event_ids": [], "truncated": False}


def test_coverage_unavailable_splits_not_applicable_from_missing(tmp_path: Path) -> None:
    """Two entries land in the SAME field's "unavailable" population for two
    different reasons: e1 (grade_snapshot, no run_id, no commit) can never carry
    a selection key -- not_applicable. e2 (work_completed, a run_id the
    commit-trailer join has no matching commit for) COULD have carried one --
    missing. Regression guard for the pre-fix behaviour where both collapsed
    into a single "unavailable" count and made a 100% not_applicable field read
    identically to a 100% missing one (iterate-2026-08-08-coverage-envelope-split)."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "unrelated.py", "x", "chore: unrelated, no run id trailer")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "grade_snapshot"},
        {"event_id": "e2", "type": "work_completed", "run_id": "run-does-not-exist"},
    ])
    payload = build_index(tmp_path)
    coverage = payload["coverage"]
    assert coverage["fields"]["commit"] == {"derived": 0, "declared": 0, "not_applicable": 1, "missing": 1}
    assert coverage["fields"]["changed_files"] == {"derived": 0, "declared": 0, "not_applicable": 1, "missing": 1}
    # area_ids has no independent signal of its own -- it mirrors changed_files
    # unavailability but is deliberately excluded from MISSING_ELIGIBLE_FIELDS
    # (see test_empty_diff_backfilled_commit_does_not_false_flag_area_ids_as_missing).
    assert coverage["fields"]["area_ids"] == {"derived": 0, "declared": 0, "not_applicable": 2, "missing": 0}
    assert "unavailable" not in coverage["fields"]["commit"]
    assert coverage["missing_work_completed"]["count"] == 1
    assert coverage["missing_work_completed"]["event_ids"] == ["e2"]
    assert coverage["missing_work_completed"]["truncated"] is False


def test_empty_diff_backfilled_commit_does_not_false_flag_area_ids_as_missing(tmp_path: Path) -> None:
    """area_ids has NO independent signal -- `_event_entry` derives it purely
    from whether `changed_files` resolved any paths (`"derived" if paths else
    "unavailable"`). A matched Run-ID commit with a genuinely EMPTY diff
    resolves changed_files "derived" with an empty list, but area_ids
    "unavailable" -- even though the trailer join succeeded completely. Before
    this fix, including area_ids in MISSING_ELIGIBLE_FIELDS re-created exactly
    the false alarm this iterate exists to remove: a perfectly-linked
    empty-diff work_completed event landed in missing_work_completed
    (code review finding, iterate-2026-08-08-coverage-envelope-split)."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _git(tmp_path, "commit", "--allow-empty", "-q", "-m", "chore: no-op\n\nRun-ID: run-empty-diff")
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "run_id": "run-empty-diff",
         "change_type": "tooling"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["changed_files"] == []
    assert entry["provenance"]["changed_files"] == "derived"
    assert entry["provenance"]["area_ids"] == "unavailable"  # per-entry vocabulary is unchanged
    coverage = payload["coverage"]
    assert coverage["fields"]["area_ids"]["missing"] == 0
    assert coverage["fields"]["area_ids"]["not_applicable"] == 1  # excluded from the split, not "eligible-missing"
    assert coverage["missing_work_completed"]["event_ids"] == []


def test_unknown_event_type_with_no_linkage_lands_in_not_applicable(tmp_path: Path) -> None:
    """Eligibility must come from the entry's own data (a run_id/commit), never
    a hardcoded event-type list -- a brand-new observation-only event type this
    test has never seen before must still land in not_applicable with zero code
    changes. `grade_snapshot` alone (used by the other split test) does not
    prove this: a regression that reintroduced a hardcoded list containing
    `grade_snapshot` would still pass it (external review openai finding,
    iterate-2026-08-08-coverage-envelope-split)."""
    seed_brownfield(tmp_path)
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "some_future_event_type_never_seen_before"},
    ])
    payload = build_index(tmp_path)
    coverage = payload["coverage"]
    for field in MISSING_ELIGIBLE_FIELDS:
        assert coverage["fields"][field]["missing"] == 0
        assert coverage["fields"][field]["not_applicable"] == 1
    assert coverage["missing_work_completed"]["event_ids"] == []


def test_missing_eligible_fields_is_a_subset_of_provenance_fields(tmp_path: Path) -> None:
    """Guard against MISSING_ELIGIBLE_FIELDS drifting out of sync with
    PROVENANCE_FIELDS (event_context_index.py) -- a stale/renamed entry would
    silently demote that field to not_applicable-only forever, with no error
    and no other failing test (code review finding,
    iterate-2026-08-08-coverage-envelope-split)."""
    assert MISSING_ELIGIBLE_FIELDS <= set(PROVENANCE_FIELDS)


def test_declared_commit_without_run_id_is_still_eligible_for_missing(tmp_path: Path) -> None:
    """A work_completed event that declares a commit directly (legacy path,
    pre-dates the run_id-keyed backfill) but never declares changed_files is a
    real linkage without a run_id -- eligibility must fall back to "does this
    entry already carry a commit" and not require run_id specifically, or these
    events would be wrongly counted not_applicable despite plainly being change
    records (matches the 10 real events of this shape found on main,
    iterate-2026-08-08-coverage-envelope-split)."""
    seed_brownfield(tmp_path)
    _write_events(tmp_path, [
        {"event_id": "e1", "type": "work_completed", "commit": "legacy-sha-no-run-id"},
    ])
    payload = build_index(tmp_path)
    coverage = payload["coverage"]
    assert coverage["fields"]["commit"]["declared"] == 1
    assert coverage["fields"]["changed_files"]["missing"] == 1
    assert coverage["fields"]["changed_files"]["not_applicable"] == 0
    assert coverage["missing_work_completed"]["event_ids"] == ["e1"]


def test_supersedes_event_id_never_lands_in_missing(tmp_path: Path) -> None:
    """Not superseding a prior event is the normal, correct state for almost
    every entry -- there is no data-derivable signal for "should have recorded
    a supersession and didn't", unlike commit/changed_files where an eligible-
    but-empty value means the trailer join genuinely failed. A run_id-bearing
    work_completed event with no `amends`/`amended_event_id`/`supersedes` must
    stay not_applicable, never missing, or the aggregate would flag the
    overwhelming majority of ordinary events as a data-quality problem
    (measured 503-of-831 on real repo data before this test was added,
    iterate-2026-08-08-coverage-envelope-split)."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    sha = _commit(tmp_path, "x.py", "1", "feat: x\n\nRun-ID: run-no-supersede")
    _write_events(tmp_path, [
        # change_type set so affected_frs is "declared" (legitimately none) --
        # isolates supersedes_event_id as the only unavailable field on this entry.
        {"event_id": "e1", "type": "work_completed", "run_id": "run-no-supersede",
         "change_type": "tooling"},
    ])
    payload = build_index(tmp_path)
    entry = payload["entries"][0]
    assert entry["commit"] == sha  # eligible: this IS a real, fully-linked change record
    coverage = payload["coverage"]
    assert coverage["fields"]["supersedes_event_id"]["missing"] == 0
    assert coverage["fields"]["supersedes_event_id"]["not_applicable"] == 1
    assert coverage["missing_work_completed"]["event_ids"] == []


def test_missing_work_completed_list_is_capped_and_flagged_truncated(tmp_path: Path) -> None:
    """The log is append-only and historical entries can never be repaired, so
    the retained 50 must be the MOST RECENT (by log sequence), not an
    arbitrary lexicographic-by-id slice -- otherwise an unfixable backlog of
    old events buries the recent, actionable ones (code review finding,
    iterate-2026-08-08-coverage-envelope-split)."""
    seed_brownfield(tmp_path)
    _init_repo(tmp_path)
    _commit(tmp_path, "unrelated.py", "x", "chore: unrelated, no run id trailer")
    events = [
        {"event_id": f"e{i:03d}", "type": "work_completed", "run_id": f"run-missing-{i:03d}"}
        for i in range(60)
    ]
    _write_events(tmp_path, events)
    payload = build_index(tmp_path)
    missing = payload["coverage"]["missing_work_completed"]
    assert missing["count"] == 60
    assert len(missing["event_ids"]) == 50
    assert missing["truncated"] is True
    assert missing["event_ids"] == sorted(f"e{i:03d}" for i in range(10, 60))
