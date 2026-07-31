"""INTEGRATION — a person's decision survives a background producer's sweep.

AC-6 of iterate-2026-07-31-it1-s2-expected-status. The `cross_component` risk
flag fires on this diff because `shared/scripts/hooks/check_drift.py` is a hook
script, and the taxonomy answers that flag with *integration coverage*: a
real-scenario test proving the components COMPOSE, not three unit tests proving
each piece works alone.

The composition under test is the one the card describes end to end:

    the SessionStart drift hook  →  the triage store's lock and union reader
                                 →  the operator's own CLI surface

with the operator's decision landing in the window the producer cannot see —
after it has taken its unlocked snapshot of open items, before it writes.

**The barrier is a wrapper, not a stub.** `mark_status` still executes for real;
the wrapper only chooses the instant the operator acts. A test that ran the two
sequentially would pass with or without the fix, because the producer's snapshot
would already contain the decision — the exact objection the external plan
review raised (finding #10).

Scope: this proves the Python producer/operator path. The Command Center writes
through `proper-lockfile`, which does not compose with the Python byte lock, so
its interleaving is deliberately NOT claimed here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
for _p in (str(_SHARED_SCRIPTS), str(_SHARED_SCRIPTS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_spec = importlib.util.spec_from_file_location(
    "check_drift_for_integration", _SHARED_SCRIPTS / "hooks" / "check_drift.py",
)
assert _spec is not None and _spec.loader is not None
check_drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_drift)

import triage  # noqa: E402
import triage_promote  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _open_drift_item(project_root: Path, finding: str) -> str:
    """Seed one open drift item exactly as the detector would have."""
    check_drift._emit_drift_to_triage(project_root, content_findings=[finding])
    items = triage.read_all_items(project_root)
    assert len(items) == 1 and items[0]["status"] == "triage"
    return items[0]["id"]


@pytest.mark.integration
def test_operator_dismiss_wins_against_a_concurrent_drift_sweep(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card's scenario, composed.

    Production lines that MUST execute: `check_drift._emit_drift_to_triage`'s
    resolve pass (its `mark_status(..., expected_status="triage")` call and the
    `except StatusPreconditionError` arm) and `triage.mark_status`'s in-lock
    `raise StatusPreconditionError`. Nothing between them is stubbed.
    """
    item_id = _open_drift_item(project, "CLAUDE.md: 'docs/' missing from Structure")

    real_mark_status = triage.mark_status
    barrier_fired = []

    def barrier(*args, **kwargs):
        """Let the operator decide, ONCE, just before the producer's write.

        At this instant the producer has already read the store and believes
        the item is open — the window `expected_status` exists to close.
        """
        if not barrier_fired:
            barrier_fired.append(True)
            triage_promote.dismiss(
                project, item_id=item_id,
                reason="known and accepted, not drift",
            )
        return real_mark_status(*args, **kwargs)

    monkeypatch.setattr(triage, "mark_status", barrier)

    # The next sweep sees NO drift, so its resolve pass wants to close the item.
    # It must not: the store no longer holds the status it read.
    appended = check_drift._emit_drift_to_triage(project, content_findings=[])

    assert appended == 0
    assert barrier_fired, "the barrier never fired — the sweep did not attempt a write"

    item = next(i for i in triage.read_all_items(project) if i["id"] == item_id)
    assert item["status"] == "dismissed"
    assert item["statusBy"] == "manualDismiss"
    assert item["statusReason"] == "known and accepted, not drift"

    # And the producer's event was never written — the log carries exactly one
    # status event, the operator's. An audit read of the raw file must not show
    # a machine decision that merely lost on resolution.
    raw = triage._iter_raw_lines_at(triage._triage_path(project))
    status_events = [r for r in raw if r.get("event") == "status"]
    assert len(status_events) == 1
    assert status_events[0]["by"] == "manualDismiss"


@pytest.mark.integration
def test_the_sweep_still_resolves_an_item_nobody_touched(project: Path) -> None:
    """The other half of the composition: with no operator in the way, the
    drift sweep must still close its own stale item. A precondition that
    refused everything would pass the test above and be useless."""
    item_id = _open_drift_item(project, "CLAUDE.md: 'docs/' missing from Structure")

    check_drift._emit_drift_to_triage(project, content_findings=[])

    item = next(i for i in triage.read_all_items(project) if i["id"] == item_id)
    assert (item["status"], item["statusBy"], item["statusReason"]) == (
        "dismissed", "driftDetector", "driftResolved",
    )
