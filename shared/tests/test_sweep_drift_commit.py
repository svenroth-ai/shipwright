"""The MUTATING half of the drift repair: what it writes, and what it must not.

Split from ``test_sweep_drift_guards.py`` (the read-only refusal guards) so each module
stays under the 300-LOC guideline. These four pin the states the code review found
untested — and three of them were real defects:

* a CRLF drift line over an LF checkout reflowed the ENTIRE tracked log (the restore
  guessed the EOL from the working file instead of letting git reproduce HEAD's bytes);
* a ``block`` used to arrive AFTER the mutation, leaving the operator's data in a
  GITIGNORED buffer while main's ``git status`` read clean — one ``git clean -x`` from gone;
* a race during the restore reported ``adopted=0`` while N lines were in fact buffered.
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
from lib import sweep_drift  # noqa: E402
from lib.sweep_drift import commit_main_tracked_drift, plan_main_tracked_drift  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from lib.sweep_text import read_text_verbatim  # noqa: E402

DRIFT = h.item("trg-6db81c59")


def outbox(work: Path) -> Path:
    return work / h.OUTBOX


def write_tracked(work: Path, *lines: str) -> str:
    body = "\n".join(lines) + "\n"
    (work / h.TRIAGE).write_text(body, encoding="utf-8", newline="")
    return body


def adopt(work: Path):
    """Plan + commit — the sweep's two-phase adoption, as the sweep runs it."""
    plan = plan_main_tracked_drift(work, outbox(work))
    if plan.status != "adoptable":
        return plan
    return commit_main_tracked_drift(plan, work, outbox(work))


@pytest.fixture
def seeded(git_origin_repo):
    """A main tree whose tracked triage log holds one committed item."""
    work, _origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked(work, h.item("trg-seed"))
    return work


def test_replaying_an_interrupted_adoption_does_not_double_deliver(seeded) -> None:
    """Gemini G2 / GPT O2. The outbox write is durable and lands FIRST; the restore is
    second. A crash between them leaves the drift in both places. The replay must
    recognise the buffered line and add nothing — else every interruption duplicates
    an append."""
    work = seeded
    write_tracked(work, h.HEADER, h.item("trg-seed"), DRIFT)

    first = adopt(work)
    assert first.status == "adopted" and first.adopted == 1
    # Simulate the crash: the outbox write survived, the restore never happened.
    write_tracked(work, h.HEADER, h.item("trg-seed"), DRIFT)

    replay = adopt(work)

    assert replay.status == "adopted"
    lines = [ln for ln in outbox(work).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines == [DRIFT], f"the drift append was buffered twice: {lines}"


def test_a_crlf_drift_line_over_an_lf_checkout_does_not_reflow_the_whole_log(seeded) -> None:
    """Code review (high). ``triage._append_line`` writes with ``newline=None`` → CRLF on
    Windows. Reconstructing the restore by hand meant guessing the EOL from the working
    file, so ONE CRLF drift line over an LF checkout rewrote the ENTIRE log as CRLF —
    trading the drift for a whole-file diff the operator would then commit into a
    merge=union log. The restore is ``git checkout --``, so git reproduces HEAD's bytes."""
    work = seeded
    h.git(work, "config", "core.autocrlf", "false")
    with (work / h.TRIAGE).open("a", encoding="utf-8", newline="") as fh:
        fh.write(DRIFT + "\r\n")  # a Windows producer's line into an LF-checked-out log

    result = adopt(work)

    assert result.status == "adopted", result
    restored = (work / h.TRIAGE).read_bytes()
    assert b"\r\n" not in restored, "the LF log was reflowed to CRLF"
    assert not h.git(work, "status", "--porcelain", "--", h.TRIAGE).stdout.strip(), \
        "the restore left main's tracked log dirty"


def test_a_block_mutates_nothing_even_when_drift_is_adoptable(seeded) -> None:
    """Code review (high). Adoption used to run BEFORE ``decide()``. On a block, the drift
    had already left the git-tracked log for the GITIGNORED outbox: main's `git status`
    went clean while the only copy of the operator's data sat in a file ``git clean -x``
    deletes. Plan first, decide, and only then mutate — a block must leave both files
    exactly as they were."""
    work = seeded
    body = write_tracked(work, h.HEADER, h.item("trg-seed"), DRIFT)  # adoptable drift
    # ...plus genuine corruption in the outbox (the non-orphan class: unparseable JSON),
    # which fails the materialized log closed no matter what the repair does.
    h.write_outbox(work, '{"event":"status","id":"trg-x" BROKEN')
    wt = h.make_worktree(work, "block-no-mutation")
    before_outbox = read_text_verbatim(outbox(work))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    assert read_text_verbatim(work / h.TRIAGE) == body, "the drift left the tracked log on a block"
    assert read_text_verbatim(outbox(work)) == before_outbox, "the outbox was mutated on a block"


def test_a_race_during_the_restore_reports_buffered_not_adopted(seeded, monkeypatch) -> None:
    """Code review (medium). A process lock cannot stop an external ``git commit`` or an
    editor. If HEAD moves between the durable outbox write and the restore, the restore is
    abandoned — no loss (the replay completes it), but the operator must be TOLD that,
    not handed a silent ``adopted`` with a count of zero."""
    work = seeded
    write_tracked(work, h.HEADER, h.item("trg-seed"), DRIFT)
    plan = plan_main_tracked_drift(work, outbox(work))
    assert plan.status == "adoptable"
    monkeypatch.setattr(sweep_drift, "_head_oid", lambda _root: "0" * 40)  # HEAD moved under us

    done = commit_main_tracked_drift(plan, work, outbox(work))

    assert done.status == "buffered", done
    assert done.adopted == 1, "the operator was told nothing was adopted"
    assert done.reason.startswith("main_tracked_changed_during_adopt"), done.reason
    assert DRIFT in h.outbox_lines(work), "the drift was not buffered"
    assert DRIFT in read_text_verbatim(work / h.TRIAGE), "the tracked log was restored anyway"
