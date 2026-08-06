"""The outbox sweep's result + the notes it owes the operator.

Split from :mod:`lib.sweep_outbox` (iterate-2026-07-14-sweep-drift-dismiss-loss) so the
orchestrator stays under the 300-LOC guideline and the reporting rule — what a human is
told about a sweep — is one testable unit.

That rule is not cosmetic. A quarantine used to look EXACTLY like a clean run:
``SweepResult.quarantined`` was returned and nothing ever printed it, so the sweep
destroyed an operator's dismiss and reported success. Silence is how the data loss stayed
invisible for as long as it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lib.sweep_quarantine import QUARANTINE_LOG


@dataclass
class SweepResult:
    """Outcome of :func:`lib.sweep_outbox.sweep_outbox_to_branch`.

    ``status`` ∈ {``committed``, ``no_change``, ``skipped``, ``invalid``, ``error``}.
    ``reason`` carries the guard name for ``skipped`` / ``error`` (and any adoption note);
    ``swept`` is the count of genuinely-new (deduped) lines folded into the branch on a
    ``committed`` run; ``gc_dropped`` is the count of outbox lines dropped because they are
    already origin-delivered; ``quarantined`` is the count of orphan-status lines moved to
    the quarantine log this run; ``held`` is the count of lines withheld from THIS delivery
    and left in the outbox for the next sweep (see :func:`lib.sweep_quarantine.decide`);
    ``adopted`` is the count of undelivered main-tree TRACKED drift appends routed into the
    outbox this run (see :mod:`lib.sweep_drift`); ``errors`` holds validator messages for
    ``invalid``; ``dedup_notes`` holds whatever :mod:`lib.triage_dedup` reported while
    materializing the log — a same-id ``append`` collapsed keep-last, or a probable 32-bit
    id collision it refused to collapse.
    """

    status: str
    reason: str = ""
    swept: int = 0
    gc_dropped: int = 0
    quarantined: int = 0
    adopted: int = 0
    commit_subject: str = ""
    errors: list[str] = field(default_factory=list)
    dedup_notes: list[str] = field(default_factory=list)
    held: int = 0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "swept": self.swept,
            "gc_dropped": self.gc_dropped,
            "quarantined": self.quarantined,
            "held": self.held,
            "adopted": self.adopted,
            "commit_subject": self.commit_subject,
            "errors": self.errors,
            "dedup_notes": self.dedup_notes,
        }


def with_adopt_note(adopt_note: str, reason: str) -> str:
    """``reason``, carrying any adoption note along.

    Lives here rather than in the orchestrator because it is the same rule this module
    exists for: what a human is told. A ``main_tracked_salvage_*`` note can name the
    ONLY surviving copy of salvaged lines, and every post-adoption error return in the
    sweep used to overwrite it with its own message (code review).
    """
    return f"{reason} (adoption: {adopt_note})" if adopt_note else reason


def sweep_warnings(result: SweepResult) -> list[str]:
    """Operator-facing notes for a sweep — the ONLY thing that reaches a human.

    COUNTS ONLY, never the line payloads: those carry operator-entered prose (external
    review). A quarantine is reported even on an otherwise-successful run, because that is
    precisely the case that used to pass in silence.
    """
    notes: list[str] = []
    if result.status in ("invalid", "error", "skipped"):
        notes.append(f"sweep-outbox {result.status}: {result.errors or result.reason}")
    elif result.reason.startswith("main_tracked_"):
        # A successful sweep that could not finish the main-tree repair. MOST of these are
        # self-healing (HEAD moved mid-restore → the drift is buffered and the next sweep
        # completes it) and the operator merely hears about it instead of reading
        # "committed". But the `main_tracked_salvage_*` reasons are NOT that class: there
        # the content survives only in a gitignored salvage file that no replay collects,
        # so the reason itself says "do not delete it" / "review before deleting". Do not
        # read this whole branch as benign.
        notes.append(f"sweep-outbox {result.reason}")
    if result.quarantined:
        notes.append(
            f"sweep-outbox QUARANTINED {result.quarantined} orphan-status line(s) — an operator "
            f"action was withheld; review {QUARANTINE_LOG}"
        )
    if result.held:
        # Reported on EVERY status, deliberately outside the branches above. A held line
        # whose append never reaches origin stays buffered indefinitely, and a sweep with
        # nothing else to do is exactly the run nobody would look at.
        notes.append(
            f"sweep-outbox HELD {result.held} line(s) in the outbox — their append is not yet "
            f"reachable from this branch; the next sweep retries them"
        )
    if result.adopted:
        notes.append(
            f"sweep-outbox adopted {result.adopted} undelivered main-tree drift append(s) "
            f"into the outbox — they ride this PR to origin"
        )
    # Dedup notes carry ids and counts only, never a title or a reason, so they honour
    # the COUNTS-ONLY rule above. They are reported on a SUCCESSFUL sweep too: a keep-last
    # collapse is benign and must not block, but the path that can drop a record is
    # exactly the one that must not be silent (audit 2026-07-28, finding 25).
    notes.extend(f"sweep-outbox dedup: {note}" for note in result.dedup_notes)
    return notes
