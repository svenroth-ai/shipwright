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
    the quarantine log this run; ``adopted`` is the count of undelivered main-tree TRACKED
    drift appends routed into the outbox this run (see :mod:`lib.sweep_drift`); ``errors``
    holds validator messages for ``invalid``.
    """

    status: str
    reason: str = ""
    swept: int = 0
    gc_dropped: int = 0
    quarantined: int = 0
    adopted: int = 0
    commit_subject: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "swept": self.swept,
            "gc_dropped": self.gc_dropped,
            "quarantined": self.quarantined,
            "adopted": self.adopted,
            "commit_subject": self.commit_subject,
            "errors": self.errors,
        }


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
        # A successful sweep that could not finish the main-tree repair (e.g. HEAD moved
        # mid-restore). No loss — the drift is buffered and the next sweep completes it —
        # but the operator hears about it rather than reading "committed" and assuming all is well.
        notes.append(f"sweep-outbox {result.reason}")
    if result.quarantined:
        notes.append(
            f"sweep-outbox QUARANTINED {result.quarantined} orphan-status line(s) — an operator "
            f"action was withheld; review {QUARANTINE_LOG}"
        )
    if result.adopted:
        notes.append(
            f"sweep-outbox adopted {result.adopted} undelivered main-tree drift append(s) "
            f"into the outbox — they ride this PR to origin"
        )
    return notes
