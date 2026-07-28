"""Canon **C3** — did THIS phase leave the handover note?

The check takes NO run id. It joins the handoff's canon marker against the
phase's own completion record (``lib.phase_history``), both read from disk.

**Why no run id.** iterate-2026-07-27-c3-phase-content-key keyed C3 on a run id
supplied by the caller, and inherited every way its two production callers
disagree about what that id is: ``phase_quality.resolve_run_id`` walks
run-config → ``run_started`` event → loop vars → **session UUID**, while
``phase_validators._run_canon_checks`` reads ``SHIPWRIGHT_RUN_ID`` from a
subprocess that never inherits the skill's shell export. Neither yields the id
the writer stamped, so C3 warned on every phase of every Stop. A check that
never consults the caller's run id cannot be broken by the caller resolving it.

**Why the completion record.** It is the accumulating per-phase artifact
C1/C2/C4/C5 already rely on. The predecessor asserted no per-phase record
existed — true of the handoff, false of the run config, whose own pre-#467
docstring pointed at ``phase_history`` verbatim.

**Why time decides ownership, not pipeline order.** When the note names a
different phase, a static order cannot separate "a later phase legitimately
superseded this one" from "a stale later-phase note plus a re-run of this phase
that wrote nothing" — the second reads as supersession and hides exactly the
skipped step this check exists to catch (external plan review, openai R1).

**Why the run id alone is not enough when the note DOES name this phase.**
``build`` appends one completion per split under a sticky run id
(``: "${SHIPWRIGHT_RUN_ID:=…}"``), and ``iterate``'s F5c rewrites its single
ledger entry in place. A bare id match calls both a pass — the predecessor's
defect in a new costume. So where the completion carries an event anchor, the
note must also not predate it.

**The marker's ``timestamp`` is not a write time.** ``generate_session_handoff``
stamps ``latest_event_dt`` — the newest ts in ``shipwright_events.jsonl`` —
because wall clock there re-dirtied the tracked handoff on every regeneration.
So a completion compared against it must be read on the same clock, which is what
``event_at`` is for. Comparing it against the completion's wall-clock ``at``
accused a phase of skipping its C3 step on every re-run where ``record_event``'s
dedup meant no fresh event landed — in the true positive's own words, with a
remedy that could not clear it.

**And when ANOTHER phase owns the note, the anchor cannot decide either.** The
same dedup means a phase completing a second time inherits whatever anchor was
newest — routinely the owner's. Ordered by that, the two read as simultaneous and
the phase that ran LATER was reported as superseded by the EARLIER one: a silent
SKIP. So that branch orders the two phases against EACH OTHER on wall clock,
sound because one producer calling ``datetime.now()`` writes both.

**Known bounds.**

* A completion that records no new event AND does not re-write the marker leaves
  its anchor equal to the note's, and the same-phase branch reads that as a pass.
* A completion recorded before its producer stamped ``event_at`` carries no
  anchor, so the clock is not consulted for it and the run id answers alone.
* Cross-phase, the owner's completion is looked up by the run the NOTE names. If
  the owner recorded SEVERAL completions under that one run id, the last is used
  and a note written at an earlier one reads as newer than it is.

Any comparison the record cannot settle is stated, never inferred.

Severity stays WARNING — the handoff is advisory, not load-bearing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.phase_history import (  # noqa: E402
    COMPLETION_PRODUCER,
    PhaseCompletion,
    RecordedTime,
    latest_completion,
    recorded_time,
)

from .common import CheckResult  # noqa: E402
from .handoff_marker import clip, read_handoff, skip, warn  # noqa: E402

NAME = "C3 session_handoff.md fresh"

#: Phases whose finalization writes the canon marker, so C3 has a producer to
#: verify. Seven pipeline phases call ``generate_session_handoff.py
#: --canon-marker --phase <phase>``; ``iterate`` supplies the same block from
#: ``tools/finalize_iterate.py``. ``security`` / ``compliance`` / ``adopt`` write
#: no marker and are skipped BY NAME — the Stop-hook canon runner invokes C3 for
#: every phase in ``PLUGIN_TO_PHASE``, so without this set a content key would
#: turn a schedule-driven false fire into a permanent one. Kept aligned with
#: ``PLUGIN_TO_PHASE`` by ``test_c3_canon_phases_align_with_plugin_to_phase``,
#: and with the completion producers by
#: ``test_every_c3_phase_has_a_completion_producer``.
C3_CANON_PHASES: frozenset[str] = frozenset({
    "project", "design", "plan", "build", "test", "changelog", "deploy", "iterate",
})


def _producer(phase: str) -> str:
    """The tool that records a completion for ``phase``, for remediation text."""
    return COMPLETION_PRODUCER.get(phase, "the phase's completion producer")


def _predates_its_own_completion(
    completion: PhaseCompletion, written: RecordedTime | None,
) -> bool | None:
    """Is the note's anchor older than this phase's own latest completion anchor?

    Same phase, same canon block, so both sides are event anchors and equality
    means "this block wrote it" — hence the STRICT ``after``. ``None`` when
    either side is unusable, or when the note's own timestamp pins only a DAY:
    reading that as midnight is the fabrication HIGH-1 removed everywhere else,
    and the marker was the one place it would have survived. Producers only ever
    stamp an instant, so the coarse branch guards a hand-edited marker.
    """
    if written is None or completion.anchor is None:
        return None
    if written.earliest != written.latest:
        return None
    return completion.anchor.after(written.earliest)


def _same_phase_verdict(
    phase: str,
    marked_run: str,
    written: RecordedTime | None,
    completion: PhaseCompletion,
) -> CheckResult:
    """The note names this phase — is it from this phase's LATEST completion?"""
    if not marked_run:
        return warn(NAME, "canon marker carries no run id")
    if marked_run != completion.run_id:
        if marked_run in completion.known_run_ids:
            return warn(
                NAME,
                f"the note is from an earlier {clip(phase)} run ({clip(marked_run)}); "
                f"the latest is {clip(completion.run_id)} — re-run this phase's C3 step",
            )
        return warn(
            NAME,
            f"the note names {clip(phase)} run {clip(marked_run)}, which the "
            f"{clip(phase)} completion record does not hold — note and record disagree",
        )

    passed = CheckResult(
        NAME, True, f"written by {clip(phase)} for its latest run {clip(marked_run)}",
    )
    # The id alone cannot say WHICH completion the note belongs to when a run
    # records more than one — `build` appends one per split under the sticky
    # `: "${SHIPWRIGHT_RUN_ID:=…}"` id, and `iterate`'s F5c can rewrite its
    # single ledger entry. So the anchors decide. Gated on the anchor EXISTING,
    # not on a count of entries: a count of one is not evidence a phase completed
    # once (the iterate ledger is one file per run id, so its count is pinned at
    # one forever), while a missing anchor really does mean the two sides sit on
    # different clocks and must not be compared.
    #
    # An entry that CLAIMS an anchor and cannot be read is a third state, and it
    # must not take the run-id fallback: that would disable the stale-note check
    # on precisely the malformed record least deserving of the benefit of doubt.
    if completion.anchor is None:
        if completion.claims_anchor:
            return warn(
                NAME,
                f"the note names {clip(phase)}'s latest run, but that completion's "
                "recorded event time cannot be read — cannot tell whether the note "
                "was written for it",
            )
        return passed

    stale = _predates_its_own_completion(completion, written)
    if stale is None:
        return warn(
            NAME,
            f"the note names {clip(phase)}'s latest run but carries no usable "
            "timestamp — cannot tell whether it was written for that completion",
        )
    if stale:
        return warn(
            NAME,
            f"the note names {clip(phase)}'s latest run but predates that run's "
            f"last recorded completion — a later {clip(phase)} step completed "
            "without re-writing it; re-run its C3 step",
        )
    return passed


