"""What a BLOCKED sweep tells the operator.

iterate-2026-08-06-triage-validate-deadends (trg-b854805c). Its sibling
``test_sweep_quarantine_dispositions`` pins WHICH disposition a line gets; this
module pins what the remaining ``block`` says, because a block whose remedy is
absent, unreachable or simply false is the defect this whole run is about. Three
paths used to end there with no way out, and one of them printed a remedy
("deliver main by push / merge") that this workflow cannot perform at all.

So the rule these tests enforce is not "block less". It is: block only on
corruption the sweep must not paper over, and when you do, say something TRUE
about it and name the tool that fixes it whenever one exists.

Split out so both modules stay under the 300-LOC guideline.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.sweep_quarantine import decide  # noqa: E402

MAIN_ONLY = "trg-in-main"        # its append lives in main's TRACKED log
GHOST = "trg-ghost"              # its append exists nowhere
PENDING = "trg-pending"          # an ordinary, perfectly deliverable append
KNOWN = frozenset({MAIN_ONLY})


def _tracked() -> list[str]:
    return [h.HEADER, h.item("trg-other")]


# --- block: what must still fail closed --------------------------------------


def test_tracked_side_defect_still_blocks() -> None:
    """AC9. The sweep cannot rewrite the worktree-tracked log, so a defect that
    lives only there is an honest hard stop — never a silent delivery."""
    orphan = h.status(GHOST, "dismissed")

    d = decide(_tracked() + [orphan], [h.item(PENDING)], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d


def test_defect_in_both_sources_still_blocks() -> None:
    """AC9. Provenance is enforced by the residual re-validation, not by the
    partition: the outbox copy is dispositioned, the byte-identical tracked copy
    survives the trim, so the re-materialized text still fails (external plan
    review r2, openai #3)."""
    orphan = h.status(GHOST, "dismissed")

    d = decide(_tracked() + [orphan], [orphan], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d


def test_unrecoverable_fragment_blocks_before_any_disposition() -> None:
    """AC12. Genuine corruption is decided BEFORE the partition runs, so no
    quarantine list is built and no side effect can be half-applied."""
    d = decide(_tracked(), ['{"event":"status" BROKEN'], "\n", known_append_ids=KNOWN)

    assert d.action == "block"
    assert d.candidates == [] and d.held_lines == []
    assert any("triage_repair.py" in e for e in d.errors), d.errors


def test_a_held_id_is_never_described_as_absent_from_the_outbox() -> None:
    """Stage-2 code review finding 2, and the over-correction it provoked.

    ``_block_errors`` first received the whole ``protected`` set, so a block told the
    operator that a status sitting in the outbox and successfully HELD "is not in the
    outbox, so it cannot be held". Suppressing the note for held ids fixed that and
    broke something worse: the block then carried ONLY the validator's "has no append
    anywhere — the merge dropped it", which is actively false (the append is on local
    main) and sends the operator hunting for corruption that does not exist.

    Both halves are asserted: the explanation is always present, and its wording
    matches which case actually occurred."""
    dismiss = h.status(MAIN_ONLY, "dismissed")

    # A copy of the same dismiss is already in the branch's tracked log, so trimming
    # the outbox copy still leaves the orphan → block, with the outbox copy held.
    d = decide(_tracked() + [dismiss], [dismiss], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    note = next((e for e in d.errors if "protected_status_unplaceable" in e), None)
    assert note is not None, d.errors
    assert "withheld its outbox copy" in note, note
    assert "not in the outbox" not in note, note


def test_a_protected_id_outside_the_outbox_still_gets_the_correction() -> None:
    """Here the protected status exists ONLY in the tracked log. The note must still
    correct the validator's "no append anywhere", but must NOT claim to know where
    the status sits — an earlier draft said "it is not in the outbox", which is false
    the moment the line is present-but-glued (Stage-3 objection 2)."""
    dismiss = h.status(MAIN_ONLY, "dismissed")

    d = decide(_tracked() + [dismiss], [], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    note = next((e for e in d.errors if "protected_status_unplaceable" in e), None)
    assert note is not None, d.errors
    assert "is wrong about it" in note, note
    assert "not in the outbox" not in note, note


def test_a_glued_protected_status_is_not_called_absent() -> None:
    """Stage-3 objection 2. The protected dismiss IS in the outbox, glued to another
    record, so it was never a candidate for holding — the old wording called it
    absent, contradicting the `unsplittable_outbox_line` message printed alongside."""
    glued = h.status(MAIN_ONLY, "dismissed") + h.item(PENDING)

    d = decide(_tracked(), [glued], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    assert not any("not in the outbox" in e for e in d.errors), d.errors
    assert any("triage_repair.py" in e for e in d.errors), d.errors


def test_corruption_elsewhere_does_not_swallow_the_protected_correction() -> None:
    """Stage-3 objection 1 — the highest-value objection of the review.

    ``protected`` used to be computed AFTER the corruption early-return, so that
    return passed an empty set and the note was silently dropped. Any corruption
    ANYWHERE in the log co-occurring with a legitimately protected dismiss ELSEWHERE
    therefore reached the operator as the raw "has no append anywhere — the merge
    dropped it": false, and pointing at corruption that does not exist. That is the
    exact defect class this run exists to remove, reborn on another path."""
    dismiss = h.status(MAIN_ONLY, "dismissed")

    d = decide(_tracked(), ["123", dismiss], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    assert any("protected_status_unplaceable" in e for e in d.errors), d.errors
    # ...and the corruption's own remedy is still named.
    assert any("triage_repair.py" in e for e in d.errors), d.errors


def test_a_held_status_does_not_make_a_glued_amend_look_held_too() -> None:
    """Stage-3 doubt review, finding 6. `MAIN_ONLY`'s `status` is a clean, sole-record
    outbox line, so it IS held; its `amend` copy is glued to another record, so it was
    NEVER a hold candidate (it goes straight to `materialized` via the ``obj is None``
    branch). Before the fix, one merged ``held_ids`` set made the amend note claim
    "this run withheld its outbox copy" too — false, and the exact wrong-kind
    misattribution `protected_note` exists to prevent."""
    dismiss = h.status(MAIN_ONLY, "dismissed")
    glued_amend = h.amend(MAIN_ONLY, "corrected") + h.item(PENDING)

    d = decide(_tracked(), [dismiss, glued_amend], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    status_note = next((e for e in d.errors if "protected_status_unplaceable" in e), None)
    amend_note = next((e for e in d.errors if "protected_amend_unplaceable" in e), None)
    assert status_note is not None and "withheld its outbox copy" in status_note, d.errors
    assert amend_note is not None and "withheld its outbox copy" not in amend_note, d.errors


def test_duplicate_append_in_a_glued_line_names_the_repair_tool() -> None:
    """Stage-2 code review, finding 3. This takes the EARLY corruption return, where
    the concatenation scan used to be unreachable. The operator was told "the merge
    double-counted an item" and went hunting for a duplicate LINE that does not
    exist, while `triage_repair.py` — which splits exactly that line — was one
    command away."""
    dup = h.item(PENDING)
    glued = dup + dup.replace('"x"', '"y"')

    d = decide(_tracked(), [glued], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    assert any("duplicate append" in e for e in d.errors), d.errors
    assert any("triage_repair.py" in e for e in d.errors), d.errors


def test_glued_line_needing_disposition_blocks_with_repair_hint() -> None:
    """AC11. The outbox is persisted, quarantined and GC'd BY PHYSICAL LINE, so a
    glued line holding a deliverable record plus one needing quarantine cannot be
    dispositioned per record — and re-serializing it inside the sweep would
    reflow EOLs and break the byte-identity dedup. It blocks, and the block is
    escapable: the message names the tool whose whole purpose is splitting such
    lines on disk."""
    glued = h.item(PENDING) + h.status(GHOST, "dismissed")

    d = decide(_tracked(), [glued], "\n", known_append_ids=KNOWN)

    assert d.action == "block", d
    assert any("triage_repair.py" in e for e in d.errors), d.errors
