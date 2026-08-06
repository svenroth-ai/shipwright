"""The dispositions, composed — real git, real outbox, real GC rewrite.

iterate-2026-08-06-triage-validate-deadends (trg-b854805c). The unit tests in
``test_sweep_quarantine_dispositions`` pin what ``decide`` returns. These pin the
properties that only exist once that decision meets the rest of the sweep, and
that are precisely where a withheld line would be lost:

* a HELD line survives the outbox rewrite AND is retried on the next sweep
  (``decide`` deciding to keep it is worthless if the GC then deletes it);
* a concatenated outbox line no longer stops delivery;
* an unrecoverable fragment blocks with NOTHING written anywhere.

Everything here uses REAL git, for the reason ``_sweep_helpers`` gives: the sweep
is the most data-loss-sensitive unit in the campaign, so nothing is mocked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
import triage  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402

MAIN_ONLY = "trg-main-only"
PENDING = "trg-pending"


@pytest.fixture
def repo(git_origin_repo):
    work, _origin = git_origin_repo
    h.set_identity(work)
    return work


def _commit_tracked(work: Path, *lines: str) -> None:
    """Append to main's TRACKED log and COMMIT it locally — without pushing.

    This is the shape behind finding 17: the append is a real, committed record on
    local main, but the iterate worktree branches off ``origin/main`` and cannot
    see it. The block that used to result named "deliver main (push / merge
    origin)" as the way out — unreachable here, because main is only ever
    fast-forwarded FROM origin, never pushed to it.
    """
    with (work / h.TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")
    h.git(work, "commit", "-m", "local-only triage append", "--", h.TRIAGE)


def test_held_line_survives_the_sweep_and_is_retried(repo) -> None:
    """AC4 + AC5. The absorbing state, end to end.

    The operator's dismiss refers to an append only local main has. Before this
    change the sweep returned ``invalid`` and delivered NOTHING — not the dismiss,
    and not the unrelated pending append sitting beside it in the buffer — on this
    run and on every future one. Now the pending append ships, the dismiss stays
    buffered (never quarantined), and once its append reaches origin the next
    sweep places it."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    _commit_tracked(work, h.item(MAIN_ONLY))
    h.write_outbox(work, h.status(MAIN_ONLY, "dismissed"), h.item(PENDING))
    wt = h.make_worktree(work, "hold-retry")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.held == 1, result.to_dict()
    assert result.quarantined == 0, "the operator's dismiss was quarantined"
    assert h.quarantine_text(work) == "", "a held line reached the quarantine log"
    # The unrelated append was delivered...
    assert h.item(PENDING) in h.branch_triage_lines(wt)
    # ...and the held line is still buffered, not destroyed.
    assert h.status(MAIN_ONLY, "dismissed") in h.outbox_lines(work)

    # Now main reaches origin: the append becomes visible to a fresh worktree, and
    # the second sweep places the dismiss with no operator action at all.
    h.git(work, "push", "origin", "main")
    wt2 = h.make_worktree(work, "hold-retry-2")

    second = sweep_outbox_to_branch(work, wt2, default_branch="main")

    assert second.status == "committed", second.to_dict()
    assert second.held == 0, second.to_dict()
    branch = h.branch_triage_lines(wt2)
    assert h.status(MAIN_ONLY, "dismissed") in branch
    resolved = {i["id"]: i["status"] for i in triage.read_all_items(wt2)}
    assert resolved[MAIN_ONLY] == "dismissed"


def test_a_dismiss_survives_when_its_append_is_glued_on_local_main(repo) -> None:
    """AC14 — the two defects COMPOSED, which is where the worst outcome lived.

    ``append_ids_of`` builds the PROTECTION universe: an id present there stops a
    ``status`` being read as an orphan and quarantined away. It parsed one
    ``json.loads`` per physical line, so an append committed on local main inside a
    line glued by an unterminated write vanished from that universe — and the
    operator's dismiss for it became an unprotected orphan, was DESTROYED, and the
    item resurrected once main reached origin. A glued line (finding 15) times an
    append only local main has (finding 17); the validator recovering such a line
    while this did not is exactly the disagreement this run exists to remove.

    Found by the Stage-2 code review, not by the plan."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    # Two appends committed on local main, sharing ONE physical line.
    with (work / h.TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(h.item(MAIN_ONLY) + h.item("trg-glued-sibling") + "\n")
    h.git(work, "commit", "-m", "local-only glued appends", "--", h.TRIAGE)
    h.write_outbox(work, h.status(MAIN_ONLY, "dismissed"))
    wt = h.make_worktree(work, "glued-protection")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.quarantined == 0, "the operator's dismiss was quarantined away"
    assert h.quarantine_text(work) == "", "the dismiss reached the quarantine log"
    assert result.held == 1, result.to_dict()
    assert h.status(MAIN_ONLY, "dismissed") in h.outbox_lines(work), "the dismiss was dropped"


def test_concatenated_outbox_line_no_longer_blocks_delivery(repo) -> None:
    """AC1. Finding 15 end to end: one unterminated write glues two records onto a
    physical line. The reader recovered it, so the board showed the items applied —
    while the validator called it corruption and delivery had silently stopped."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    outbox = work / h.OUTBOX
    outbox.parent.mkdir(parents=True, exist_ok=True)
    # No trailing newline on the first write → the next append shares the line.
    outbox.write_text(h.item("trg-first"), encoding="utf-8", newline="\n")
    h.write_outbox(work, h.item("trg-second"))
    assert len([ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln]) == 1
    wt = h.make_worktree(work, "glued-delivery")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    resolved = {i["id"] for i in triage.read_all_items(wt)}
    assert {"trg-first", "trg-second"} <= resolved, "a recovered record never reached the branch"


def test_unrecoverable_fragment_blocks_with_no_side_effects(repo) -> None:
    """AC12. Valid records followed by real corruption: the sweep must stop BEFORE
    touching anything, so a corruption event can never half-apply a destructive
    action (external plan review, r2 openai #4)."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    h.write_outbox(work, h.item(PENDING), '{"event":"append" BROKEN')
    wt = h.make_worktree(work, "fragment-block")
    outbox_before = (work / h.OUTBOX).read_bytes()

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    assert any("triage_repair.py" in e for e in result.errors), result.errors
    assert (work / h.OUTBOX).read_bytes() == outbox_before, "the outbox was rewritten"
    assert h.quarantine_text(work) == "", "a quarantine was appended on a blocked sweep"
    assert h.item(PENDING) not in h.branch_triage_lines(wt), "a blocked sweep committed"


def test_unidentified_status_is_quarantined_and_the_rest_ships(repo) -> None:
    """AC6. Finding 18 end to end. The line names no item, so no reader can apply
    it and no id-keyed remedy could select it — it simply stopped the sweep. It is
    inert, so quarantining it preserves it for review and costs nothing."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    no_id = '{"event":"status","ts":"2026-06-08T00:00:01Z","newStatus":"dismissed"}'
    h.write_outbox(work, no_id, h.item(PENDING))
    wt = h.make_worktree(work, "unidentified")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.quarantined == 1, result.to_dict()
    # The quarantine log wraps each line as ``{"quarantined_at":…,"original":<line>}``,
    # so read the field rather than substring-matching the escaped form.
    preserved = [
        json.loads(ln)["original"]
        for ln in h.quarantine_text(work).splitlines() if ln.strip()
    ]
    assert preserved == [no_id], "the line was dropped instead of preserved"
    assert h.item(PENDING) in h.branch_triage_lines(wt)
    assert no_id not in h.outbox_lines(work), "the quarantined line stayed in the outbox"
