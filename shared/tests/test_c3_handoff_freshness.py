"""Canon **C3** — did THIS phase leave the handover note?

iterate-2026-07-27-c3-phase-content-key keyed C3 on a run id the caller supplied.
The internal review cascade showed that key is vacuous in one regime and broken
in the other; this suite pins the replacement.

This half covers the note that names THIS phase — the run-id join — plus the
four unanswerable states and the module guards. Its siblings:

* ``test_c3_cross_phase_verdict.py`` — a DIFFERENT phase owns the note, which is
  where both regressions of this check have lived.
* ``test_c3_same_phase_window.py`` — one run recording several completions.
* ``test_c3_applicability.py`` — which phases are checked, and whole-run audits.
* ``test_completion_writers.py`` — the real producers, in real canon order.
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

import pytest  # noqa: E402

from _c3_fixtures import (  # noqa: E402
    EARLY,
    LATE,
    OLDER,
    RUN,
    history_entries as _hist,
    write_handoff,
    write_run_config,
)
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

#: RLO + zero-width space, built from codepoints so this source stays ASCII.
_RLO = chr(0x202E)
_ZWSP = chr(0x200B)


def _project(root: Path, *, marker_phase: str, marker_run: str, marker_ts: str = EARLY,
             history: dict | None = None, marker: bool = True) -> Path:
    write_handoff(root, phase=marker_phase, run_id=marker_run,
                  timestamp=marker_ts, marker=marker)
    write_run_config(root, history)
    return root


# --- the note names THIS phase: the run-id join -------------------------------

def test_the_phase_that_wrote_the_note_passes(tmp_path):
    _project(tmp_path, marker_phase="build", marker_run=RUN,
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    assert result.ok is True, result.detail
    assert RUN in result.detail


def test_a_note_from_an_earlier_run_of_this_phase_warns(tmp_path):
    _project(tmp_path, marker_phase="build", marker_run=OLDER,
             history={"build": _hist((OLDER, EARLY), (RUN, LATE))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "earlier" in result.detail and OLDER in result.detail


def test_a_note_naming_a_run_history_never_recorded_warns(tmp_path):
    """Distinct from 'earlier run' on purpose: it is the shape a mid-flight read
    takes, and conflating the two would misattribute it as a stale note."""
    _project(tmp_path, marker_phase="build", marker_run="build-ghost",
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "does not hold" in result.detail


# --- unanswerable says which part ---------------------------------------------

def test_a_missing_handoff_is_not_a_pass(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "missing" in result.detail


def test_a_handoff_without_a_canon_marker_is_not_a_pass(tmp_path):
    _project(tmp_path, marker_phase="build", marker_run=RUN, marker=False,
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "no canon marker" in result.detail


def test_no_recorded_completion_for_this_phase_is_not_a_pass(tmp_path):
    _project(tmp_path, marker_phase="build", marker_run=RUN, history={})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "phase_history" in result.detail


def test_a_marker_without_a_run_id_is_not_a_pass(tmp_path):
    _project(tmp_path, marker_phase="build", marker_run="",
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "no run id" in result.detail


def test_an_inaccessible_handoff_reads_as_unreadable_not_missing(tmp_path, monkeypatch):
    _project(tmp_path, marker_phase="build", marker_run=RUN,
             history={"build": _hist((RUN, EARLY))})

    def _denied(*_a, **_k):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "read_text", _denied)
    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "unreadable" in result.detail and "missing" not in result.detail


# --- the clock is gone, and stays gone ----------------------------------------

def test_the_check_never_consults_mtime(tmp_path):
    fresh, stale = tmp_path / "a", tmp_path / "b"
    for root in (fresh, stale):
        root.mkdir()
        _project(root, marker_phase="build", marker_run=RUN,
                 history={"build": _hist((RUN, EARLY))})
    old = time.time() - 86_400
    os.utime(stale / ".shipwright" / "agent_docs" / "session_handoff.md", (old, old))

    a = check_c3(fresh, "build")
    b = check_c3(stale, "build")

    assert (a.ok, a.detail) == (b.ok, b.detail)


@pytest.mark.parametrize("module_name", [
    "verifiers.handoff_phase_canon",  # the verdict
    "verifiers.handoff_marker",       # where the file I/O actually lives
    "lib.phase_history",              # where the timekeeping actually lives
])
def test_no_mtime_call_survives_anywhere_in_the_chain(module_name):
    """#467's guard inspected one FUNCTION while the file I/O lived in another.
    Its replacement inspected one MODULE — the only one of the three with no file
    I/O at all, so a reintroduced `st_mtime` would have landed outside it. Guard
    every module the check reads through."""
    module = importlib.import_module(module_name)
    src = inspect.getsource(module)
    for forbidden in ("st_mtime", "getmtime", "max_age_seconds", "time.time"):
        assert forbidden not in src, f"{module_name}: {forbidden}"


def test_the_check_takes_no_run_id():
    """The parameter is REMOVED, not defaulted: #467 kept a defaulted run_id on
    the runner, and that is exactly how the caller mismatch reached C3."""
    params = inspect.signature(check_c3).parameters

    assert "run_id" not in params
    assert list(params) == ["project_root", "phase"]


def test_terminal_escapes_in_a_marker_never_reach_the_detail(tmp_path):
    hostile = "a\x1b[31mred" + _RLO + "reversed" + _ZWSP
    _project(tmp_path, marker_phase="build", marker_run=hostile,
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    for forbidden in ("\x1b", _RLO, _ZWSP):
        assert forbidden not in result.detail
