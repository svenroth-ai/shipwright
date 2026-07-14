"""The main-tree drift repair refuses anything it does not fully understand.

Split from ``test_sweep_drift.py`` (the AC1-6 core) so each module stays under the
300-LOC guideline. The repair MOVES lines out of a tracked file and rewrites it —
the same class of destructive read-modify-write that caused the bug it fixes. Every
test here pins a state in which it must mutate NOTHING, plus the crash-replay path
that must never double-deliver.

The guards were surfaced by the external plan review (GPT O1/O3/O4, Gemini G2) and
are, deliberately, the majority of this module: the value of an automatic repair is
entirely in what it declines to do.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.sweep_drift import append_ids_of, commit_main_tracked_drift, plan_main_tracked_drift  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from lib.sweep_text import read_text_verbatim  # noqa: E402

DRIFT = h.item("trg-6db81c59")


def adopt(work: Path):
    """Plan + commit in one call — the sweep's two-phase adoption, as the sweep runs it."""
    plan = plan_main_tracked_drift(work, outbox(work))
    if plan.status != "adoptable":
        return plan
    done = commit_main_tracked_drift(plan, work, outbox(work))
    return DriftView(done.status, done.reason, done.adopted, plan.known_append_ids)


class DriftView(NamedTuple):
    status: str
    reason: str
    adopted: int
    known_append_ids: frozenset


@pytest.fixture
def seeded(git_origin_repo):
    """A main tree whose tracked triage log holds one committed item."""
    work, _origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked(work, h.item("trg-seed"))
    return work


def outbox(work: Path) -> Path:
    return work / h.OUTBOX


def write_tracked(work: Path, *lines: str) -> str:
    body = "\n".join(lines) + "\n"
    (work / h.TRIAGE).write_text(body, encoding="utf-8", newline="")
    return body


def test_a_staged_triage_delta_refuses_the_repair(seeded) -> None:
    """GPT O1. Restoring the WORKING file while the drift sits in the INDEX would
    leave it staged — and the operator's next commit on main would resurrect it,
    double-delivering an append the iterate PR already carries."""
    work = seeded
    body = write_tracked(work, h.HEADER, h.item("trg-seed"), DRIFT)
    h.git(work, "add", "--", h.TRIAGE)

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_index_diverged"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body
    assert not outbox(work).exists()


def test_a_reordered_log_is_not_append_only(seeded) -> None:
    """GPT O3. A set-difference test would call this append-only — the HEAD lines are
    all still present. They are not in HEAD's ORDER, so the file is not an extension
    of HEAD and we cannot say which lines are new. Refuse."""
    work = seeded
    h.git(work, "commit", "--allow-empty", "-m", "noop")  # keep HEAD stable
    body = write_tracked(work, h.item("trg-seed"), h.HEADER, DRIFT)  # header no longer first

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_diverged"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body


def test_a_deleted_head_line_refuses_the_repair(seeded) -> None:
    """The plain divergence case: a line HEAD has is gone from the working log. We do
    not understand this file's state, so we do not rewrite it (the operator's call)."""
    work = seeded
    body = write_tracked(work, h.HEADER, DRIFT)  # trg-seed (in HEAD) deleted

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_diverged"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body
    assert not outbox(work).exists()


def test_malformed_drift_is_never_copied_into_the_outbox(seeded) -> None:
    """GPT O4. Adopting corruption would poison the outbox AND hide its source by
    rewriting the tracked file it came from. Validate before any destructive write."""
    work = seeded
    body = write_tracked(work, h.HEADER, h.item("trg-seed"), '{"event":"append" BROKEN')

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_unparseable"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body
    assert not outbox(work).exists(), "a corrupt line reached the delivery buffer"


def test_an_uncommitted_log_is_unrepairable_but_never_blocks_delivery(git_origin_repo) -> None:
    """No ``HEAD:<triage>`` blob (a log that exists but was never committed). There is
    nothing to restore TO, so we move nothing — but this shape is BENIGN, and refusing it
    would strand every pending append in the outbox, trading one delivery failure for
    another. ``unrepairable`` (proceed), not ``refused`` (stop). The append ids are still
    reported: knowing them is what stops a legitimate status dying as an orphan."""
    work, _origin = git_origin_repo
    h.set_identity(work)
    (work / ".shipwright").mkdir(parents=True, exist_ok=True)
    write_tracked(work, h.HEADER, DRIFT)

    result = adopt(work)

    assert result.status == "unrepairable"
    assert result.reason == "main_tracked_no_head_blob"
    assert result.known_append_ids == frozenset({"trg-6db81c59"})
    assert not outbox(work).exists()


