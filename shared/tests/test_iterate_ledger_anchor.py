"""The iterate ledger writer's event anchor, driven through the real tools.

Sibling of ``test_completion_writers.py`` and held to the same rule: no
hand-built dicts, every producer invoked as a subprocess exactly as the
finalization runs it. That suite covers ``append_phase_history`` (the seven
pipeline phases); this one covers ``append_iterate_entry`` (F5c), whose
completions live in a file-per-run ledger rather than in ``phase_history``.

Until iterate-2026-07-28-it0-followup-anchor-prose the ledger stamped no
``event_at``, so Canon C3 never consulted its clock for the ``iterate`` phase.
That was recorded as a KNOWN BOUND in four places and left safe by one property:
the ledger is one file per run id, so a stale marker names a DIFFERENT run and
the run-id branch catches it. What escaped was the case the run id cannot see —
an **in-place F5c re-run under the same id**. These tests pin the anchor's
arrival, its absence where there is nothing to anchor to, and the verdict that
was previously unreachable (trg-1346abbd).

The scaffolding below is deliberately local rather than imported from
``test_completion_writers``: coupling two collected test modules' import graphs
is the failure class ADR-044/045 exist for, and fifteen lines of subprocess
plumbing is the cheaper side of that trade.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from _c3_fixtures import EARLY, ITERATE_RUN, write_iterate_entry  # noqa: E402
from shared.tests._iterate_entry_helpers import write_current_evidence  # noqa: E402
from lib.canon_frontmatter import parse_canon_frontmatter  # noqa: E402
from lib.iterate_entry import entry_file_for  # noqa: E402
from lib.phase_history import latest_completion  # noqa: E402
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

TOOLS = REPO_ROOT / "shared" / "scripts" / "tools"
_ENV = {**os.environ, "SHIPWRIGHT_RUN_ID": ITERATE_RUN}


def _run(tool: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke a producer exactly as the finalization does."""
    result = subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        capture_output=True, text=True, timeout=120, env=_ENV,
    )
    assert result.returncode == 0, f"{tool} failed: {result.stderr}"
    return result


def _project(root: Path) -> Path:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {}}), encoding="utf-8"
    )
    write_current_evidence(root, ITERATE_RUN)
    return root


def _event(root: Path, *args: str) -> None:
    _run("record_event.py", "--project-root", str(root), *args)


def _marker(root: Path) -> dict | None:
    """F5b's half of the canon block — the note plus its marker."""
    _run("generate_session_handoff.py", "--project-root", str(root),
         "--reason", "iterate complete", "--phase", "iterate", "--canon-marker")
    return parse_canon_frontmatter(
        (root / ".shipwright" / "agent_docs" / "session_handoff.md").read_text(
            encoding="utf-8"))


def _f5c(root: Path) -> dict:
    """F5c — append the ledger entry, and read back what landed on disk."""
    _run("append_iterate_entry.py", "--project-root", str(root),
         "--run-id", ITERATE_RUN, "--entry-json", json.dumps({
             "type": "change", "complexity": "medium", "tests_passed": True,
             "branch": f"iterate/{ITERATE_RUN}"}))
    return json.loads(entry_file_for(root, ITERATE_RUN).read_text(encoding="utf-8"))


# --- the anchor lands, and reads back as an instant ---------------------------

def test_the_ledger_writer_stamps_the_anchor_c3_reads(tmp_path):
    """The bound closed. `latest_event_dt` is the same function the marker is
    stamped from, so the two sides of C3's comparison sit on ONE clock."""
    root = _project(tmp_path)
    _event(root, "--type", "phase_completed", "--phase", "iterate", "--detail", "done")

    entry = _f5c(root)
    completion = latest_completion(root, "iterate")

    assert entry["event_at"], "the ledger must carry the anchor C3 reads"
    assert completion is not None and completion.anchor is not None
    assert completion.anchor.earliest == completion.anchor.latest, (
        "the anchor must pin an instant, not a whole day"
    )
    assert completion.wall is not None, (
        "and the wall clock must survive — it is what orders iterate against "
        "another phase in the cross-phase branch"
    )


@pytest.mark.parametrize("log", [None, "", "\n\n", "not json\n{oops\n"],
                         ids=["absent", "empty", "blank-lines", "unparseable"])
def test_a_ledger_entry_with_nothing_to_anchor_to_carries_no_anchor(tmp_path, log):
    """The companion state, and why the key is OMITTED rather than nulled.

    All four inputs make `latest_event_dt` answer None — it never raises — and an
    absent key is a stated unknown that sends C3 back to the run id alone. That is
    exactly how every ledger entry written before the anchor existed must keep
    being read, so the writer must turn "nothing to anchor to" into neither a
    failure nor a null. Driven over the real log shapes rather than the absent
    one alone: an empty file and an all-corrupt file take different branches
    inside the helper, and only the absent case short-circuits on `exists()`.
    """
    root = _project(tmp_path)
    if log is not None:
        (root / "shipwright_events.jsonl").write_text(log, encoding="utf-8")

    entry = _f5c(root)
    completion = latest_completion(root, "iterate")

    assert "event_at" not in entry
    assert completion is not None
    assert completion.anchor is None and completion.wall is not None


def test_the_marker_and_the_ledger_entry_land_on_one_clock(tmp_path):
    """The invariant the whole comparison rests on, in the ordering that makes
    the two EQUAL: one event, then the marker, then F5c, with nothing recorded
    in between. Equality is the shape of a correct run — `RecordedTime.after` is
    strict precisely so that it reads as a pass and not as a missing write."""
    root = _project(tmp_path)
    _event(root, "--type", "phase_completed", "--phase", "iterate", "--detail", "done")
    marker = _marker(root)

    entry = _f5c(root)

    assert marker is not None
    assert entry["event_at"] == marker["timestamp"], (
        "both are latest_event_dt().isoformat() — one function, one serialization"
    )
    assert check_c3(root, "iterate").ok is True


