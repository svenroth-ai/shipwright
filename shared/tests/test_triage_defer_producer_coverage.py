"""Every shared auto-resolver closes a PARKED entry, not just an open one.

AC-26 for iterate-2026-08-01-triage-defer-lifecycle, and the direct answer to
how a defect shipped: `expected_status` was widened at all seven producer
paths, but one path's *read filter* was left at the literal `"triage"`, so that
producer dropped every parked entry before it could reach the write. One
representative integration scenario could not see it — only a test per path can,
which is what this file and its compliance-plugin sibling are.

The compliance producers (`audit/triage_bundle`, `sbom_generator`,
`test_evidence`) live in that plugin's own pytest root and cannot be imported
here (ADR-044); their three paths are covered by
`plugins/shipwright-compliance/tests/test_triage_defer_producer_coverage.py`.

Each test does the same four things — seed the producer's own kind of entry,
PARK it with a date still in the future, run the real producer in the state
where its finding has gone, and assert the entry closed. Reverting either half
of the widening at that producer turns exactly one of them red.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item, read_all_items  # noqa: E402
from tools.triage_promote import defer  # noqa: E402

FUTURE = "2099-01-01"


def _parked(project: Path, *, source: str, dedup_key: str, **over) -> str:
    """An entry this producer owns, parked and NOT yet due."""
    kw = dict(source=source, severity="medium", kind="bug", title="t",
              detail="d", dedup_key=dedup_key)
    kw.update(over)
    item_id = append_triage_item(project, **kw)
    defer(project, item_id=item_id, reason="not now", revisit_at=FUTURE)
    assert _status(project, item_id) == "snoozed", "fixture did not park"
    return item_id


def _status(project: Path, item_id: str) -> str:
    return next(i["status"] for i in read_all_items(project)
                if i["id"] == item_id)


# ---------------------------------------------------------------------------
# github_triage — two widened paths through one shared helper
# ---------------------------------------------------------------------------

def test_resolve_stale_closes_a_parked_action_unit(tmp_path: Path) -> None:
    from github_triage.resolve import resolve_stale  # noqa: PLC0415

    item = _parked(tmp_path, source="github", dedup_key="gh-security:acme/x")
    assert resolve_stale(tmp_path, {"gh-security:"}, set()) == 1
    assert _status(tmp_path, item) == "dismissed"


def test_resolve_pr_ci_closes_a_parked_pr_entry(tmp_path: Path) -> None:
    from github_triage.resolve import resolve_pr_ci  # noqa: PLC0415

    item = _parked(tmp_path, source="github", dedup_key="gh-pr-ci:42")
    closed = resolve_pr_ci(
        tmp_path, open_pr_numbers=set(), failing_pr_numbers=set(),
        pr_state_fetcher=lambda n: {"merged": True, "state": "closed"},
    )
    assert closed == 1
    assert _status(tmp_path, item) == "dismissed"


def test_the_legacy_migration_still_leaves_a_parked_entry_alone(
    tmp_path: Path,
) -> None:
    """The deliberate NON-widening, pinned so it cannot drift into the default.

    `migrate_legacy_items` shares `_dismiss_if_open` with the two above; it is a
    one-shot schema migration, not a "the finding disappeared" resolver, so a
    decided entry is none of its business.
    """
    from github_triage.resolve import migrate_legacy_items  # noqa: PLC0415

    item = _parked(tmp_path, source="github",
                   dedup_key="github:dependabot:CVE-2026-1")
    assert migrate_legacy_items(tmp_path, {"dependabot": True}) == 0
    assert _status(tmp_path, item) == "snoozed"


# ---------------------------------------------------------------------------
# drift detector
# ---------------------------------------------------------------------------

def test_the_drift_detector_closes_a_parked_drift_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hooks import check_drift  # noqa: PLC0415

    item = _parked(tmp_path, source="drift", kind="maintenance",
                   dedup_key="drift:CLAUDE.md#Structure:content")
    # The F7 guard refuses to write triage state into a non-Shipwright tree,
    # and tmp_path is one — patched on the module object (ADR-045), not by name.
    monkeypatch.setattr(check_drift, "_is_shipwright_project", lambda _r: True)
    # No findings this run → the drift this entry describes has cleared.
    check_drift._emit_drift_to_triage(tmp_path, [])
    assert _status(tmp_path, item) == "dismissed"


# ---------------------------------------------------------------------------
# phase-quality backlog
# ---------------------------------------------------------------------------

def test_the_phase_quality_backlog_closes_a_parked_entry(
    tmp_path: Path,
) -> None:
    from lib.phase_quality import _triage_bundle as bundle  # noqa: PLC0415

    item = _parked(tmp_path, source="phaseQuality",
                   dedup_key=bundle.BACKLOG_PREFIX + "deadbeef")
    # No fails in scope → the check this entry describes now passes.
    result = bundle.emit_phase_quality_backlog(tmp_path, run_id=None,
                                               commit=None)
    assert result["dismissed"] == 1
    assert _status(tmp_path, item) == "dismissed"