def test_an_uncommitted_log_still_lets_the_sweep_deliver_the_outbox(seeded) -> None:
    """The regression the ``unrepairable`` split exists to prevent, in its realistic
    shape: LOCAL main is behind origin (nobody pulled), so main's HEAD has no triage blob
    — while ``origin/main``, and therefore the iterate worktree cut from it, does. The
    repair cannot run, but delivery is perfectly possible. Treating "cannot repair" as
    "must stop" would silently skip the whole sweep and strand every pending append."""
    work = seeded
    h.git(work, "reset", "--hard", "HEAD~1")  # main behind origin: the log is not in HEAD
    assert h.git(work, "show", f"HEAD:{h.TRIAGE}", check=False).returncode != 0
    write_tracked(work, h.HEADER, DRIFT)  # a producer's local log, absent from main's HEAD
    h.write_outbox(work, h.item("trg-pending"))
    wt = h.make_worktree(work, "behind-origin")  # branches from origin/main, which HAS the log

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.adopted == 0, "nothing may be moved when there is no HEAD blob to restore to"
    assert h.item("trg-pending") in h.branch_triage_lines(wt), "the outbox was stranded"
    assert read_text_verbatim(work / h.TRIAGE).count(DRIFT) == 1, "main's log was mutated"


@pytest.mark.parametrize("emptied", [True, False], ids=["emptied", "deleted"])
def test_an_emptied_or_deleted_log_is_the_severest_divergence(seeded, emptied: bool) -> None:
    """External review, GPT (high). A missing/emptied working log whose HEAD blob has
    content is not "no drift" — EVERY HEAD line is gone. Shortcutting to ``no_drift``
    before the HEAD comparison would let the sweep proceed over a state it never read."""
    work = seeded
    if emptied:
        (work / h.TRIAGE).write_text("", encoding="utf-8", newline="")
    else:
        (work / h.TRIAGE).unlink()

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_diverged"), result.reason
    assert not outbox(work).exists()


def test_a_whitespace_only_edit_to_a_head_line_is_not_append_only(seeded) -> None:
    """External review, GPT (medium). Comparing stripped lines would accept this as
    append-only and then RESTORE the stripped form — silently normalizing away an edit
    nobody asked us to touch. The comparison is verbatim, so it refuses."""
    work = seeded
    body = write_tracked(work, h.HEADER, h.item("trg-seed") + "  ", DRIFT)  # trailing spaces

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_diverged"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body, "the edited line was rewritten"


def test_a_stray_blank_line_does_not_refuse_the_repair(seeded) -> None:
    """The other side of verbatim comparison: blank lines carry no event, so a stray one
    must NOT block a legitimate repair. Comparison ignores blanks; the lines it does
    compare are exact."""
    work = seeded
    write_tracked(work, h.HEADER, h.item("trg-seed"), "", DRIFT)

    result = adopt(work)

    assert result.status == "adopted" and result.adopted == 1


def test_an_unplaceable_known_append_blocks_instead_of_eating_the_dismiss(seeded) -> None:
    """AC2, on the path that actually reaches ``decide()``. The append is KNOWN (it is in
    main's log) but unadoptable (main is behind origin — no HEAD blob to restore to), so
    it cannot be materialized. The sweep must fail CLOSED and leave the dismiss in the
    outbox — never quarantine it. A loud stop is the correct failure; data loss is not."""
    work = seeded
    h.git(work, "reset", "--hard", "HEAD~1")  # no HEAD blob → unrepairable, sweep proceeds
    write_tracked(work, h.HEADER, DRIFT)      # the append is known ONLY from main's log
    dismiss = h.status("trg-6db81c59", "dismissed")
    h.write_outbox(work, dismiss)
    wt = h.make_worktree(work, "unplaceable")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    assert result.quarantined == 0, "the operator's dismiss was quarantined"
    assert h.quarantine_text(work) == "", "the dismiss was moved to the quarantine log"
    assert dismiss in h.outbox_lines(work), "the dismiss was dropped from the outbox"


def test_append_ids_admits_only_well_formed_appends() -> None:
    """GPT O5: only a valid, unambiguous append may protect a status from the orphan
    check. Corruption, a status event, or a non-str id must contribute nothing."""
    ids = append_ids_of([
        h.HEADER,
        h.item("trg-real"),
        h.status("trg-real", "dismissed"),   # status: not an append
        '{"event":"append","id":42}',        # non-str id
        "{ BROKEN",                          # unparseable
        "",
    ])

    assert ids == frozenset({"trg-real"})
