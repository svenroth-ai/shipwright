"""Cross-tree decision visibility — measured 2026-09-06, trg-5e0b9b16 / trg-e85c5c8e.

A decision (dismiss, amend, ...) recorded directly in a worktree's TRACKED
``.shipwright/triage.jsonl`` used to be invisible to ``main`` reading its own
store: `read_all_items` only ever unioned ONE tree's own tracked + outbox
files, so an item dismissed only in a worktree read back on `main` as still
open, with `pendingDelivery` computing `False` — a false reassurance. RED-
before-fix scenario, kept as the permanent regression gate. See
:mod:`lib.triage_cross_tree` for the fix; the CLI subprocess round-trip lives
in `test_triage_cross_tree_cli_roundtrip.py` (split out at 300 lines).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_SCRIPTS = _SHARED / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402
from lib import triage_cross_tree  # noqa: E402
from lib.triage_contract import build_listing  # noqa: E402
from lib.triage_delivery import (  # noqa: E402
    foreign_undelivered_amends_from_records,
    foreign_undelivered_from_records,
)


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _make_main(tmp_path: Path) -> Path:
    """A main tree: `.shipwright/` present, `.git` a DIRECTORY (not a file)."""
    main = tmp_path / "main"
    (main / ".shipwright").mkdir(parents=True)
    (main / ".git").mkdir()
    return main


def _make_worktree(main: Path, slug: str, branch: str) -> Path:
    """A linked worktree under `main/.worktrees/<slug>`: `.git` is a FILE naming
    an admin dir whose `HEAD` names `branch` — the real git worktree shape,
    reproduced without an actual git process."""
    wt = main / ".worktrees" / slug
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / slug
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return wt


_APPEND = {
    "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
    "title": "t", "status": "triage", "severity": "low", "kind": "bug",
    "source": "manual", "detail": "d",
}
_DISMISS = {
    "event": "status", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "newStatus": "dismissed", "by": "cli", "reason": "done",
}


# ---------------------------------------------------------------------------
# lib.triage_cross_tree — discovery
# ---------------------------------------------------------------------------

def test_sibling_worktree_logs_finds_a_branch_and_its_tracked_log(tmp_path: Path) -> None:
    main = _make_main(tmp_path)
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n", encoding="utf-8")

    found = triage_cross_tree.sibling_worktree_logs(main)
    assert found == [("iterate/camp-a", wt / ".shipwright" / "triage.jsonl")]


def test_sibling_worktree_logs_is_empty_from_inside_a_worktree(tmp_path: Path) -> None:
    """The fold-in is main-tree-only — a worktree must never recurse into its
    own (normally absent) `.worktrees`, even if one somehow exists."""
    main = _make_main(tmp_path)
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n", encoding="utf-8")
    # A stray nested .worktrees inside the worktree itself must not be walked.
    (wt / ".worktrees" / "nested" / ".shipwright").mkdir(parents=True)

    assert triage_cross_tree.sibling_worktree_logs(wt) == []


def test_sibling_worktree_logs_empty_with_no_worktrees_dir(tmp_path: Path) -> None:
    main = _make_main(tmp_path)
    assert triage_cross_tree.sibling_worktree_logs(main) == []


def test_a_detached_head_worktree_is_skipped_not_guessed_at(tmp_path: Path) -> None:
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "detached"
    (wt / ".shipwright").mkdir(parents=True)
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n", encoding="utf-8")
    admin = main / ".git" / "worktrees" / "detached"
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("deadbeef" * 5 + "\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == []


# ---------------------------------------------------------------------------
# triage.read_all_items — the board itself
# ---------------------------------------------------------------------------

def test_a_dismiss_recorded_only_in_a_worktree_resolves_as_dismissed_on_main(
    tmp_path: Path,
) -> None:
    """The exact measured defect: main must not show this as open `triage`."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "dismissed"


def test_a_foreign_append_never_seeds_an_item_this_tree_never_created(
    tmp_path: Path,
) -> None:
    """Only KNOWN ids fold in — a sibling's own item must not appear on main."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n", encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    foreign_only = {**_APPEND, "id": "trg-foreignonly"}
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(foreign_only) + "\n", encoding="utf-8")

    assert triage.read_all_items(main) == []


def test_a_foreign_tie_is_broken_by_file_order_not_origin(tmp_path: Path) -> None:
    """`read_all_items`' tie-break is pure ``(ts, file-order)`` with no special
    case for physical origin (same rule as the existing tracked-before-outbox
    precedent) — the foreign tail is appended last, so it wins an identical
    timestamp even against main's own tracked copy. Distinguishing `by` values
    make the winner provable. This is safe regardless of which copy wins:
    `pendingDelivery`'s canonical-content check (`lib.triage_delivery`)
    answers "delivered" from content equality, not from this tie-break."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    foreign_dismiss = {**_DISMISS, "by": "worktree-cli"}
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(foreign_dismiss) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "dismissed"
    assert item["statusBy"] == "worktree-cli"


# ---------------------------------------------------------------------------
# lib.triage_delivery — the pending marker + branch attribution
# ---------------------------------------------------------------------------

