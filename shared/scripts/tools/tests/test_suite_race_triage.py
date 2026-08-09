"""F0 race follow-ups - the observation must outlive the session that made it.

iterate-2026-07-27-f0-race-triage. A unit that is red in parallel and GREEN on its
authoritative alone re-run leaves the gate green, by design. Until this producer
existed that observation was only a `print`, so it died with the console.

The load-bearing behaviours: the runner itself writes a TRACKED entry (AC1/AC2); one
open entry per unit that is never auto-closed but reopens after an operator closes it
(AC3); captured test output never reaches the published log (AC5/AC13); an infra
retry is deliberately NOT filed (AC9); and an observed race that could not be
recorded stops an otherwise-green run (AC8).

The CLI wiring - ordering, exit-code precedence, `main()` end to end - lives in
`test_suite_race_cli.py`.

Every test writes to `tmp_path`. Pointing a Shipwright runner at a tracked directory
leaks its `.shipwright/triage.jsonl` writes into version control (conventions,
2026-07-15).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import scripts.tools.suite_race_triage as mod  # noqa: E402
from scripts.tools.run_test_suite import (  # noqa: E402
    INFRA,
    PASS,
    RETRY_INFRA,
    RETRY_SERIAL,
    TEST_FAILURE,
    SuiteResult,
    UnitResult,
    unrecorded_races,
)
from scripts.tools.suite_report import (  # noqa: E402
    MAX_TITLE,
    entry_title,
    facts,
    suite_command,
)
from triage import mark_status, read_all_items  # noqa: E402

_XDIST = ("shared/tests",)
_ALONE = "uv run --with pytest pytest tests -q"


def _raced(unit_id="shared/tests", rc=1, serial_rc=0, output="", cmd=_ALONE):
    """A UnitResult exactly as `run_suite` leaves a confirmed race."""
    return UnitResult(unit_id, PASS, rc, 1.0, output, race=True,
                      retry_kind=RETRY_SERIAL, serial_rc=serial_rc, retry_cmd=cmd)


def _suite(*results, exit_code=0, xdist=_XDIST):
    return SuiteResult(list(results), exit_code, 12.0, xdist)


def _emit(root, *results, **kw):
    res = list(results)
    return mod.emit_race_followups(root, res, _XDIST, **kw)


def _items(root):
    return read_all_items(root)


# --- AC1/AC2: the runner writes it, into the TRACKED store, under the given root ---

def test_a_confirmed_race_is_written_to_the_tracked_store(tmp_path):
    report = _emit(tmp_path, _raced(), run_id="iterate-x", commit="deadbeef")

    assert (tmp_path / ".shipwright" / "triage.jsonl").is_file()
    assert not (tmp_path / ".shipwright" / "triage.outbox.jsonl").exists(), \
        "the outbox is for idle-main background producers; F0 runs inside the worktree"
    item, = _items(tmp_path)
    assert item["source"] == "f0-suite" and item["kind"] == "bug"
    assert item["severity"] == "high" and item["suggestedPriority"] == "P1"
    assert item["dedupKey"] == "f0-race:shared/tests"
    assert item["status"] == "triage" and item["runId"] == "iterate-x"
    assert item["commit"] == "deadbeef" and item["suiteId"] == "shared/tests"
    assert report.recorded == {"shared/tests": item["id"]} and not report.failed


def test_the_store_is_resolved_from_the_passed_root_not_the_cwd(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.chdir(elsewhere)

    _emit(target, _raced())

    assert (target / ".shipwright" / "triage.jsonl").is_file()
    assert not (elsewhere / ".shipwright").exists()


# --- AC3: one durable entry per unit; an operator decision persists ---

def test_a_second_sighting_reuses_the_open_entry_instead_of_spamming(tmp_path):
    first = _emit(tmp_path, _raced())
    second = _emit(tmp_path, _raced())

    assert len(_items(tmp_path)) == 1, "one open entry per unit, however often it races"
    handle = first.recorded["shared/tests"]
    assert second.recorded == {"shared/tests": handle}, \
        "the second run must still surface the durable handle, not go quiet"
    assert not second.failed


def test_a_race_after_the_operator_closed_the_card_keeps_that_decision(tmp_path):
    first = _emit(tmp_path, _raced())
    mark_status(tmp_path, first.recorded["shared/tests"],
                new_status="dismissed", by="cli", reason="notRelevant")

    again = _emit(tmp_path, _raced())

    assert again.recorded == first.recorded, "the original decision remains the handle"
    assert [item["status"] for item in _items(tmp_path)] == ["dismissed"]


def test_two_units_racing_get_one_entry_each(tmp_path):
    report = _emit(tmp_path, _raced("shared/tests"), _raced("integration-tests"))

    assert len(report.recorded) == 2 and not report.failed
    assert {i["dedupKey"] for i in _items(tmp_path)} == {
        "f0-race:shared/tests", "f0-race:integration-tests"}


# --- AC9: only the test-failure -> green-alone class is filed ---

@pytest.mark.parametrize("res", [
    UnitResult("integration-tests", PASS, 2, 1.0, "", race=True,
               retry_kind=RETRY_INFRA, serial_rc=0),          # transient uv fault
    UnitResult("integration-tests", TEST_FAILURE, 1, 1.0, ""),  # red both ways
    UnitResult("integration-tests", INFRA, 5, 1.0, ""),         # nothing collected
    UnitResult("integration-tests", INFRA, 124, 1.0, ""),       # hang
    UnitResult("integration-tests", PASS, 0, 1.0, ""),          # plain green
])
def test_only_a_confirmed_race_is_filed(tmp_path, res):
    """An infra retry is a different diagnosis (contention between `uv` processes) and
    fires on ordinary cache noise - filing it would bury the real signal.

    Driven through the EXACT path `main()` uses (classify, then hand the survivors to
    the producer), so a regression that passed every `race` item straight through
    would fail here rather than pass a producer called with nothing.
    """
    survivors = unrecorded_races(_suite(res))
    assert survivors == []
    assert _emit(tmp_path, *survivors).recorded == {}
    assert not (tmp_path / ".shipwright" / "triage.jsonl").exists()


def test_the_predicate_accepts_exactly_the_confirmed_race(tmp_path):
    race = _raced()
    assert unrecorded_races(_suite(race, UnitResult("a", PASS, 0, 1.0))) == [race]


# --- AC5/AC13: no captured test output reaches the published log ---

def test_captured_output_never_reaches_the_tracked_log(tmp_path):
    marker = "CAPTURED-OUTPUT-MARKER-9f3a1 C:/Users/someone/private"
    _emit(tmp_path, _raced(output=f"assert 1 == 2\n{marker}\n"))

    raw = (tmp_path / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert marker not in raw and "assert 1 == 2" not in raw
    assert "red in parallel" in raw, "the measured facts ARE recorded"


def test_race_card_links_durable_evidence_without_copying_output(tmp_path):
    marker = "PRIVATE-FAILURE-OUTPUT"
    race = _raced(output=marker)
    race.evidence_path = ".shipwright/runs/f0-abc/f0-diagnostics/u/a.json"

    _emit(tmp_path, race)

    item, = _items(tmp_path)
    assert item["evidencePath"] == race.evidence_path
    raw = (tmp_path / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert marker not in raw


# --- AC14: hostile-looking text cannot break the entry or the command ---

def test_control_characters_and_length_are_neutralised(tmp_path):
    evil = "unit\nwith\rcontrol\x07chars" + "x" * 200
    _emit(tmp_path, _raced(unit_id=evil))

    item, = _items(tmp_path)
    assert len(item["title"]) <= MAX_TITLE
    assert "\n" not in item["title"] and "\r" not in item["dedupKey"]
    assert item["dedupKey"].startswith("f0-race:unitwithcontrolchars")


def test_the_title_is_capped_after_formatting(tmp_path):
    assert len(entry_title(facts(_raced(unit_id="u" * 300), ()))) <= MAX_TITLE


def test_the_dedup_key_is_identity_and_is_never_truncated(tmp_path):
    """Two units sharing an 80-char display prefix must not collapse onto one card."""
    a, b = "plugins/" + "x" * 90 + "-alpha", "plugins/" + "x" * 90 + "-beta"
    _emit(tmp_path, _raced(unit_id=a), _raced(unit_id=b))

    keys = {i["dedupKey"] for i in _items(tmp_path)}
    assert keys == {f"f0-race:{a}", f"f0-race:{b}"} and len(keys) == 2


def test_the_reproduce_commands_are_never_truncated(tmp_path):
    """A command cut mid-quote is a broken CTA, not a shorter one."""
    long_cmd = "cd plugins/deep && uv run --with pytest pytest " + "a/" * 300 + "tests"
    _emit(tmp_path, _raced(cmd=long_cmd))
    assert long_cmd in _items(tmp_path)[0]["launchPayload"]


def test_the_parallel_command_targets_the_root_that_was_actually_run(tmp_path):
    """A hard-coded `--project-root .` silently points a CTA at the wrong tree."""
    _emit(tmp_path, _raced(), run_id="iterate-x",
          suite_command=suite_command(tmp_path, "iterate-x"))

    payload = _items(tmp_path)[0]["launchPayload"]
    assert str(tmp_path) in payload and "--run-id iterate-x" in payload


# --- AC6/R10: the payload carries the command the runner ACTUALLY re-ran ---

def test_the_launch_payload_reproduces_both_sides_with_the_real_command(tmp_path):
    real = "cd plugins/shipwright-alpha && uv run --with pytest pytest tests -q"
    _emit(tmp_path, _raced(unit_id="shipwright-alpha", cmd=real))

    payload = _items(tmp_path)[0]["launchPayload"]
    assert payload.startswith("/shipwright-iterate --type bug")
    assert real in payload, "a guessed command is an unreliable Fix-now CTA"
    assert str(tmp_path) in payload and "run_test_suite.py" in payload


def test_the_card_says_what_was_measured_and_claims_no_cause(tmp_path):
    _emit(tmp_path, _raced())
    detail = _items(tmp_path)[0]["detail"]
    assert "cannot tell which of these it is" in detail
    assert "never closed automatically" in detail
    assert "NOT xdist-allowlisted" not in detail, "shared/tests IS allowlisted here"


# --- AC8: a lost record is reported, and a read-back failure is not a lost record ---

def test_an_append_failure_is_reported_not_raised(tmp_path, monkeypatch):
    class _Boom:
        @staticmethod
        def append_triage_item_idempotent(*a, **k):
            raise OSError("read-only file system")

    monkeypatch.setattr(mod, "_load_triage", lambda: _Boom)
    report = _emit(tmp_path, _raced())

    assert report.recorded == {} and "OSError" in report.failed["shared/tests"]


def test_an_unimportable_triage_api_is_reported_not_raised(tmp_path, monkeypatch):
    def _fail():
        raise ImportError("no triage module here")

    monkeypatch.setattr(mod, "_load_triage", _fail)
    assert "ImportError" in _emit(tmp_path, _raced()).failed["shared/tests"]


def test_a_read_back_failure_after_a_successful_append_is_still_recorded(tmp_path,
                                                                        monkeypatch):
    """The append fsyncs inside the triage lock, so it - not the read-back - is the
    authority. A damaged store elsewhere must never redden an otherwise green gate."""
    _emit(tmp_path, _raced())                      # first sighting: a real open entry
    monkeypatch.setattr(mod, "_open_ids", lambda *a, **k: {})

    report = _emit(tmp_path, _raced())             # suppressed, id not resolvable

    assert not report.failed
    assert report.recorded["shared/tests"] == mod.RaceFollowupReport.UNRESOLVED


def test_only_this_producers_open_entries_resolve_a_handle(tmp_path):
    import triage
    triage.append_triage_item(tmp_path, source="performance", severity="low",
                              kind="bug", title="t", detail="d",
                              dedup_key="f0-race:shared/tests")
    report = _emit(tmp_path, _raced())
    assert report.recorded["shared/tests"] != mod.RaceFollowupReport.UNRESOLVED
    assert len([i for i in _items(tmp_path) if i["source"] == "f0-suite"]) == 1


# --- AC12: commit resolution is evidence, never a failure mode ---

def test_commit_resolution_on_a_non_repo_root_yields_no_commit(tmp_path):
    assert mod.resolve_commit(tmp_path) is None


def test_a_missing_git_binary_yields_no_commit(tmp_path, monkeypatch):
    def _no_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(mod.subprocess, "run", _no_git)
    assert mod.resolve_commit(tmp_path) is None
