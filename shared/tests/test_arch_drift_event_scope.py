"""Event-ownership scoping for the whole-set arch-drift checkers.

Pins the fix for the campaign cross-branch bleed: gitignored decision-drops
accumulate in the shared main-rooted ``decision-drops/`` dir across sibling
branches, but each branch's ``architecture.md`` / ``conventions.md`` entry is
committed per-branch (unmerged until the PR lands). A later sibling therefore
sees an earlier sibling's drop with no doc entry on *its* branch → false drift.

The whole-set checkers (``test_architecture_md_reflects_arch_impact`` +
the Group-F ``F5`` detective) scope to drops OWNED by this tree's lineage:
``run_id ∈ events_log.finalized_run_ids(events.jsonl)``. When the event log is
absent (hermetic test / non-events project), ownership is unknowable and the
caller falls back to whole-set checking (fail-open — never weaker than before).

Run-id origin: an iterate's ``work_completed`` event carries its run_id in
``adr_id`` (ADR-059); the decision-drop carries the same string in ``run_id``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

from lib.architecture_doc import (  # noqa: E402
    DropRecord,
    arch_impact_records,
    missing_entries,
    records_in_run_set,
    scan_drops,
)
from lib.events_log import EVENT_FILE, finalized_run_ids  # noqa: E402


# --- helpers ---------------------------------------------------------------

def _write_events(root: Path, *events: dict) -> None:
    lines = [json.dumps(e) for e in events]
    (root / EVENT_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _work_completed(adr_id: str) -> dict:
    return {"type": "work_completed", "source": "iterate", "adr_id": adr_id, "commit": ""}


def _seed_drop(root: Path, run_id: str, impact: str = "component") -> None:
    drops = root / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True, exist_ok=True)
    (drops / f"{run_id}_001.json").write_text(
        json.dumps({"run_id": run_id, "architecture_impact": impact}),
        encoding="utf-8",
    )


# --- finalized_run_ids (AC1, Boundary Probe round-trip) --------------------

def test_finalized_run_ids_absent_log_returns_none(tmp_path):
    # No events.jsonl → ownership unknowable → None (callers fail open).
    assert finalized_run_ids(tmp_path) is None


def test_finalized_run_ids_empty_log_returns_empty_set(tmp_path):
    # Present-but-empty → empty set (strict scoping), NOT None.
    (tmp_path / EVENT_FILE).write_text("", encoding="utf-8")
    assert finalized_run_ids(tmp_path) == set()


def test_finalized_run_ids_collects_adr_id_and_run_id(tmp_path):
    # Round-trip (touches_io_boundary probe): write events.jsonl, read back the
    # run_id set. Covers both the iterate `adr_id` field and an explicit
    # `run_id` field, and a non-run event that carries neither.
    _write_events(
        tmp_path,
        _work_completed("iterate-2026-06-12-a"),
        _work_completed("iterate-2026-06-12-b"),
        {"type": "phase_completed", "run_id": "iterate-2026-06-12-c"},
        {"type": "noise", "session": "x"},
    )
    assert finalized_run_ids(tmp_path) == {
        "iterate-2026-06-12-a",
        "iterate-2026-06-12-b",
        "iterate-2026-06-12-c",
    }


def test_finalized_run_ids_skips_corrupt_lines(tmp_path):
    path = tmp_path / EVENT_FILE
    path.write_text(
        json.dumps(_work_completed("iterate-good")) + "\n"
        + "{not valid json\n"
        + "\n"  # blank
        + json.dumps(_work_completed("iterate-good2")) + "\n",
        encoding="utf-8",
    )
    assert finalized_run_ids(tmp_path) == {"iterate-good", "iterate-good2"}


# --- records_in_run_set (AC2) ----------------------------------------------

def test_records_in_run_set_keeps_only_allowed():
    recs = [
        DropRecord(drop_file="a_001.json", run_id="run-a", impact="component"),
        DropRecord(drop_file="b_001.json", run_id="run-b", impact="convention"),
        DropRecord(drop_file="c_001.json", run_id="run-c", impact="data-flow"),
    ]
    kept = records_in_run_set(recs, {"run-a", "run-c"})
    assert {r.run_id for r in kept} == {"run-a", "run-c"}


def test_records_in_run_set_empty_allowed_keeps_nothing():
    recs = [DropRecord(drop_file="a_001.json", run_id="run-a", impact="component")]
    assert records_in_run_set(recs, set()) == []


# --- end-to-end scoping composition (AC3 / AC4) ----------------------------

def test_unowned_undocumented_drop_is_excluded(tmp_path):
    # AC3: a sibling drop in the shared dir whose run_id is NOT in this tree's
    # events.jsonl is scoped OUT, so its absence from the docs is not drift.
    _seed_drop(tmp_path, "iterate-sibling-unowned", impact="component")
    drops_dir = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    _write_events(tmp_path, _work_completed("iterate-something-else"))

    records, _ = scan_drops(drops_dir)
    owned = finalized_run_ids(tmp_path)
    assert owned is not None
    scoped = records_in_run_set(records, owned)
    # Empty architecture.md / conventions.md (drop is undocumented).
    missing = missing_entries(scoped, {"architecture.md": "", "conventions.md": ""})
    assert missing == []  # excluded → no false drift


def test_owned_undocumented_drop_is_caught(tmp_path):
    # AC4: a drop whose run_id IS in this tree's events.jsonl but is undocumented
    # is still flagged — drift protection preserved for owned runs.
    _seed_drop(tmp_path, "iterate-owned", impact="component")
    drops_dir = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    _write_events(tmp_path, _work_completed("iterate-owned"))

    records, _ = scan_drops(drops_dir)
    owned = finalized_run_ids(tmp_path)
    scoped = records_in_run_set(records, owned)
    assert {r.run_id for r in arch_impact_records(scoped)} == {"iterate-owned"}
    missing = missing_entries(scoped, {"architecture.md": "", "conventions.md": ""})
    assert [r.run_id for r in missing] == ["iterate-owned"]
