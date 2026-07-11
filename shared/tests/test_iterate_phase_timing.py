"""Tests for iterate per-phase timing — M-Pre-1 iterate half (Iterate-Rail durations).

Follow-up to campaign monorepo-wow-usability-2026-07-10 sub-iterate B1
(triage trg-8efeb3d7). The iterate flow writes ONE ``work_completed`` event and
its phases are LLM-driven SKILL steps, so per-phase durations are produced by a
lightweight boundary-mark sidecar folded into ``work_completed.phase_timings`` at
finalize. These tests pin the 5-group SSoT, the mark/compute/normalize logic, the
finalize fold, and the record_event CLI parity.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_phase_groups as ipg  # noqa: E402

CANON_RUN = "iterate-2026-07-11-iterate-phase-timing"
_T0 = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# --------------------------------------------------------------------------- #
# AC1 — SSoT + drift pin to session_plan._PHASE_CATALOG
# --------------------------------------------------------------------------- #

def test_groups_are_the_five_rail_nodes():
    assert ipg.ITERATE_PHASE_GROUPS == ("scope", "build", "review", "test", "finalize")


def test_groups_pin_to_session_plan_catalog():
    """The shared timing SSoT must match the plugin-local Plan-Card grouping so
    the WebUI can join phases-per-group with duration-per-group. Loaded by file
    path (not ``import lib.session_plan``) to sidestep the ADR-045 ``lib`` package
    collision between shared/scripts/lib and the plugin-local lib."""
    sp_path = (
        Path(__file__).resolve().parents[2]
        / "plugins" / "shipwright-iterate" / "scripts" / "lib" / "session_plan.py"
    )
    spec = importlib.util.spec_from_file_location("_ipt_session_plan", sp_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seen: list[str] = []
    for _pid, group, _fn in mod._PHASE_CATALOG:
        if group not in seen:
            seen.append(group)
    assert tuple(seen) == ipg.ITERATE_PHASE_GROUPS


# --------------------------------------------------------------------------- #
# AC2 — mark sidecar: append, first-wins, containment, validation
# --------------------------------------------------------------------------- #

def test_append_mark_writes_sidecar(tmp_path):
    path = ipg.append_mark(tmp_path, CANON_RUN, "build", ts=_iso(_T0))
    assert path == ipg.sidecar_path(tmp_path, CANON_RUN)
    assert path.name == f"{CANON_RUN}.phase_timings.jsonl"
    marks = ipg.read_marks(tmp_path, CANON_RUN)
    assert marks == [{"phase": "build", "ts": _iso(_T0)}]


def test_append_mark_is_first_wins_per_group(tmp_path):
    ipg.append_mark(tmp_path, CANON_RUN, "build", ts=_iso(_T0))
    ipg.append_mark(tmp_path, CANON_RUN, "build", ts=_iso(_T0 + timedelta(minutes=5)))
    marks = ipg.read_marks(tmp_path, CANON_RUN)
    assert [m["phase"] for m in marks] == ["build"]
    assert marks[0]["ts"] == _iso(_T0)  # earliest write kept


def test_append_mark_rejects_unknown_group(tmp_path):
    with pytest.raises(ValueError):
        ipg.append_mark(tmp_path, CANON_RUN, "deploy", ts=_iso(_T0))


def test_read_marks_skips_malformed_lines(tmp_path):
    p = ipg.sidecar_path(tmp_path, CANON_RUN)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"phase": "scope", "ts": _iso(_T0)}) + "\n"
        + "{ not json\n"
        + json.dumps({"phase": "build", "ts": _iso(_T0 + timedelta(minutes=1))}) + "\n",
        encoding="utf-8",
    )
    marks = ipg.read_marks(tmp_path, CANON_RUN)
    assert [m["phase"] for m in marks] == ["scope", "build"]


def test_sidecar_path_contains_crafted_run_id(tmp_path):
    p = ipg.sidecar_path(tmp_path, "../../etc/evil")
    assert p.parent == tmp_path / ".shipwright" / "agent_docs" / "iterates"


# --------------------------------------------------------------------------- #
# AC3 — compute_phase_timings
# --------------------------------------------------------------------------- #

def test_compute_durations_chronological_with_end_ts():
    marks = [
        {"phase": "scope", "ts": _iso(_T0)},
        {"phase": "build", "ts": _iso(_T0 + timedelta(seconds=30))},
        {"phase": "review", "ts": _iso(_T0 + timedelta(seconds=40))},
        {"phase": "test", "ts": _iso(_T0 + timedelta(seconds=50))},
        {"phase": "finalize", "ts": _iso(_T0 + timedelta(seconds=55))},
    ]
    end = _T0 + timedelta(seconds=70)
    out = ipg.compute_phase_timings(marks, end)
    assert [e["phase"] for e in out] == ["scope", "build", "review", "test", "finalize"]
    assert out[0] == {"phase": "scope", "started": _iso(_T0), "duration_ms": 30000}
    assert out[1]["duration_ms"] == 10000
    assert out[-1]["duration_ms"] == 15000  # finalize end = end_ts (55s..70s)


def test_compute_empty_marks_is_empty():
    assert ipg.compute_phase_timings([], _T0) == []


def test_compute_durations_non_negative_and_int():
    marks = [{"phase": "build", "ts": _iso(_T0 + timedelta(seconds=10))}]
    out = ipg.compute_phase_timings(marks, _T0)  # end BEFORE the mark
    assert out[0]["duration_ms"] == 0  # clamped, never negative
    assert isinstance(out[0]["duration_ms"], int)


# --------------------------------------------------------------------------- #
# normalize_phase_timings — the shared validator used inside fold_into_event
# --------------------------------------------------------------------------- #

def test_normalize_accepts_valid_block():
    block = [{"phase": "build", "started": _iso(_T0), "duration_ms": 5}]
    assert ipg.normalize_phase_timings(block) == block


@pytest.mark.parametrize("bad", [
    [{"phase": "nope", "started": _iso(_T0), "duration_ms": 5}],
    [{"phase": "build", "started": _iso(_T0), "duration_ms": -5}],
    [{"phase": "build", "duration_ms": 5}],
    [{"started": _iso(_T0), "duration_ms": 5}],
    "not-a-list",
    [123],
])
def test_normalize_rejects_malformed(bad):
    with pytest.raises(ValueError):
        ipg.normalize_phase_timings(bad)


# --------------------------------------------------------------------------- #
# AC2 — the CLI (mark + summarize)
# --------------------------------------------------------------------------- #

def test_cli_mark_and_summarize(tmp_path, capsys):
    from tools import iterate_phase_timing as cli

    rc = cli.main(["mark", "scope", "--project-root", str(tmp_path), "--run-id", CANON_RUN])
    assert rc == 0
    rc = cli.main(["mark", "build", "--project-root", str(tmp_path), "--run-id", CANON_RUN])
    assert rc == 0
    marks = ipg.read_marks(tmp_path, CANON_RUN)
    assert [m["phase"] for m in marks] == ["scope", "build"]

    capsys.readouterr()
    rc = cli.main(["summarize", "--project-root", str(tmp_path), "--run-id", CANON_RUN])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert [e["phase"] for e in out] == ["scope", "build"]


def test_cli_mark_rejects_noncanonical_run_id(tmp_path):
    from tools import iterate_phase_timing as cli

    rc = cli.main(["mark", "build", "--project-root", str(tmp_path), "--run-id", "not-canonical"])
    assert rc != 0


# --------------------------------------------------------------------------- #
# AC4 — finalize folds phase_timings into work_completed
# --------------------------------------------------------------------------- #

_VALID_EXTRAS = {"change_type": "tooling", "none_reason": "phase-timing unit test"}


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8"
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def _latest_work_completed(project: Path) -> dict:
    from tools.record_event import read_events
    events = [e for e in read_events(project) if e.get("type") == "work_completed"]
    return events[-1]


def test_finalize_folds_phase_timings(project, monkeypatch):
    monkeypatch.chdir(project)
    from tools.finalize_iterate import run

    ipg.append_mark(project, CANON_RUN, "scope", ts=_iso(_T0))
    ipg.append_mark(project, CANON_RUN, "build", ts=_iso(_T0 + timedelta(seconds=20)))
    ipg.append_mark(project, CANON_RUN, "finalize", ts=_iso(_T0 + timedelta(seconds=30)))

    run(project, run_id=CANON_RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)
    assert "phase_timings" in ev
    phases = [e["phase"] for e in ev["phase_timings"]]
    assert phases == ["scope", "build", "finalize"]
    assert ev["phase_timings"][0]["duration_ms"] == 20000


def test_finalize_without_sidecar_omits_phase_timings(project, monkeypatch):
    monkeypatch.chdir(project)
    from tools.finalize_iterate import run

    run(project, run_id="test-no-timing-001", event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)
    assert "phase_timings" not in ev


def test_fold_into_event_is_additive_and_validated():
    """The lib fold helper is the sole producer (finalize calls it): sets a valid
    block, no-ops on empty marks, and never overwrites a pre-existing field."""
    ev: dict = {}
    ipg.fold_into_event(ev, "no-such-root", "iterate-2026-07-11-none")
    assert "phase_timings" not in ev  # no sidecar -> unchanged

    ev2 = {"phase_timings": [{"phase": "build", "started": "x", "duration_ms": 1}]}
    ipg.fold_into_event(ev2, "no-such-root", CANON_RUN)  # pre-existing wins
    assert ev2["phase_timings"][0]["duration_ms"] == 1