def _other_phase_verdict(
    phase: str,
    owner: str,
    completion: PhaseCompletion,
    owner_completion: PhaseCompletion | None,
) -> CheckResult:
    """A different phase owns the note — which of the two acted last?

    The two phases are ordered against EACH OTHER on wall clock, not against the
    marker. The marker's timestamp is an event anchor, and ``record_event``
    dedups ``phase_completed`` permanently, so a phase completing a second time
    inherits the newest anchor on disk — routinely the owner's. Ordered by that,
    the two read as simultaneous, and a phase that ran later and wrote nothing
    was reported as legitimately superseded: defect 1, in the one branch the
    first fix did not touch. Both completions come from one producer calling
    ``datetime.now()``, so their wall clocks ARE mutually comparable.
    """
    if owner_completion is None or owner_completion.wall is None or completion.wall is None:
        missing = (
            "no completion is recorded for it under the run the note names"
            if owner_completion is None else "one of the two has no usable time"
        )
        return warn(
            NAME,
            f"the note was written by {owner}, and {missing} — cannot tell "
            f"whether {clip(phase)} ran after it",
        )
    ran_after = completion.wall.later_than(owner_completion.wall)
    if ran_after is None:
        return warn(
            NAME,
            f"{clip(phase)} and {owner}, which wrote the note, cannot be ordered "
            "against each other — cannot tell which completed last",
        )
    if ran_after:
        return warn(
            NAME,
            f"{clip(phase)} completed after the handover note was written by "
            f"{owner}, so it left no note of its own — re-run its C3 step",
        )
    return skip(
        NAME,
        f"superseded: {owner} wrote the note after {clip(phase)} completed, so "
        f"{clip(phase)}'s own note is no longer on disk to check",
    )


