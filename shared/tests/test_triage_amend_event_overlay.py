"""`triage.amend_triage_item` read-side overlay, ordering, and locking.

iterate-2026-08-08-triage-amend-event (trg-b310add8 / P2.46). Split out of
`test_triage_amend_event.py` when that file crossed the 300-LOC guideline
(Stage-2 code review fix round). Covers the iterate spec's AC2-5 and AC13-14:
read-side overlay (present-overlays / absent-untouched / invalid-skips-whole),
`(ts, file-order)` interleaving with `status` events, locking, and the
real-disk round-trip Boundary Probe. Writer validation/errors live in the
sibling file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import amend_triage_item, append_triage_item, read_all_items  # noqa: E402


def _seed(root: Path, **overrides) -> str:
    kwargs = dict(
        source="manual", severity="low", kind="bug",
        title="Original title", detail="Original detail",
    )
    kwargs.update(overrides)
    return append_triage_item(root, **kwargs)


# --- read-side overlay (AC2-5) ------------------------------------------------

def test_amend_overlays_present_fields_leaves_absent_untouched(tmp_path: Path):
    item_id = _seed(tmp_path)
    amend_triage_item(tmp_path, item_id, by="sven", title="Corrected title")
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "Corrected title"
    assert item["detail"] == "Original detail"
    assert item["severity"] == "low"


def test_amend_does_not_overlay_item_ts(tmp_path: Path):
    item_id = _seed(tmp_path)
    before = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)["ts"]
    amend_triage_item(tmp_path, item_id, by="sven", title="Corrected title")
    after = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)["ts"]
    assert after == before


def test_amend_with_invalid_field_is_skipped_whole(tmp_path: Path):
    item_id = _seed(tmp_path)
    # Hand-write a corrupt amend line directly (bypassing writer validation)
    # to exercise the reader's tolerant-skip path.
    path = Path(tmp_path) / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(
            '{"event":"amend","id":"%s","ts":"2026-08-08T12:00:00Z",'
            '"by":"x","title":"should not apply","severity":"urgent"}\n' % item_id
        )
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "Original title"
    assert item["amendedBy"] is None


def test_amend_severity_recomputes_suggested_priority(tmp_path: Path):
    item_id = _seed(tmp_path, severity="low")
    amend_triage_item(tmp_path, item_id, by="sven", severity="critical")
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["severity"] == "critical"
    assert item["suggestedPriority"] == "P0"


def test_amend_kind_change_does_not_alter_suggested_domain(tmp_path: Path):
    item_id = _seed(tmp_path, source="compliance", kind="bug")
    before_domain = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)["suggestedDomain"]
    amend_triage_item(tmp_path, item_id, by="sven", kind="maintenance")
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["kind"] == "maintenance"
    assert item["suggestedDomain"] == before_domain


def test_amend_ordering_interleaves_with_status_by_ts(tmp_path: Path):
    """A later `status` must win over an earlier `amend` and vice versa —
    same merged pass, not two independent overlays."""
    item_id = _seed(tmp_path)
    path = Path(tmp_path) / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(
            '{"event":"status","id":"%s","ts":"2026-08-08T10:00:00Z",'
            '"newStatus":"dismissed","by":"a","reason":null,"promotedTaskId":null}\n' % item_id
        )
        fp.write(
            '{"event":"amend","id":"%s","ts":"2026-08-08T11:00:00Z",'
            '"by":"b","title":"later amend wins"}\n' % item_id
        )
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "later amend wins"
    assert item["status"] == "dismissed"  # unaffected — amend never touches status


def test_equal_ts_amends_tiebreak_on_file_order(tmp_path: Path):
    """Two amends at the SAME `ts`: the sort key is `(ts, file-order)`, so the
    LATER line in the file wins the tie, not an arbitrary/unstable order."""
    item_id = _seed(tmp_path)
    path = Path(tmp_path) / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8") as fp:
        fp.write('{"event":"amend","id":"%s","ts":"2026-08-08T12:00:00Z","by":"a","title":"first"}\n' % item_id)
        fp.write('{"event":"amend","id":"%s","ts":"2026-08-08T12:00:00Z","by":"b","title":"second"}\n' % item_id)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "second"
    assert item["amendedBy"] == "b"


def test_malformed_ts_amend_sorts_earliest(tmp_path: Path):
    """A missing/non-string `ts` coerces to "" and sorts EARLIEST, so a
    well-formed later amend still wins over it regardless of file order."""
    item_id = _seed(tmp_path)
    path = Path(tmp_path) / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8") as fp:
        # Malformed ts written AFTER the well-formed one in file order — if
        # malformed did not sort earliest, this would win instead.
        fp.write('{"event":"amend","id":"%s","ts":"2026-08-08T12:00:00Z","by":"a","title":"well-formed"}\n' % item_id)
        fp.write('{"event":"amend","id":"%s","ts":null,"by":"b","title":"malformed ts"}\n' % item_id)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "well-formed"


def test_status_and_amend_at_the_same_ts_both_apply(tmp_path: Path):
    """A `status` and an `amend` sharing one `ts` act on DISJOINT fields, so
    both must apply regardless of which the merged (ts, file-order) sort
    visits first — a compositional proof the merged pass is correct."""
    item_id = _seed(tmp_path)
    path = Path(tmp_path) / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(
            '{"event":"amend","id":"%s","ts":"2026-08-08T12:00:00Z",'
            '"by":"a","title":"corrected"}\n' % item_id
        )
        fp.write(
            '{"event":"status","id":"%s","ts":"2026-08-08T12:00:00Z",'
            '"newStatus":"dismissed","by":"b","reason":null,"promotedTaskId":null}\n' % item_id
        )
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "corrected"
    assert item["status"] == "dismissed"


def test_later_invalid_amend_does_not_clobber_a_prior_valid_amends_metadata(tmp_path: Path):
    """A later amend that fails validation is skipped WHOLE — including its
    `amendedBy`/`amendedAt` — so it must not erase the metadata a prior valid
    amend already set.

    Both lines are hand-written with FIXED timestamps rather than letting the
    valid one pick up `_now_z()` — a wall-clock ts made this test date-fragile
    (it would silently stop exercising the ordering it claims to pin once the
    real date moved past the invalid line's hardcoded ts)."""
    item_id = _seed(tmp_path)
    path = Path(tmp_path) / ".shipwright" / "triage.jsonl"
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(
            '{"event":"amend","id":"%s","ts":"2026-08-08T12:00:00Z",'
            '"by":"sven","title":"valid correction"}\n' % item_id
        )
        fp.write(
            '{"event":"amend","id":"%s","ts":"2026-08-08T23:59:59Z",'
            '"by":"intruder","severity":"urgent"}\n' % item_id  # unknown severity: invalid
        )
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "valid correction"
    assert item["amendedBy"] == "sven"


def test_multiple_amends_last_valid_wins_per_field(tmp_path: Path):
    item_id = _seed(tmp_path)
    amend_triage_item(tmp_path, item_id, by="a", title="first")
    amend_triage_item(tmp_path, item_id, by="b", detail="second detail")
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == "first"
    assert item["detail"] == "second detail"
    assert item["amendedBy"] == "b"


# --- locking discipline (AC14, mirrors test_mark_status_acquires_the_canonical_lock_exactly_once) --

def test_amend_triage_item_acquires_the_canonical_lock_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real_cls = triage._load_file_lock_cls()
    acquisitions = []

    class CountingLock(real_cls):  # type: ignore[misc,valid-type]
        def __enter__(self):
            acquisitions.append(1)
            return super().__enter__()

    item_id = _seed(tmp_path)
    monkeypatch.setattr(triage, "_load_file_lock_cls", lambda: CountingLock)
    amend_triage_item(tmp_path, item_id, by="sven", title="new title")
    assert sum(acquisitions) == 1


# --- Boundary Probe: real-file round-trip (touches_io_boundary) -------------

def test_amend_round_trips_unicode_and_special_characters(tmp_path: Path):
    """write → real disk → fresh read must not lose or mangle a byte. Exercises
    the `ensure_ascii=False` JSONL write path plus JSON-string escaping for
    quotes/newlines/backslashes, on an ACTUAL file (not an in-memory fixture)."""
    item_id = _seed(tmp_path)
    tricky_title = 'ünïcödé 日本語 🎉 "quoted" back\\slash'
    tricky_detail = "line one\nline two\ttabbed"
    amend_triage_item(tmp_path, item_id, by="sven", title=tricky_title, detail=tricky_detail)

    # Force a genuinely fresh read: re-import-free, just re-invoke against the
    # same on-disk path with no cached state involved.
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["title"] == tricky_title
    assert item["detail"] == tricky_detail

    raw_bytes = (Path(tmp_path) / ".shipwright" / "triage.jsonl").read_bytes()
    assert "ünïcödé 日本語 🎉".encode() in raw_bytes  # ensure_ascii=False, not \uXXXX-escaped
