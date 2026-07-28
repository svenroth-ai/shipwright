"""The real completion writers, run as the pipeline runs them.

This suite exists because of how the two high-severity defects in this iterate
survived: every fixture stamped ``at``, ``append_phase_history.py`` stamped
``date``, and 5856 shared tests were green while Canon C3's time comparison was
dead in production. A fixture asserts against a shape someone believed; only the
writer asserts against the shape that ships.

So: no hand-built dicts here. Each test invokes the actual tool as a subprocess,
then reads the artifact back through ``lib.phase_history`` and, where it matters,
runs Canon C3 against the result. What ``_c3_fixtures`` writes elsewhere is
pinned to these by ``test_the_hand_built_shape_matches_the_writer``; the
producer registry itself is guarded in ``test_c3_applicability.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from _c3_fixtures import ITERATE_RUN, history_entries, write_handoff  # noqa: E402
from lib.canon_frontmatter import parse_canon_frontmatter  # noqa: E402
from lib.phase_history import latest_completion  # noqa: E402
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

TOOLS = REPO_ROOT / "shared" / "scripts" / "tools"
RUN = "build-2026-07-27-splits"


def _run(tool: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke a producer exactly as a phase skill does."""
    result = subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        capture_output=True, text=True, timeout=120, env=env,
    )
    assert result.returncode == 0, f"{tool} failed: {result.stderr}"
    return result


def _project(root: Path) -> Path:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {}}), encoding="utf-8"
    )
    return root


def append_completion(root: Path, phase: str, run_id: str) -> dict:
    _run("append_phase_history.py", "--project-root", str(root),
         "--phase", phase, "--run-id", run_id)
    config = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))
    return config["phase_history"][phase][-1]


# --- append_phase_history stamps an instant, not just a day -------------------

def test_the_writer_stamps_a_full_instant(tmp_path):
    """HIGH-1 at its source. `date` alone cannot order anything inside a day,
    and the marker it is compared against is always an intra-day instant."""
    entry = append_completion(_project(tmp_path), "build", RUN)

    assert "T" in entry["at"], f"`at` must be an instant, got {entry['at']!r}"
    assert entry["date"] == entry["at"][:10], "the two keys must name one moment"


def test_the_written_entry_reads_back_as_an_instant(tmp_path):
    """End to end: what the writer emits must be usable by what C3 reads.

    Driven through the whole canon block, because the anchor only exists when an
    event does — `append_phase_history` alone yields a wall clock and no anchor,
    which is a real (and correct) state, just not the one this asserts."""
    root = _project(tmp_path)
    canon_block(root, "build", RUN, "split 1")

    completion = latest_completion(root, "build")

    assert completion is not None
    for label, moment in (("anchor", completion.anchor), ("wall", completion.wall)):
        assert moment is not None, f"a writer-produced entry must carry a {label}"
        assert moment.earliest == moment.latest, (
            f"the {label} must pin an instant, not a whole day"
        )


def test_a_completion_recorded_with_no_events_yet_carries_no_anchor(tmp_path):
    """The companion state: `append_phase_history` on a project with an empty
    event log omits `event_at` rather than nulling it, and C3 then falls back to
    the run id alone instead of comparing across two clocks."""
    entry = append_completion(_project(tmp_path), "build", RUN)
    completion = latest_completion(tmp_path, "build")

    assert "event_at" not in entry
    assert completion is not None
    assert completion.anchor is None and completion.wall is not None


def test_the_hand_built_shape_matches_the_writer(tmp_path):
    """The anti-drift assertion: the fixture helper the other C3 suites use must
    carry exactly the keys the writer carries.

    Both directions, deliberately. `written <= fixture` alone catches a fixture
    that is missing a key the writer emits — the original defect. It does NOT
    catch the writer LOSING a key: drop `event_at` and the subset still holds
    while C3 silently falls back to a wall clock. `event_at` is therefore also
    asserted by name, because its absence is not a shape change the set
    comparison can see."""
    root = _project(tmp_path)
    canon_block(root, "build", RUN, "split 1")  # a real event, so `event_at` lands
    written = set(json.loads((root / "shipwright_run_config.json").read_text(
        encoding="utf-8"))["phase_history"]["build"][-1])
    fixture = set(history_entries((RUN, "2026-07-27T10:00:00+00:00"))[0])

    assert "event_at" in written, "the writer must stamp the event anchor C3 reads"
    assert written <= fixture, f"the writer emits keys no fixture has: {written - fixture}"
    assert "event_at" in fixture, "and the fixtures must model it"