def test_the_real_f5c_before_f5b_ordering_still_passes(tmp_path):
    """`finalize_bundle` runs F5c BEFORE F5b, so the run's own `work_completed`
    event does not exist when the ledger is stamped and the marker is therefore
    strictly NEWER than the anchor. The activated clock branch must read that as
    the correct run it is — this is the no-false-positive side of the change."""
    root = _project(tmp_path)
    _event(root, "--type", "phase_completed", "--phase", "iterate", "--detail", "prior")

    entry = _f5c(root)
    # F5b's real event, FR-gate flags and all (ADR-059 applies to every iterate).
    _event(root, "--type", "work_completed", "--source", "iterate",
           "--description", "the run's own completion",
           "--change-type", "tooling", "--none-reason", "fixture, touches no FR")
    marker = _marker(root)

    assert marker is not None and entry["event_at"] < marker["timestamp"]
    assert check_c3(root, "iterate").ok is True, check_c3(root, "iterate").detail


# --- the verdict the bound used to hide ---------------------------------------

def test_an_in_place_f5c_rerun_after_a_new_event_is_now_caught(tmp_path):
    """THE true positive, driven rather than asserted about — so the activation
    cannot have been bought by blinding the check.

    The ledger is one file per run id, so an F5c re-run REWRITES the entry under
    the same id and the run-id branch sees nothing wrong. With the anchor
    stamped, the rewritten completion is newer than the note nobody re-wrote,
    and C3 says so instead of passing.
    """
    root = _project(tmp_path)
    _event(root, "--type", "phase_completed", "--phase", "iterate", "--detail", "first")
    _f5c(root)
    _marker(root)
    assert check_c3(root, "iterate").ok is True, "the single-pass run must pass"

    _event(root, "--type", "test_run", "--detail", "a later event")
    _f5c(root)

    result = check_c3(root, "iterate")

    assert result.ok is False, result.detail
    assert "predates that run's last recorded completion" in result.detail


# --- the guard, and the fixture -----------------------------------------------

def test_the_writer_refuses_to_let_a_caller_forge_the_anchor(tmp_path):
    """`event_at` is produced now, not merely reserved, so the guard that keeps
    a caller out of it protects a real value rather than an empty seat. It lives
    in `main()`, where the sibling producer keeps its own, and nothing covered
    it: `test_append_iterate_entry.py` drives only the Python API."""
    result = subprocess.run(
        [sys.executable, str(TOOLS / "append_iterate_entry.py"),
         "--project-root", str(_project(tmp_path)), "--run-id", ITERATE_RUN,
         "--entry-json", json.dumps({"event_at": "2020-01-01T00:00:00+00:00"})],
        capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 1
    assert "event_at" in result.stderr


def test_main_stamps_and_omits_the_anchor_in_process(tmp_path):
    """The same two behaviours as above, driven IN-PROCESS through `main(argv)`.

    Not redundant with the subprocess tests: diff-coverage measures the process
    it instruments, so a `main()` reached only by `subprocess.run` reads as 0%
    covered and the patch-coverage gate blocks a change that is in fact fully
    exercised. The subprocess tests remain the honest ones — they prove the tool
    behaves as the pipeline invokes it — and this one makes that provable to the
    coverage gate as well.
    """
    from tools.append_iterate_entry import main as append_main

    entry_json = json.dumps({"type": "change", "complexity": "medium",
                             "tests_passed": True, "branch": f"iterate/{ITERATE_RUN}"})
    argv = ["--project-root", str(_project(tmp_path)), "--run-id", ITERATE_RUN,
            "--entry-json", entry_json]

    assert append_main(argv) == 0
    assert "event_at" not in json.loads(
        entry_file_for(tmp_path, ITERATE_RUN).read_text(encoding="utf-8"))

    _event(tmp_path, "--type", "phase_completed", "--phase", "iterate",
           "--detail", "now there is something to anchor to")

    assert append_main(argv) == 0
    entry = json.loads(entry_file_for(tmp_path, ITERATE_RUN).read_text(encoding="utf-8"))
    assert entry["event_at"], "the second call must stamp the anchor"


def test_the_hand_built_ledger_fixture_matches_the_writer(tmp_path):
    """The ledger's half of the anti-drift assertion `test_completion_writers`
    makes for `phase_history` — and EQUALITY, not a subset.

    A subset catches a fixture missing a key the writer emits, but not a fixture
    that invents one, and a suite built on an invented key asserts against a
    shape production never produces: the same defect in the other direction.
    Equality is only sound because `_f5c` passes the MINIMAL `--entry-json` — the
    canonical keys plus the four the validator requires. The optional ones
    (`spec`, `adr`) are the caller's payload, not the writer's shape, so they
    stay out of both sides.

    An event is recorded FIRST so the writer's key set is deterministic: with no
    log it legitimately omits the anchor, and the comparison would then pass
    while the fixture modelled the wrong shape.
    """
    root = _project(tmp_path)
    _event(root, "--type", "phase_completed", "--phase", "iterate", "--detail", "done")
    written = set(_f5c(root))
    fixture = set(json.loads(
        write_iterate_entry(tmp_path / "fx", ITERATE_RUN, EARLY).read_text(
            encoding="utf-8")))

    assert "event_at" in written, "the writer must stamp the event anchor C3 reads"
    assert written == fixture, (
        f"writer-only keys: {written - fixture}; fixture-only keys: {fixture - written}"
    )
