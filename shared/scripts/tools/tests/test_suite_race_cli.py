"""F0 race follow-ups - the CLI wiring, driven through `main()`.

iterate-2026-07-27-f0-race-triage. A CLI whose real logic lives in `main()` (arg
wiring, ordering, exit-code choice) must be tested THROUGH `main()` at least once:
driving only the pure core has previously let a whole lifecycle no-op undetected
(conventions, iterate-2026-06-10-phase-hook-lifecycle).

What only this level can prove:
  * the runner records the race ITSELF - nothing else in the pipeline does it (AC1);
  * recording happens BEFORE the report, so the warning carries its handle (AC7);
  * exit-code precedence: a green suite with a lost record exits 3, a red suite keeps
    1, and a recorded race leaves the verdict untouched (AC8);
  * `--run-id` reaches the entry, and a run with no race writes nothing (AC12).

`run_suite` is stubbed: this file is about the wiring, not about running pytest.
Everything writes to `tmp_path` (a runner pointed at a tracked root leaks its
`.shipwright/triage.jsonl` into version control - conventions, 2026-07-15).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import scripts.tools.run_test_suite as mod  # noqa: E402
import scripts.tools.suite_race_triage as race_mod  # noqa: E402
from scripts.tools.run_test_suite import (  # noqa: E402
    PASS,
    RETRY_INFRA,
    RETRY_SERIAL,
    TEST_FAILURE,
    SuiteResult,
    UnitResult,
)
from triage import read_all_items  # noqa: E402

_XDIST = ("shared/tests",)


def _boom():
    """A triage API that cannot be loaded at all - the lost-record path."""
    raise OSError("triage store unavailable")


def _race(unit_id="shared/tests"):
    return UnitResult(unit_id, PASS, 1, 1.0, "boom", race=True,
                      retry_kind=RETRY_SERIAL, serial_rc=0,
                      retry_cmd="uv run --with pytest pytest shared/tests -q")


def _run(monkeypatch, root, *results, exit_code=0, argv=()):
    """Drive main() with a stubbed suite; returns (rc, captured stdout)."""
    result = SuiteResult(list(results), exit_code, 12.0, _XDIST)
    monkeypatch.setattr(mod, "run_suite", lambda *a, **k: result)
    monkeypatch.setattr(mod, "source_fingerprint", lambda *a, **k: ("stable", ""))
    monkeypatch.setattr(sys, "argv",
                        ["run_test_suite.py", "--project-root", str(root), *argv])
    return mod.main()


def test_main_records_the_race_and_names_it_in_the_warning(tmp_path, monkeypatch,
                                                           capsys):
    rc = _run(monkeypatch, tmp_path, _race(),
              argv=["--run-id", "iterate-2026-07-27-f0-race-triage"])
    out = capsys.readouterr().out

    item, = read_all_items(tmp_path)
    assert item["source"] == "f0-suite"
    assert item["runId"] == "iterate-2026-07-27-f0-race-triage"
    # AC7: the handle is IN the warning, so persistence provably preceded reporting.
    assert f"Tracked as {item['id']}" in out
    assert "WARNING: unit(s) passed only on a retry" in out
    # AC8: a recorded race does not change the verdict.
    assert rc == 0


def test_a_green_run_that_could_not_record_the_race_exits_three(tmp_path, monkeypatch,
                                                                capsys):
    monkeypatch.setattr(race_mod, "_load_triage", _boom)

    rc = _run(monkeypatch, tmp_path, _race())

    assert rc == 3, "a green suite must not pass with the observation written nowhere"
    assert "*** FAILED TO RECORD" in capsys.readouterr().out


def test_a_red_run_keeps_its_own_exit_code(tmp_path, monkeypatch, capsys):
    """rc 3 exists to stop a GREEN run passing silently. A red run already STOPs, and
    relabelling it would misdescribe its dominant fact - both are non-zero anyway."""
    monkeypatch.setattr(race_mod, "_load_triage", _boom)

    rc = _run(monkeypatch, tmp_path, _race(),
              UnitResult("integration-tests", TEST_FAILURE, 1, 2.0, "red"),
              exit_code=1)

    assert rc == 1
    assert "*** FAILED TO RECORD" in capsys.readouterr().out, \
        "the lost record must still be shouted about, even on a red run"


def test_a_red_sibling_never_skips_the_recording(tmp_path, monkeypatch):
    """Recording runs before ANY return, so an unrelated failure cannot swallow it."""
    rc = _run(monkeypatch, tmp_path, _race(),
              UnitResult("integration-tests", TEST_FAILURE, 1, 2.0, "red"),
              exit_code=1)

    assert rc == 1
    assert [i["dedupKey"] for i in read_all_items(tmp_path)] == ["f0-race:shared/tests"]


def test_an_infra_retry_is_not_filed_end_to_end(tmp_path, monkeypatch, capsys):
    """AC9 through the real wiring: a transient infra fault recovers loudly but is
    NOT tracked. Only main() can prove the classification survives the CLI path."""
    rc = _run(monkeypatch, tmp_path,
              UnitResult("integration-tests", PASS, 2, 1.0, "", race=True,
                         retry_kind=RETRY_INFRA, serial_rc=0))

    assert rc == 0
    assert not (tmp_path / ".shipwright").exists(), "infra noise must not open a card"
    assert "did NOT reproduce" in capsys.readouterr().out


def test_the_recorded_parallel_command_targets_the_run_root(tmp_path, monkeypatch):
    """The CTA must name the tree F0 actually ran, not a hard-coded `.`."""
    _run(monkeypatch, tmp_path, _race(), argv=["--run-id", "iterate-y"])

    payload = read_all_items(tmp_path)[0]["launchPayload"]
    assert str(tmp_path) in payload and "--run-id iterate-y" in payload


def test_a_clean_run_writes_nothing_and_keeps_exit_zero(tmp_path, monkeypatch, capsys):
    rc = _run(monkeypatch, tmp_path, UnitResult("shared/tests", PASS, 0, 1.0))

    assert rc == 0
    assert not (tmp_path / ".shipwright").exists(), \
        "no race, no card - the producer must not touch the store"
    assert "WARNING" not in capsys.readouterr().out


def test_the_summary_still_prints_after_the_refactor(tmp_path, monkeypatch, capsys):
    _run(monkeypatch, tmp_path, UnitResult("shared/tests", PASS, 0, 3.0))
    out = capsys.readouterr().out
    assert "PASS " in out and "F0 suite: 1 units in" in out and "-> GREEN" in out


def test_a_config_error_still_exits_two_without_touching_the_store(tmp_path,
                                                                  monkeypatch):
    def _refuse(*a, **k):
        raise mod.SuiteConfigError("no test units discovered")

    monkeypatch.setattr(mod, "run_suite", _refuse)
    monkeypatch.setattr(sys, "argv",
                        ["run_test_suite.py", "--project-root", str(tmp_path)])
    assert mod.main() == 2
    assert not (tmp_path / ".shipwright").exists()


def test_run_id_is_optional_and_its_absence_is_recorded_as_absent(tmp_path,
                                                                  monkeypatch):
    """The flag is additive - F0 in an adopted project may not pass one - and a
    missing run id must be a null field, never a placeholder that reads as real."""
    assert _run(monkeypatch, tmp_path, _race()) == 0

    item, = read_all_items(tmp_path)
    assert item["runId"] is None and item["dedupKey"] == "f0-race:shared/tests"
