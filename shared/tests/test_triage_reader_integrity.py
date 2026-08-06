"""Lock scope + delivery visibility — IT-1 audit findings 12 and 28.

Part of iterate-2026-08-06-p2-19c-corruption-absence (card ``trg-8652bf24``).
The record-boundary, corruption and delivery halves live in
``test_triage_record_boundary_recovery.py``,
``test_triage_corruption_visibility.py`` and
``test_triage_delivery_visibility.py``.

* **AC4 / finding 12** — ``mark_status`` spawned three git subprocesses
  (~100-300 ms on Windows) *inside* the canonical append-log lock, which the D2
  sweep also holds across read→commit. Nothing in that decision depends on the
  locked state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _add(project: Path, *, to_outbox: bool) -> str:
    return triage.append_triage_item(
        project, source="manual", severity="low", kind="bug",
        title="t", detail="d", to_outbox=to_outbox,
    )


# ---------------------------------------------------------------------------
# AC4 (finding 12) — no git subprocess inside the canonical lock
# ---------------------------------------------------------------------------

def test_routing_probe_runs_outside_the_canonical_lock(tmp_path: Path, monkeypatch) -> None:
    """Fails if the probe is deleted AND if it merely moves back inside the lock.

    A test that only asserted "the probe ran" would stay green against the very
    refactor this pins; the ordering assertion is what makes it bite.
    """
    project = _project(tmp_path)
    item_id = _add(project, to_outbox=False)

    order: list[str] = []
    real_lock_cls = triage._load_file_lock_cls()

    class RecordingLock:
        def __init__(self, path):
            self._inner = real_lock_cls(path)

        def __enter__(self):
            order.append("lock-acquire")
            return self._inner.__enter__()

        def __exit__(self, *exc):
            order.append("lock-release")
            return self._inner.__exit__(*exc)

    real_probe = triage.should_route_to_outbox

    def spy(root):
        order.append("git-probe")
        return real_probe(root)

    monkeypatch.setattr(triage, "_load_file_lock_cls", lambda: RecordingLock)
    monkeypatch.setattr(triage, "should_route_to_outbox", spy)

    triage.mark_status(project, item_id, new_status="dismissed", by="test")

    assert "git-probe" in order, "the routing probe stopped running at all"
    assert "lock-acquire" in order, "the lock is no longer taken"
    assert order.index("git-probe") < order.index("lock-acquire"), order


def test_residence_still_routes_an_outbox_only_item_to_the_outbox(
    tmp_path: Path, monkeypatch,
) -> None:
    """The half that DOES depend on locked state must stay inside and keep working."""
    project = _project(tmp_path)
    item_id = _add(project, to_outbox=True)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: False)

    triage.mark_status(project, item_id, new_status="dismissed", by="test")

    flips = [
        r for r in triage._iter_raw_lines_at(triage._outbox_path(project))
        if r.get("event") == "status"
    ]
    assert [e["id"] for e in flips] == [item_id]


def test_tracked_item_flip_stays_tracked(tmp_path: Path, monkeypatch) -> None:
    """TRACKED-PREFERRED residence is unchanged by the hoist."""
    project = _project(tmp_path)
    item_id = _add(project, to_outbox=False)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: False)

    triage.mark_status(project, item_id, new_status="dismissed", by="test")

    flips = [
        r for r in triage._iter_raw_lines_at(triage._triage_path(project))
        if r.get("event") == "status"
    ]
    assert [e["id"] for e in flips] == [item_id]


def test_precondition_failure_still_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    """Hoisting must not let a refused flip leave a routing side effect behind."""
    project = _project(tmp_path)
    item_id = _add(project, to_outbox=False)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: False)

    try:
        triage.mark_status(
            project, item_id, new_status="dismissed", by="test",
            expected_status="promoted",
        )
    except triage.StatusPreconditionError:
        pass
    else:  # pragma: no cover - the precondition must refuse
        raise AssertionError("expected StatusPreconditionError")

    rows = triage._iter_raw_lines(project)
    assert [r for r in rows if r.get("event") == "status"] == []
