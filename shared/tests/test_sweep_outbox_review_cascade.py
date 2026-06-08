"""D2 review-cascade remediation (part 1) — EMPIRICAL tests for FIX A / B / F.

The D2 sweep+GC is the most data-loss-sensitive unit in the campaign; a review
cascade hardened five edges. FIX C/D/E live in
``test_sweep_outbox_review_cascade2.py`` (split to keep each module < 300 LOC).
Each fix is proven here with REAL git repos + REAL worktrees + the REAL canonical
lock + the REAL producer path — NOTHING is mocked (mocking the lock or git would
let a real loss slip through).

* FIX A (LF outbox): the producer writes the gitignored outbox as LF on every
  platform, then the real sweep delivers it exactly-once.
* FIX B (GC by id): a delivered append is GC'able even if re-serialized with a
  different key order / whitespace; a non-delivered id always survives; status
  lines still text-match; missing origin → nothing GC'd.
* FIX F (swept-count comment): exercised implicitly by the swept-count asserts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
import triage  # noqa: E402
from lib import sweep_gc  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402

TRIAGE = h.TRIAGE


@pytest.fixture
def repo(git_origin_repo):
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


# --------------------------------------------------------------------------- #
# FIX A — producer writes the OUTBOX as LF on all platforms, swept exactly-once
# --------------------------------------------------------------------------- #


def test_producer_writes_outbox_as_lf(repo) -> None:
    """The REAL ``append_triage_item(to_outbox=True)`` writes the gitignored
    outbox with LF bytes (no CRLF) on the running platform, then the REAL sweep
    delivers that line exactly-once onto the branch — a full producer round-trip,
    not a hand-written fixture line."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "fixa-lf")

    item_id = triage.append_triage_item(
        work, source="plugin-sync", severity="low", kind="maintenance",
        title="bg finding", detail="d", to_outbox=True,
    )

    # (a) the outbox bytes are LF — no CRLF anywhere, even on Windows.
    raw = (work / h.OUTBOX).read_bytes()
    assert b"\r\n" not in raw, raw
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1  # exactly one LF-terminated line

    # (b) the real sweep folds it onto the branch exactly-once.
    result = sweep_outbox_to_branch(work, wt, default_branch="main")
    assert result.status == "committed", result.to_dict()
    branch = [ln for ln in h.branch_triage_lines(wt) if f'"id":"{item_id}"' in ln]
    assert len(branch) == 1, branch


# --------------------------------------------------------------------------- #
# FIX B — GC drops by APPEND ID (serialization-drift-immune), not raw text
# --------------------------------------------------------------------------- #


def _append(iid: str, *, title: str = "x", extra: str = "") -> str:
    """An append line whose ``id`` is ``iid`` (extra widens the serialization)."""
    body = (
        f'{{"event":"append","id":"{iid}","ts":"2026-06-08T00:00:00Z",'
        f'"title":"{title}","status":"triage"{extra}}}'
    )
    return body


def test_gc_drops_delivered_append_even_if_reserialized(repo) -> None:
    """FIX B core: origin carries the delivered append with ONE serialization;
    the outbox carries the SAME id re-serialized differently (an added key → the
    bytes differ, the id does not). The GC must still drop the outbox copy because
    membership is by id, NOT raw text.

    The branch (from main) already carries the re-serialized form so the verbatim
    sweep does not double the id at materialize — this test isolates the GC's
    delivered-membership decision, which is the only thing FIX B changed."""
    work, _ = repo
    reserialized = _append("trg-deliv", extra=',"detail":"re-serialized"')
    canonical = _append("trg-deliv")
    assert reserialized != canonical  # precondition: bytes differ, id identical
    # The BRANCH/origin tracked log carries the re-serialized form (so materialize
    # sees the id once); but origin's delivered form is the CANONICAL bytes.
    h.seed_tracked(work, h.item("trg-aaaa"), reserialized)
    wt = h.make_worktree(work, "fixb-reser")
    # Advance origin/main so its delivered copy uses the CANONICAL serialization
    # (the "future producer re-serialized it differently" shape).
    (work / TRIAGE).write_text(
        "\n".join([h.HEADER, h.item("trg-aaaa"), canonical]) + "\n",
        encoding="utf-8", newline="\n",
    )
    h.git(work, "commit", "-am", "origin canonicalizes trg-deliv")
    h.git(work, "push", "origin", "main")
    # The outbox holds the re-serialized copy (its id IS delivered in origin).
    p = work / h.OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(reserialized + "\n", encoding="utf-8", newline="\n")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    # The re-serialized outbox line is recognised as delivered (by id) → GC'd,
    # even though its raw bytes never appear in origin.
    assert result.gc_dropped == 1, result.to_dict()
    assert reserialized not in h.outbox_lines(work)