def test_the_writer_refuses_to_let_a_caller_overwrite_the_timestamp(tmp_path):
    """`at` joined `run_id`/`date` as canonical, so the guard must cover it."""
    result = subprocess.run(
        [sys.executable, str(TOOLS / "append_phase_history.py"),
         "--project-root", str(_project(tmp_path)), "--phase", "build",
         "--run-id", RUN, "--entry-json", '{"at": "2020-01-01T00:00:00+00:00"}'],
        capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 1
    assert "at" in result.stderr


# --- the whole canon block, in the order the phase skills run it --------------

def canon_block(root: Path, phase: str, run_id: str, label: str) -> None:
    """C1 -> C3 -> completion, exactly as every phase skill sequences it.

    Verified against project/design/plan/build/test/changelog/deploy: each runs
    `record_event.py --type phase_completed --phase <phase>`, then
    `generate_session_handoff.py --canon-marker --phase <phase>`, then its
    completion producer. Driving anything less than this sequence is what let
    two clock defects through a green suite.
    """
    env = {**os.environ, "SHIPWRIGHT_RUN_ID": run_id}
    _run("record_event.py", "--project-root", str(root),
         "--type", "phase_completed", "--phase", phase,
         "--detail", label, env=env)
    _run("generate_session_handoff.py", "--project-root", str(root),
         "--reason", f"{phase} phase complete: {label}",
         "--phase", phase, "--canon-marker", env=env)
    _run("append_phase_history.py", "--project-root", str(root),
         "--phase", phase, "--run-id", run_id, env=env)


def test_the_marker_and_the_completion_land_on_one_clock(tmp_path):
    """The invariant everything else rests on: a correct canon block leaves the
    marker's timestamp and the completion's `event_at` EQUAL. They are stamped
    by two different tools from the same function, moments apart."""
    root = _project(tmp_path)
    canon_block(root, "changelog", RUN, "first")

    marker = parse_canon_frontmatter(
        (root / ".shipwright" / "agent_docs" / "session_handoff.md").read_text(
            encoding="utf-8"))
    entry = json.loads((root / "shipwright_run_config.json").read_text(
        encoding="utf-8"))["phase_history"]["changelog"][-1]

    assert marker is not None
    assert entry["event_at"] == marker["timestamp"], (
        "marker and completion must read one clock — comparing the marker "
        "against the wall-clock `at` is the defect this pins"
    )
    assert entry["at"] > entry["event_at"], (
        "and `at` must really be later, or this test proves nothing"
    )


def test_a_phase_rerun_that_records_no_new_event_still_passes(tmp_path):
    """THE regression. `record_event` dedups `phase_completed` first-wins on
    (phase, splitId), so a re-run appends no event; the marker is rewritten but
    re-derives the same anchor. Comparing it against the completion's wall clock
    reported 'a later step completed without re-writing it' — on a note rewritten
    seconds earlier, in the same words as the true positive, with a remedy that
    could not clear it because re-running C3 re-derives the same time."""
    root = _project(tmp_path)
    canon_block(root, "changelog", RUN, "first")
    assert check_c3(root, "changelog").ok is True, "first run must pass"

    canon_block(root, "changelog", RUN, "second")

    # Count `phase_completed` ONLY: the log also carries whatever else the tools
    # emit (`generate_session_handoff` records a `session_id_fallback` warning
    # when SHIPWRIGHT_SESSION_ID is unset — true on CI, false locally). Asserting
    # over the whole file passed on one machine and failed on the other.
    completions = [
        json.loads(line) for line in
        (root / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries = json.loads((root / "shipwright_run_config.json").read_text(
        encoding="utf-8"))["phase_history"]["changelog"]
    result = check_c3(root, "changelog")

    phase_events = [e for e in completions if e.get("type") == "phase_completed"]
    assert len(phase_events) == 1, f"the dedup must have held, got {phase_events}"
    assert len(entries) == 2, "but the completion record must have grown"
    assert result.ok is True, result.detail


def test_a_split_that_skips_the_marker_write_is_still_caught(tmp_path):
    """The true positive, driven the same way — so the fix above cannot have
    been bought by blinding the check. Split 2 records its own event and its own
    completion but never re-writes the marker."""
    root = _project(tmp_path)
    canon_block(root, "build", RUN, "split 1")
    _run("record_event.py", "--project-root", str(root),
         "--type", "phase_completed", "--phase", "build",
         "--split-id", "02-second", "--detail", "split 2",
         env={**os.environ, "SHIPWRIGHT_RUN_ID": RUN})
    _run("append_phase_history.py", "--project-root", str(root),
         "--phase", "build", "--run-id", RUN,
         env={**os.environ, "SHIPWRIGHT_RUN_ID": RUN})

    result = check_c3(root, "build")

    assert result.ok is False, result.detail
    assert "predates that run's last recorded completion" in result.detail


def test_a_later_phase_that_rewrites_the_note_does_not_accuse_the_earlier_one(tmp_path):
    """The other-phase branch, same root cause. deploy owns the note; changelog
    is re-run and rewrites the marker WITHOUT recording a new event. deploy did
    write its note, so it must read as superseded, not as having left none —
    otherwise following the remedy makes the two phases accuse each other
    forever."""
    root = _project(tmp_path)
    canon_block(root, "deploy", "deploy-v9.9.9", "release")
    canon_block(root, "changelog", RUN, "notes rebuilt")

    result = check_c3(root, "deploy")

    assert result.is_skipped, result.detail
    assert "superseded" in result.detail and "changelog" in result.detail


# --- iterate's completions come from its own ledger ---------------------------

def test_the_iterate_ledger_writer_produces_a_readable_completion(tmp_path):
    """HIGH-3. `iterate` has never written `phase_history`; F5c writes the
    file-per-run ledger. C3 must read the record iterate actually keeps."""
    root = _project(tmp_path)
    _run("record_event.py", "--project-root", str(root),
         "--type", "phase_completed", "--phase", "iterate", "--detail", "done")
    _run("append_iterate_entry.py", "--project-root", str(root),
         "--run-id", ITERATE_RUN, "--entry-json", json.dumps({
             "type": "change", "complexity": "medium",
             "branch": "iterate/c3-phase-history-join", "tests_passed": True,
         }))

    completion = latest_completion(root, "iterate")
    config = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))
    entry = json.loads(
        (root / ".shipwright" / "agent_docs" / "iterates" /
         f"{ITERATE_RUN}.json").read_text(encoding="utf-8"))

    assert "iterate" not in config.get("phase_history", {}), (
        "the ledger writer must not have started writing phase_history"
    )
    assert completion is not None, "iterate's completion must be readable"
    assert completion.run_id == ITERATE_RUN
    assert completion.wall is not None, (
        "its wall clock must be readable — that is what orders iterate against "
        "another phase in the cross-phase branch"
    )
    # The recorded bound: the ledger stamps no event anchor, so C3 never consults
    # the clock for iterate. Asserted rather than assumed, so the day someone adds
    # `event_at` there this test is what tells them the bound moved.
    assert "event_at" not in entry
    assert completion.anchor is None


def test_an_iterate_that_wrote_its_note_passes_end_to_end(tmp_path):
    """Ledger entry + marker, both from real writers, joined by C3."""
    root = _project(tmp_path)
    _run("append_iterate_entry.py", "--project-root", str(root),
         "--run-id", ITERATE_RUN, "--entry-json", json.dumps({
             "type": "change", "complexity": "medium", "tests_passed": True,
             "branch": "iterate/c3-phase-history-join",
         }))
    write_handoff(root, phase="iterate", run_id=ITERATE_RUN,
                  timestamp="2026-07-27T08:00:00+00:00")

    result = check_c3(root, "iterate")

    assert result.ok is True, result.detail