def test_foreign_undelivered_from_records_names_the_branch(tmp_path: Path) -> None:
    foreign = [("iterate/camp-a", [_APPEND, _DISMISS])]
    pending = foreign_undelivered_from_records(
        [_APPEND], [], foreign, applied_statuses=triage.STATUSES)
    assert pending == {"trg-good0001": "iterate/camp-a"}


def test_foreign_undelivered_from_records_empty_once_tracked_has_the_deciding_event(
) -> None:
    """Second test in the report: once the event reaches origin's tracked log,
    it must read plain delivered — no pending marker."""
    foreign = [("iterate/camp-a", [_APPEND, _DISMISS])]
    pending = foreign_undelivered_from_records(
        [_APPEND, _DISMISS], [], foreign, applied_statuses=triage.STATUSES)
    assert pending == {}


def test_foreign_undelivered_from_records_requires_a_known_append() -> None:
    orphan_dismiss = {**_DISMISS, "id": "trg-orphan01"}
    foreign = [("iterate/camp-a", [orphan_dismiss])]
    pending = foreign_undelivered_from_records(
        [], [], foreign, applied_statuses=triage.STATUSES)
    assert pending == {}


def test_foreign_undelivered_amends_names_the_branch() -> None:
    amend = {"event": "amend", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
              "by": "cli", "title": "corrected"}
    foreign = [("iterate/camp-a", [_APPEND, amend])]
    pending = foreign_undelivered_amends_from_records(
        [_APPEND], foreign, is_valid_amend=lambda _e: True)
    assert pending == {"trg-good0001": "iterate/camp-a"}


def test_build_listing_names_the_branch_in_the_terminal_envelope_blocks() -> None:
    """Unit-level pin of the envelope shape, independent of the CLI subprocess."""
    payload = build_listing(
        [], [],
        tracked_ids={"trg-good0001"}, outbox_ids=set(),
        severity_rank={"low": 3},
        undelivered_status_ids={"trg-good0001"},
        undelivered_amend_ids=set(),
        corruption=[],
        status_origin_branches={"trg-good0001": "iterate/camp-a"},
    )
    assert payload["undeliveredDecisions"]["originBranches"] == {
        "trg-good0001": "iterate/camp-a"}
    assert payload["undeliveredAmends"]["originBranches"] == {}


def test_build_listing_keeps_status_and_amend_branches_separate() -> None:
    """Stage-3 doubt review, finding 2: a status decision on one branch and an
    amend on ANOTHER branch, for the SAME id, must not collapse into one
    branch name shared by both envelope blocks — each block must report its
    OWN origin."""
    payload = build_listing(
        [], [],
        tracked_ids={"trg-good0001"}, outbox_ids=set(),
        severity_rank={"low": 3},
        undelivered_status_ids={"trg-good0001"},
        undelivered_amend_ids={"trg-good0001"},
        corruption=[],
        status_origin_branches={"trg-good0001": "iterate/camp-b"},
        amend_origin_branches={"trg-good0001": "iterate/camp-a"},
    )
    assert payload["undeliveredDecisions"]["originBranches"] == {
        "trg-good0001": "iterate/camp-b"}
    assert payload["undeliveredAmends"]["originBranches"] == {
        "trg-good0001": "iterate/camp-a"}


def test_build_listing_origin_branches_defaults_to_empty() -> None:
    """The param is optional — every EXISTING call site keeps working."""
    payload = build_listing(
        [{"id": "trg-x", "status": "triage", "severity": "low"}], [],
        tracked_ids={"trg-x"}, outbox_ids=set(), severity_rank={"low": 3},
        undelivered_status_ids=set(), undelivered_amend_ids=set(), corruption=[],
    )
    assert payload["open"][0]["originBranch"] is None
    assert payload["undeliveredDecisions"]["originBranches"] == {}


# ---------------------------------------------------------------------------
# Discovery caching — must not go stale forever within one process
# ---------------------------------------------------------------------------

def test_sibling_discovery_cache_picks_up_a_worktree_added_later(
    tmp_path: Path,
) -> None:
    """The FIRST call here actually populates `_DISCOVERY_CACHE` (there is
    already one sibling, so `.worktrees` exists and the walk's result is
    cached) — unlike calling on a not-yet-existing `.worktrees`, which returns
    before ever touching the cache. The second call must see the newly added
    sibling too, proving the cache invalidates rather than sticking forever."""
    main = _make_main(tmp_path)
    wt_a = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt_a / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n", encoding="utf-8")

    first = triage_cross_tree.sibling_worktree_logs(main)
    assert first == [("iterate/camp-a", wt_a / ".shipwright" / "triage.jsonl")]

    wt_b = _make_worktree(main, "camp-b", "iterate/camp-b")
    (wt_b / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n", encoding="utf-8")

    found = triage_cross_tree.sibling_worktree_logs(main)
    assert found == [
        ("iterate/camp-a", wt_a / ".shipwright" / "triage.jsonl"),
        ("iterate/camp-b", wt_b / ".shipwright" / "triage.jsonl"),
    ]
