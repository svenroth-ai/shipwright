"""The sweep must never eat an operator's dismiss (real git, no mocks).

WHY THIS FILE EXISTS. Reproduced live in shipwright-webui on 2026-07-14: triage
item trg-6db81c59 kept resurfacing on the board after every dismiss. Two defects
compounded into a loop that SILENTLY destroyed operator dismisses.

* **Defect A** — an ``append`` written into MAIN's *tracked* ``triage.jsonl``
  while still uncommitted is delivered by nothing: the sweep folds only the
  gitignored outbox, and ``reconcile_main_triage`` is a manual CLI nobody calls.
  The append rots in the working tree, invisible to origin and to every worktree.
* **Defect B** — ``sweep_quarantine.decide`` classified orphan-status over
  worktree-tracked ∪ outbox ONLY. A ``status`` for such a drift-only append MUST
  look like an orphan, so it was quarantined AND deleted from the outbox while the
  sweep reported success. The reader still saw the append (it unions main's tracked
  log), the dismiss was gone → the item reappeared → dismiss again → eaten again.

The #303 quarantine turned a loud hard-block into quiet data loss. These tests pin
the repaired contract: the drift append is ROUTED to the outbox (the real delivery
channel), a status whose append is known from main is never an orphan, and a
quarantine can never remove the operator's only dismiss.
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
from lib.sweep_text import read_text_verbatim  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch, sweep_warnings  # noqa: E402
from lib.sweep_quarantine import decide  # noqa: E402

APPEND = "trg-6db81c59"  # the webui item, by name — this is a regression pin


@pytest.fixture
def repo(git_origin_repo):
    work, _origin = git_origin_repo
    h.set_identity(work)
    return work


def drift_append(work: Path, *lines: str) -> None:
    """Append to MAIN's TRACKED triage log WITHOUT committing — the exact shape
    ``git status`` showed in webui (``M .shipwright/triage.jsonl``, +2 lines)."""
    with (work / h.TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def tracked_is_clean(work: Path) -> bool:
    return not h.git(work, "status", "--porcelain", "--", h.TRIAGE).stdout.strip()


# --- AC1/AC2: the orphan universe (unit) ------------------------------------

def test_status_whose_append_is_only_in_main_tracked_is_not_an_orphan() -> None:
    """The heart of Defect B. The dismiss is a legitimate status — its append is
    real, it just lives in main's tracked log. It must NOT be a quarantine
    candidate; with the append unplaceable the sweep fails CLOSED (loud) instead."""
    worktree = [h.HEADER, h.item("trg-other")]
    dismiss = h.status(APPEND, "dismissed")

    protected = decide(worktree, [dismiss], "\n", known_append_ids=frozenset({APPEND}))

    assert protected.action == "block", protected
    assert dismiss not in protected.candidates, "the operator's dismiss was made a quarantine candidate"


def test_the_old_universe_is_what_ate_the_dismiss() -> None:
    """The defect, pinned. With the pre-fix universe (worktree-tracked ∪ outbox only)
    the very same dismiss IS a quarantine candidate — it gets moved to the quarantine
    log and deleted from the outbox while the sweep reports success. Nothing else about
    the sweep changed; the universe is the whole bug."""
    dismiss = h.status(APPEND, "dismissed")

    old = decide([h.HEADER, h.item("trg-other")], [dismiss], "\n")  # no known_append_ids

    assert old.action == "quarantine" and old.candidates == [dismiss]


def test_a_status_whose_append_exists_nowhere_is_still_quarantined() -> None:
    """The genuine-orphan class (#303) is untouched: no append anywhere → quarantine,
    so one broken record cannot strand every other pending append."""
    orphan = h.status("trg-ghost", "dismissed")

    d = decide([h.HEADER, h.item("trg-other")], [orphan], "\n", known_append_ids=frozenset({APPEND}))

    assert d.action == "quarantine"
    assert d.candidates == [orphan]


def test_decide_is_clean_once_the_drift_append_rides_the_outbox() -> None:
    """The repair (AC3) dissolves the orphan at the source: with the append routed
    into the outbox, the materialized log validates and nothing is quarantined."""
    d = decide(
        [h.HEADER], [h.item(APPEND), h.status(APPEND, "dismissed")], "\n",
        known_append_ids=frozenset({APPEND}),
    )

    assert d.action == "clean", d
    assert d.candidates == []


# --- AC3: main-tracked drift is routed into the outbox (real git) -----------

def test_main_tracked_drift_append_is_routed_into_the_outbox(repo) -> None:
    """Defect A. The append exists in NO git object — only as an uncommitted
    modification of main's tracked log. After the sweep it is on the branch (→ PR →
    origin) and main's tracked log is clean again."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    drift_append(work, h.item(APPEND))
    assert not tracked_is_clean(work), "fixture failed to create the drift"
    wt = h.make_worktree(work, "drift-route")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.adopted == 1, result.to_dict()
    assert h.item(APPEND) in h.branch_triage_lines(wt), "the drift append never reached the branch"
    assert tracked_is_clean(work), "main's tracked log still carries undelivered drift"


