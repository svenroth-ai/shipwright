"""`triage.read_all_items` — cross-tree status precedence.

Split out of `test_triage_cross_tree_delivery.py` (300-line guideline).
A local `status` decision (this tree's own tracked+outbox union) always wins
over a foreign (sibling-worktree) `status` event for the same id — a foreign
status is applied only to fill a gap for an id this tree has never decided.
`amend` events are unaffected and stay purely chronological.

Fix for the measured defect (2026-09-10, trg-74ef24ce): a sibling worktree
abandoned after its branch stalled can carry a `status -> triage` reopen
event dated after this tree's own dismiss, resurrecting an already-dismissed
card purely because pass 2's old rule was ``(ts, file-order)`` with no
per-origin precedence. See `lib.triage_cross_tree`'s module docstring for the
sibling-discovery/parsing side this reads from. Further edge cases (multiple
foreign events, amend tie-break, local+sibling composition) live in
`test_triage_cross_tree_precedence_edgecases.py` (same reason).
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


def test_a_local_status_wins_an_exact_timestamp_tie_against_a_foreign_status(
    tmp_path: Path,
) -> None:
    """Corrected precedence (measured 2026-09-10, trg-74ef24ce): a foreign
    `status` event for an id is applied ONLY when this tree's own
    tracked+outbox union has NO `status` event for that id at all. Here main's
    own tracked log already decided (dismissed) — the foreign copy of the
    same decision at an identical timestamp must not be consulted, let alone
    win a tie. (Formerly this test asserted the opposite — the foreign event
    winning an exact tie against a LOCAL decision was the mechanism of the
    measured bug, just with matching timestamps instead of a later one.)
    `pendingDelivery`'s canonical-content check (`lib.triage_delivery`) is
    unaffected — it answers "delivered" from content equality, not from this
    precedence rule."""
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
    assert item["statusBy"] == "cli"


def test_a_chronologically_later_foreign_status_cannot_override_a_local_decision(
    tmp_path: Path,
) -> None:
    """The exact measured defect (trg-74ef24ce): main's own tracked log
    dismissed this id on 2026-07-28. An abandoned sibling worktree, last
    touched 2026-08-10, still carries a `status -> triage` (reopen) event
    dated AFTER the dismiss. The reopen must not resurrect the card — a local
    decision is never overruled by a sibling, however much later its
    timestamp."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")
    wt = _make_worktree(
        main, "p2-59-branch-feedback-authority-redo",
        "iterate/p2-59-branch-feedback-authority-redo")
    stale_reopen = {
        "event": "status", "id": "trg-good0001", "ts": "2026-08-10T02:24:23Z",
        "newStatus": "triage", "by": "complianceBacklog", "reason": "complianceRegressed",
    }
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(stale_reopen) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "dismissed"
    assert item["statusBy"] == "cli"


def test_a_foreign_amend_still_resolves_purely_chronologically_even_when_the_id_has_a_local_status(
    tmp_path: Path,
) -> None:
    """The new precedence rule is scoped to `status` events only — `amend`
    (title/detail/severity/kind, no status) keeps the existing pure
    `(ts, file-order)` chronology regardless of whether the id has a local
    status decision, matching the module boundary note (`amend` events "can
    keep pure-chronological ordering")."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    foreign_amend = {
        "event": "amend", "id": "trg-good0001", "ts": "2026-01-03T00:00:00Z",
        "by": "worktree-cli", "title": "corrected title",
    }
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(foreign_amend) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "dismissed"
    assert item["title"] == "corrected title"


def test_a_local_decision_in_the_outbox_only_still_blocks_a_foreign_override(
    tmp_path: Path,
) -> None:
    """D1's tracked+outbox UNION, not just tracked, is what "this tree's own
    decision" means — a status event that has landed in the outbox (not yet
    swept into tracked) must block a foreign override exactly like a tracked
    one would (opus-plan-reviewer finding: no prior test exercised this)."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    (main / ".shipwright" / "triage.outbox.jsonl").write_text(
        _j(_DISMISS) + "\n", encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    stale_reopen = {**_DISMISS, "newStatus": "triage", "ts": "2026-01-03T00:00:00Z",
                    "by": "stale-sibling"}
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(stale_reopen) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "dismissed"
    assert item["statusBy"] == "cli"


def test_a_malformed_local_status_event_does_not_block_a_legitimate_foreign_gap_fill(
    tmp_path: Path,
) -> None:
    """The local-decided-ids gate only counts a VALID `newStatus` (mirrors
    pass 2's own tolerant-skip and `lib.triage_delivery`'s parallel "deciding
    event" filter) — a corrupted local status record (bad `newStatus`, which
    pass 2 already ignores and which never actually changed this item's
    status) must not permanently block a legitimate foreign gap-fill for the
    same id (opus-plan-reviewer finding)."""
    main = _make_main(tmp_path)
    malformed_status = {
        "event": "status", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
        "newStatus": "not-a-real-status", "by": "cli",
    }
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(malformed_status) + "\n",
        encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "dismissed"
    assert item["statusBy"] == "cli"