def check_c3_session_handoff_fresh_after_phase(
    project_root: Path,
    phase: str,
) -> CheckResult:
    """C3 — pass iff ``phase`` itself wrote the handover note for its latest run."""
    if phase not in C3_CANON_PHASES:
        return skip(
            NAME,
            f"not applicable for phase={clip(phase)} (writes no canon-marker handoff)",
        )

    handoff = read_handoff(Path(project_root))
    if handoff.problem:
        return warn(NAME, handoff.problem)
    if handoff.marker is None:
        return warn(
            NAME,
            "session_handoff.md has no canon marker — re-run the phase's C3 step "
            f"(generate_session_handoff.py --canon-marker --phase {clip(phase)})",
        )

    completion = latest_completion(Path(project_root), phase)
    if completion is None:
        return warn(
            NAME,
            f"no completion recorded for {clip(phase)} — nothing to check the "
            f"handover note against. Expected if {clip(phase)} has never run in "
            f"this project; otherwise run {_producer(phase)}",
        )

    written = recorded_time(handoff.marker.get("timestamp", ""))
    marked_phase = handoff.marker.get("phase", "")
    if marked_phase == phase:
        return _same_phase_verdict(
            phase, handoff.marker.get("run_id", ""), written, completion,
        )

    # A different phase owns the note. Whoever acted LAST decides whether this is
    # legitimate supersession or a phase that skipped its step — so the OWNER's
    # completion is loaded too, and the two phases are ordered against each other
    # rather than against the note's anchor.
    #
    # Narrowed to the owner's completion for the run the NOTE names, not its
    # latest: those differ exactly when the owner completed again without
    # re-writing the note, and `finalize_bundle` reaches that on its own
    # (F5c writes the ledger, then F5b can `_abort`). Using the latest then reads
    # a phase that skipped its step as legitimately superseded — a silent SKIP,
    # the direction this check exists to close.
    owner_completion = (
        latest_completion(
            Path(project_root), marked_phase, run_id=handoff.marker.get("run_id", ""),
        )
        if marked_phase else None
    )
    return _other_phase_verdict(
        phase, clip(marked_phase) or "(unnamed)", completion, owner_completion,
    )


__all__ = [
    "C3_CANON_PHASES",
    "NAME",
    "check_c3_session_handoff_fresh_after_phase",
]