def test_the_operators_only_dismiss_survives_the_sweep(repo) -> None:
    """The webui shape, end to end: a drift append on main + the operator's dismiss
    in the outbox. Before the fix the dismiss was quarantined and deleted, the sweep
    reported success, and the item resurrected. Now both lines ride the branch and
    the reader resolves the item to ``dismissed``."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    drift_append(work, h.item(APPEND))
    h.write_outbox(work, h.status(APPEND, "dismissed"))
    wt = h.make_worktree(work, "drift-dismiss")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.quarantined == 0, "the operator's dismiss was quarantined"
    assert h.quarantine_text(work) == "", "a dismiss was moved to the quarantine log"
    branch = h.branch_triage_lines(wt)
    assert h.item(APPEND) in branch and h.status(APPEND, "dismissed") in branch
    resolved = {i["id"]: i["status"] for i in triage.read_all_items(wt)}
    assert resolved[APPEND] == "dismissed", "the reader still shows the item as open — it would resurface"


def test_crlf_main_tracked_log_stays_clean_after_the_repair(repo) -> None:
    """Probe: the Windows/autocrlf shape — where this bug was actually found. The
    repair REWRITES main's tracked log, so it must round-trip the file's own EOL
    style; emitting LF over a CRLF checkout would trade the drift for a whole-file
    diff. The checkout is done by git itself (delete + restore under
    ``core.autocrlf``), because a hand-written CRLF file is genuinely modified to git
    and would not prove anything."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    h.git(work, "config", "core.autocrlf", "true")
    (work / h.TRIAGE).unlink()
    h.git(work, "checkout", "--", h.TRIAGE)  # git writes CRLF + records the stat
    assert tracked_is_clean(work) and b"\r\n" in (work / h.TRIAGE).read_bytes()
    with (work / h.TRIAGE).open("a", encoding="utf-8", newline="") as fh:
        fh.write(h.item(APPEND) + "\r\n")
    wt = h.make_worktree(work, "drift-crlf")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.adopted == 1, result.to_dict()
    assert tracked_is_clean(work), "the EOL round-trip left main's tracked log dirty"
    assert b"\r\n" in (work / h.TRIAGE).read_bytes(), "the file's CRLF style was normalized away"


# --- AC4: the divergence guard ----------------------------------------------

def test_a_diverged_main_tracked_log_refuses_to_run_and_touches_nothing(repo) -> None:
    """If main's tracked log is MISSING lines that HEAD has, we do not understand its
    state — and rewriting a file you don't understand is the move that caused this bug.
    Refuse loudly, mutate nothing, leave the repair to the operator."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"), h.item("trg-keep"))
    # A HEAD line deleted (divergence) AND a new drift append: not append-only.
    body = "\n".join([h.HEADER, h.item("trg-seed"), h.item(APPEND)]) + "\n"
    (work / h.TRIAGE).write_text(body, encoding="utf-8", newline="")
    h.write_outbox(work, h.item("trg-pending"))
    wt = h.make_worktree(work, "drift-diverged")
    before_head = h.git(wt, "rev-parse", "HEAD").stdout.strip()

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "skipped", result.to_dict()
    assert result.reason.startswith("main_tracked_diverged"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body, "the diverged log was rewritten"
    assert h.outbox_lines(work) == {h.item("trg-pending")}, "the outbox was mutated"
    assert h.git(wt, "rev-parse", "HEAD").stdout.strip() == before_head


# --- AC5: the operator actually sees it -------------------------------------

def test_sweep_warnings_surface_quarantine_and_adoption() -> None:
    """``SweepResult.quarantined`` was returned and never shown — a quarantine looked
    exactly like a clean run. Both counts must reach the operator."""
    from lib.sweep_outbox import SweepResult

    notes = sweep_warnings(SweepResult(status="committed", swept=1, quarantined=2, adopted=3))

    joined = " ".join(notes)
    assert "quarantine" in joined.lower() and "2" in joined
    assert "3" in joined and "drift" in joined.lower()
    assert sweep_warnings(SweepResult(status="no_change", reason="empty_outbox")) == []
