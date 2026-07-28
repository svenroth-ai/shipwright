"""Building a project tree for the Canon C3 suites — one builder, one shape.

Three suites ask different questions of the same two artifacts, and the shapes
they write are load-bearing rather than incidental: the two high-severity defects
this iterate fixed both survived a full green suite because every fixture stamped
``at`` alone, while the producer stamped ``date`` alone. A single builder means
that shape is fixed in one place, and ``test_completion_writers.py`` drives the
REAL tools to assert this module still agrees with them.

Nothing here asserts. It writes the two artifacts C3 joins:

* ``.shipwright/agent_docs/session_handoff.md`` — the note and its canon marker
* the phase's completion record — ``phase_history`` for the seven pipeline
  phases, the file-per-run ledger for ``iterate``
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.iterate_entry import entry_file_for  # noqa: E402

RUN = "plan-20260727-1015-core"
OLDER = "plan-20260101-0900-core"

#: Iterate run ids are strict-validated (``iterate-<date>-<slug>``) and the
#: ledger reader only loads files named from one, so the iterate phase cannot
#: share the pipeline fixture's id.
ITERATE_RUN = "iterate-2026-07-27-c3-phase-history-join"

DAWN = "2026-07-27T09:00:00+00:00"
EARLY = "2026-07-27T10:00:00+00:00"
MID = "2026-07-27T11:00:00+00:00"
LATE = "2026-07-27T12:00:00+00:00"


def write_handoff(root: Path, *, phase: str, run_id: str,
                  timestamp: str = EARLY, marker: bool = True) -> Path:
    """Write the tracked handoff, with or without a canon marker."""
    docs = root / ".shipwright" / "agent_docs"
    docs.mkdir(parents=True, exist_ok=True)
    body = "# Session Handoff\n"
    if marker:
        body = (
            f'---\ncanon_generated: true\nrun_id: "{run_id}"\n'
            f'phase: "{phase}"\nreason: "phase complete"\n'
            f'timestamp: "{timestamp}"\n---\n\n' + body
        )
    path = docs / "session_handoff.md"
    path.write_text(body, encoding="utf-8")
    return path


def history_entries(*entries: tuple[str, str]) -> list[dict]:
    """Entries in the shape ``append_phase_history.py`` writes — ALL THREE keys.

    Not decoration. Twice now the shape has been the defect: the writer stamped
    ``date`` alone while every fixture stamped ``at`` alone (a dead time
    comparison through a full green suite), and then ``at`` turned out to be a
    wall clock that C3 must not compare against a marker at all. ``event_at`` is
    the anchor C3 reads; it is stamped from the same function as the marker's
    own timestamp, so a correct canon block makes the two EQUAL.

    ``at`` is stamped strictly LATER than ``event_at``, mirroring the real
    writer: the canon block records the event, writes the marker, THEN appends,
    so the wall clock always trails the anchor. Collapsing the two would make
    every suite built on this helper return the same verdict whether the code
    read the anchor or the wall clock — which is precisely how a cross-clock
    comparison could regress back in without a single test noticing.
    """
    return [
        {"run_id": run_id, "outcome": "completed", "event_at": at,
         "at": at.replace("+00:00", "") + ".900000+00:00", "date": at[:10]}
        for run_id, at in entries
    ]


def write_run_config(root: Path, history: dict | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "shipwright_run_config.json"
    path.write_text(json.dumps({"phase_history": history or {}}), encoding="utf-8")
    return path


def write_iterate_entry(
    root: Path, run_id: str, at: str, *, anchored: bool = True,
) -> Path:
    """One entry in the file-per-run ledger ``append_iterate_entry.py`` writes.

    Carries every field ``validate_iterate_entry`` requires — ``branch``
    included. The ledger's READER validates nothing, so an under-filled fixture
    reads back happily while being an entry the real writer would refuse; the
    symmetric assertion in ``test_iterate_ledger_anchor`` is what keeps this
    honest.

    ``event_at`` is the anchor C3 reads, stamped from the same function as the
    marker's own timestamp, so a correct canon block makes the two EQUAL. This
    ledger has no ``at``: ``date`` is its full-instant wall clock, and it is
    stamped strictly LATER, mirroring the real writer — F5c reads the event log
    and only then calls ``now()``. Collapsing the two would make every suite
    built on this helper return the same verdict whether the code read the
    anchor or the wall clock.

    ``anchored=False`` writes the PRE-anchor shape. Every ledger entry written
    before iterate-2026-07-28-it0-followup-anchor-prose has it, and C3 must keep
    answering those on the run id alone rather than treating a missing anchor as
    a malformed record — so the shape stays reachable on purpose.
    """
    path = entry_file_for(root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"run_id": run_id, "type": "change", "complexity": "medium",
             "branch": f"iterate/{run_id}", "tests_passed": True}
    if anchored:
        entry["event_at"] = at
        # Parsed and re-serialised rather than string-spliced: a `Z` suffix, a
        # non-UTC offset or an existing fractional second all make textual
        # surgery emit something no reader can parse (external code review R1).
        entry["date"] = (
            datetime.fromisoformat(at.replace("Z", "+00:00"))
            + timedelta(microseconds=900_000)
        ).isoformat()
    else:
        entry["date"] = at
    path.write_text(json.dumps(entry), encoding="utf-8")
    return path


def run_for(phase: str) -> str:
    return ITERATE_RUN if phase == "iterate" else RUN


def record_completions(root: Path, completions: dict[str, str]) -> None:
    """Record each phase's completion in the record that phase actually uses.

    Not one dict for all eight: ``iterate``'s completions live in the ledger, and
    a fixture that wrote them all into ``phase_history`` would assert against a
    shape production never produces — which is how ``iterate`` came to be checked
    against a bucket nothing has ever written.
    """
    write_run_config(root, {
        phase: history_entries((run_for(phase), at))
        for phase, at in completions.items() if phase != "iterate"
    })
    if "iterate" in completions:
        write_iterate_entry(root, ITERATE_RUN, completions["iterate"])
