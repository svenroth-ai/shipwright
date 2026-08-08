"""GC compaction of `amend` events (AC11/AC12, iterate-2026-08-08-triage-amend-event).

AC11: an orphan-amend validation error must ship together with the matching
compaction fix — without it, a churned item's leftover `amend` line survives
`apply_gc_reporting`'s rewrite, and `_validate_after`'s orphan check (extended
to `amend` in the same change) would then raise on every future GC run over a
survivor it can never un-drop. This module pins both halves together.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent
for _p in (str(_SHARED / "scripts"), str(_SHARED / "scripts" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import triage  # noqa: E402
import triage_gc  # noqa: E402

HEADER = '{"v":1,"schema":"triage","created":"2026-08-08T00:00:00Z"}'
ITEM_ID = "trg-churned1"

_APPEND = (
    f'{{"event":"append","id":"{ITEM_ID}","ts":"2026-08-08T00:00:00Z",'
    f'"source":"sbomGenerator","severity":"low","kind":"bug","title":"t","detail":"d",'
    f'"status":"triage"}}'
)
_AMEND = (
    f'{{"event":"amend","id":"{ITEM_ID}","ts":"2026-08-08T00:30:00Z",'
    f'"by":"cli","title":"corrected before dismissal"}}'
)
_MACHINE_DISMISS = (
    f'{{"event":"status","id":"{ITEM_ID}","ts":"2026-08-08T01:00:00Z",'
    f'"newStatus":"dismissed","by":"sbomGenerator","reason":"sbomResolved"}}'
)


def _seed(root: Path, *lines: str) -> Path:
    path = root / ".shipwright" / "triage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([HEADER, *lines]) + "\n", encoding="utf-8", newline="\n")
    return path


def test_amend_line_for_a_churned_id_is_compacted_away(tmp_path: Path) -> None:
    """The `kept` filter must drop `amend` alongside `append`/`status` for a
    dropped id — otherwise the amend line survives as an orphan."""
    _seed(tmp_path, _APPEND, _AMEND, _MACHINE_DISMISS)
    plan = triage_gc.plan_gc(tmp_path)
    assert ITEM_ID in plan["drop_ids"], plan

    triage_gc.apply_gc_reporting(tmp_path, plan["drop_ids"], backup=False)

    raw = triage._iter_raw_lines_at(triage._triage_path(tmp_path))
    assert not any(r.get("id") == ITEM_ID for r in raw), raw


def test_amend_for_a_surviving_item_is_not_touched_by_gc(tmp_path: Path) -> None:
    """A normal (non-churned) item's amend history is not compaction fodder."""
    _seed(tmp_path, _APPEND, _AMEND)  # no dismiss — item stays open
    plan = triage_gc.plan_gc(tmp_path)
    assert plan["drop_ids"] == set(), plan

    triage_gc.apply_gc_reporting(tmp_path, plan["drop_ids"], backup=False)

    raw = triage._iter_raw_lines_at(triage._triage_path(tmp_path))
    assert any(r.get("event") == "amend" and r.get("id") == ITEM_ID for r in raw), raw
    item = next(i for i in triage.read_all_items(tmp_path) if i["id"] == ITEM_ID)
    assert item["title"] == "corrected before dismissal"


def test_plan_gc_report_reflects_the_amended_title_not_the_original(tmp_path: Path) -> None:
    """`_resolve_tracked_only` (the tracked-only resolver `plan_gc`'s dry-run
    report is built from) must overlay `amend` events the same way
    `read_all_items` does — otherwise an operator previewing a GC run sees a
    churned item's PRE-amend title."""
    _seed(tmp_path, _APPEND, _AMEND)  # open item, amended, no dismiss
    resolved = {i["id"]: i for i in triage_gc._resolve_tracked_only(tmp_path)}
    assert resolved[ITEM_ID]["title"] == "corrected before dismissal", resolved[ITEM_ID]


def test_resolve_tracked_only_initializes_amended_fields_for_unamended_items(tmp_path: Path) -> None:
    """Stage-2 code review finding 3: `_resolve_tracked_only`'s pass-1 init must
    set `amendedBy`/`amendedAt` for EVERY item, not only ones a later amend
    happens to touch — otherwise a consumer reading `item['amendedBy']` off an
    un-amended `plan_gc` result hits `KeyError`, diverging from `read_all_items`
    (which initializes both unconditionally)."""
    _seed(tmp_path, _APPEND)  # no amend at all
    resolved = {i["id"]: i for i in triage_gc._resolve_tracked_only(tmp_path)}
    assert resolved[ITEM_ID]["amendedBy"] is None
    assert resolved[ITEM_ID]["amendedAt"] is None


def test_resolve_tracked_only_handles_an_amend_preceding_its_append_in_file_order(tmp_path: Path) -> None:
    """Stage-3 doubt review, finding 4: a `merge=union` churn resolve can place a
    status/amend BEFORE its own append on the same tracked file — the classifier
    (`lib.triage_validate`) already documents this as legitimate. A single
    file-order interleaved pass silently dropped such an event (its append was
    not yet resolved when the loop reached it); the two-pass (append-first,
    then overlay) resolution must not."""
    _seed(tmp_path, _AMEND, _APPEND)  # amend precedes its own append in file order
    resolved = {i["id"]: i for i in triage_gc._resolve_tracked_only(tmp_path)}
    assert resolved[ITEM_ID]["title"] == "corrected before dismissal", resolved[ITEM_ID]


def test_resolve_tracked_only_resolves_two_same_id_amends_by_ts_not_file_order(tmp_path: Path) -> None:
    """Two amends for the same id, out of ts order in the FILE: `_resolve_tracked_only`
    must resolve them by `(ts, file-order)`, the same tiebreak `read_all_items` uses
    — a plain file-order pass would show the operator the wrong (later-in-file, but
    earlier-in-time) title (Stage-3 doubt review, finding 4)."""
    later_ts_first_in_file = (
        f'{{"event":"amend","id":"{ITEM_ID}","ts":"2026-08-08T02:00:00Z",'
        f'"by":"cli","title":"later by ts, first in file"}}'
    )
    earlier_ts_second_in_file = (
        f'{{"event":"amend","id":"{ITEM_ID}","ts":"2026-08-08T01:00:00Z",'
        f'"by":"cli","title":"earlier by ts, second in file"}}'
    )
    _seed(tmp_path, _APPEND, later_ts_first_in_file, earlier_ts_second_in_file)
    resolved = {i["id"]: i for i in triage_gc._resolve_tracked_only(tmp_path)}
    assert resolved[ITEM_ID]["title"] == "later by ts, first in file", resolved[ITEM_ID]


def test_validate_after_raises_on_an_orphan_amend(tmp_path: Path) -> None:
    """Pins the guard itself: a leftover amend whose append is gone must be
    refused, not silently accepted as clean post-GC state."""
    path = _seed(tmp_path, _AMEND)  # amend with no append anywhere — hand-crafted
    with pytest.raises(RuntimeError, match="orphan amend"):
        triage_gc._validate_after(tmp_path, drop_ids=set())
    assert path.exists()  # nothing rewritten by the raising call itself