def test_gc_keeps_undelivered_id(repo) -> None:
    """An outbox append whose id is NOT in origin must SURVIVE the GC."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))  # origin has NO trg-fresh
    h.write_outbox(work, _append("trg-fresh"))
    wt = h.make_worktree(work, "fixb-keep")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.gc_dropped == 0, result.to_dict()
    assert _append("trg-fresh") in h.outbox_lines(work)


def test_gc_status_line_still_text_matches(repo) -> None:
    """A status line (no stable append id to key on) is GC'd iff its raw stripped
    text is in origin — the text path is preserved for non-append lines."""
    work, _ = repo
    status_line = (
        '{"event":"status","id":"trg-aaaa","ts":"2026-06-08T00:00:05Z",'
        '"newStatus":"dismissed","by":"op"}'
    )
    # origin carries BOTH the append (so validate passes) AND the status line.
    h.seed_tracked(work, h.item("trg-aaaa"), status_line)
    # Outbox carries the same status text (delivered) + a fresh append (kept).
    h.write_outbox(work, status_line, _append("trg-new"))
    wt = h.make_worktree(work, "fixb-status")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    survivors = h.outbox_lines(work)
    assert status_line not in survivors            # text-matched → GC'd
    assert _append("trg-new") in survivors         # not in origin → kept
    assert result.gc_dropped == 1, result.to_dict()


def test_gc_missing_origin_drops_nothing(repo) -> None:
    """No ``origin/<default>`` ref → empty membership → nothing GC'd (fail-safe).

    Drives the sweep with a default_branch that does not exist on origin; the
    line stays buffered (existing fail-safe behavior, unchanged by FIX B)."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    h.write_outbox(work, _append("trg-bbbb"))
    wt = h.make_worktree(work, "fixb-noorigin")

    result = sweep_outbox_to_branch(work, wt, default_branch="does-not-exist")

    assert result.gc_dropped == 0, result.to_dict()
    assert _append("trg-bbbb") in h.outbox_lines(work)


def test_sweep_gc_membership_unit() -> None:
    """Pure membership unit (no git): id-match for appends, text for status,
    unparseable → text path, and an undelivered id survives."""
    a_canon = _append("trg-1")
    a_reser = _append("trg-1", extra=',"detail":"x"')
    status = '{"event":"status","id":"trg-1","newStatus":"dismissed"}'
    origin = {a_canon.strip(), status, "garbage-not-json"}
    ids, text = sweep_gc.parse_delivered(origin)
    assert ids == {"trg-1"}
    assert status in text and "garbage-not-json" in text
    # Re-serialized append: delivered by id.
    assert sweep_gc.is_delivered(a_reser.strip(), ids, text) is True
    # Undelivered append id: survives.
    assert sweep_gc.is_delivered(_append("trg-9").strip(), ids, text) is False
    # Status line: text-matched.
    assert sweep_gc.is_delivered(status, ids, text) is True
    # Unparseable line present in text: delivered; absent: survives.
    assert sweep_gc.is_delivered("garbage-not-json", ids, text) is True
    assert sweep_gc.is_delivered("other-garbage", ids, text) is False
