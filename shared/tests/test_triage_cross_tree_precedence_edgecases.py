"""`triage.read_all_items` cross-tree status precedence — edge cases.

Split out of `test_triage_cross_tree_precedence.py` (300-line guideline).
External-review-driven (openai/glm, iterate-2026-09-10-triage-cross-tree-
precedence): the drop-filter must remove ONLY a foreign `status` whose id is
already locally decided — it must not affect ordering among foreign events
for an id with no local decision, and it must not touch `amend` tie-break
behavior at all.
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
    main = tmp_path / "main"
    (main / ".shipwright").mkdir(parents=True)
    (main / ".git").mkdir()
    return main


def _make_worktree(main: Path, slug: str, branch: str) -> Path:
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


def test_multiple_foreign_status_events_for_a_never_decided_id_still_resolve_chronologically(
    tmp_path: Path,
) -> None:
    """The drop-filter must remove ONLY a foreign status whose id is already
    locally decided — it must not accidentally collapse to a single foreign
    event for an id with no local decision at all. Two foreign status events
    for the same never-decided id resolve to the chronologically later one,
    same as before this fix."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    first_foreign = {**_DISMISS, "by": "first-sibling"}
    second_foreign = {
        "event": "status", "id": "trg-good0001", "ts": "2026-01-03T00:00:00Z",
        "newStatus": "snoozed", "by": "second-sibling", "reason": "later",
        "revisitAt": "2099-01-01",
    }
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(first_foreign) + "\n"
        + _j(second_foreign) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["status"] == "snoozed"
    assert item["statusBy"] == "second-sibling"


def test_a_local_and_foreign_amend_tie_still_resolves_by_file_order_not_origin(
    tmp_path: Path,
) -> None:
    """The fix must not accidentally change the existing `(ts, file-order)`
    tie behavior for `amend` — a foreign amend at the SAME timestamp as a
    local one for the same id still wins the tie by file order (foreign is
    appended after local in `raw_lines`), exactly as before this fix. Amend
    is out of scope for the new precedence rule."""
    main = _make_main(tmp_path)
    local_amend = {
        "event": "amend", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
        "by": "local-cli", "title": "local title",
    }
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(local_amend) + "\n",
        encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    foreign_amend = {**local_amend, "by": "foreign-cli", "title": "foreign title"}
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(foreign_amend) + "\n",
        encoding="utf-8")

    item = next(i for i in triage.read_all_items(main) if i["id"] == "trg-good0001")
    assert item["title"] == "foreign title"


def test_a_foreign_status_with_a_non_string_id_does_not_crash_the_read(
    tmp_path: Path,
) -> None:
    """External code review (glm): the drop-filter's foreign-side `in
    local_status_ids` set-membership check must guard `isinstance(id, str)`
    just like the local side already does — an unhashable foreign `id`
    (list/dict, a corrupted sibling-log line) must not raise `TypeError` and
    take down the whole board read; it is simply skipped like any other
    status event for an unknown/malformed id."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    corrupt_id_status = {
        "event": "status", "id": ["not", "a", "string"],
        "ts": "2026-01-03T00:00:00Z", "newStatus": "dismissed", "by": "sibling",
    }
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(corrupt_id_status) + "\n",
        encoding="utf-8")

    items = triage.read_all_items(main)  # must not raise TypeError

    item = next(i for i in items if i["id"] == "trg-good0001")
    assert item["status"] == "triage"


def test_read_all_items_composes_local_and_sibling_stores_for_ids_never_locally_decided(
    tmp_path: Path,
) -> None:
    """category:integration — proves the local tracked/outbox reader and the
    cross-tree sibling-log reader still compose end to end through the public
    `read_all_items` entry point: one id resolved purely from main's own
    files, a second id (main knows the append, never decided its status)
    filled in from a sibling's tracked log, in the SAME read."""
    main = _make_main(tmp_path)
    local_only = {**_APPEND, "id": "trg-local001"}
    known_but_undecided = {**_APPEND, "id": "trg-good0001"}
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(local_only) + "\n" + _j(known_but_undecided) + "\n",
        encoding="utf-8")
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(known_but_undecided) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")

    items = {i["id"]: i for i in triage.read_all_items(main)}
    assert items["trg-local001"]["status"] == "triage"
    assert items["trg-good0001"]["status"] == "dismissed"
    assert items["trg-good0001"]["statusBy"] == "cli"
