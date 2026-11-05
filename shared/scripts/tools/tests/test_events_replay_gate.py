"""Ratchet logic of the standing events replay gate (campaign events-drop-files, S0)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[1] / "events_replay_gate.py"
_spec = importlib.util.spec_from_file_location("_events_replay_gate_under_test", _TOOL)
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)


@pytest.fixture
def known_file(tmp_path, monkeypatch):
    path = tmp_path / "known.json"
    monkeypatch.setattr(gate, "KNOWN_PATH", path)
    return path


@pytest.fixture
def fake_run(monkeypatch):
    """Replace plan discovery + root execution; ``failing`` is the drops-only set."""
    state = {"failing": [], "files": 3}
    monkeypatch.setattr(gate, "_plans", lambda repo, only: [object()])
    monkeypatch.setattr(gate, "run_root", lambda plan, timeout: {
        "root": "shared/tests", "files": state["files"], "seconds": 1.0,
        "drops_failed": list(state["failing"]), "baseline_failed": []})
    monkeypatch.setattr(gate, "base_known", lambda repo: None)
    return state


def _write(path, known, budget=100):
    path.write_text(json.dumps({"schema": 1, "budget_seconds": budget,
                                "known": {k: {"unit": "S3"} for k in known}}), encoding="utf-8")


def _main(tmp_path, *extra):
    return gate.main(["--repo", str(tmp_path), *extra])


def test_classify_unit_splits_writers_from_readers():
    assert gate.classify_unit("shared/tests/test_finalize_iterate.py::t") == "S4"
    assert gate.classify_unit("shared/tests/test_record_event.py::t") == "S4"
    assert gate.classify_unit("shared/tests/test_iterate_ledger_anchor.py::t") == "S2"
    assert gate.classify_unit("shared/tests/test_compliance_input_state.py::t") == "S3"


def test_fail_line_parsing():
    m = gate._FAIL_LINE.match("FAILED shared/tests/test_x.py::test_y[a-b] - AssertionError: no")
    assert m and m.group(1) == "shared/tests/test_x.py::test_y[a-b]"
    assert gate._FAIL_LINE.match("ERROR shared/tests/test_x.py").group(1) == "shared/tests/test_x.py"
    assert gate._FAIL_LINE.match("PASSED shared/tests/test_x.py::t") is None


def test_check_passes_when_failures_equal_known(tmp_path, known_file, fake_run):
    _write(known_file, ["a::t"])
    fake_run["failing"] = ["a::t"]
    assert _main(tmp_path) == 0


def test_check_fails_on_a_new_failure(tmp_path, known_file, fake_run, capsys):
    _write(known_file, ["a::t"])
    fake_run["failing"] = ["a::t", "b::new"]
    assert _main(tmp_path) == 1
    assert "b::new" in capsys.readouterr().out


def test_stale_entry_is_a_note_unless_strict(tmp_path, known_file, fake_run):
    _write(known_file, ["a::t", "gone::t"])
    fake_run["failing"] = ["a::t"]
    assert _main(tmp_path) == 0
    assert _main(tmp_path, "--strict-stale") == 1


def test_tighten_only_deletes(tmp_path, known_file, fake_run):
    _write(known_file, ["a::t", "gone::t"])
    fake_run["failing"] = ["a::t", "brand::new"]
    assert _main(tmp_path, "tighten") == 1  # a new failure is still reported
    assert list(json.loads(known_file.read_text())["known"]) == ["a::t"]


def test_init_refuses_a_non_empty_set_and_records_an_empty_one(tmp_path, known_file, fake_run):
    _write(known_file, ["a::t"])
    assert _main(tmp_path, "init") == 2
    known_file.unlink()
    fake_run["failing"] = ["x::finalize_t"]
    assert _main(tmp_path, "init") == 0
    doc = json.loads(known_file.read_text())
    assert list(doc["known"]) == ["x::finalize_t"] and doc["budget_seconds"] >= 60


def test_budget_overrun_fails(tmp_path, known_file, fake_run, monkeypatch):
    _write(known_file, [], budget=5)
    ticks = iter([0.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(gate.time, "monotonic", lambda: next(ticks, 100.0))
    assert _main(tmp_path) == 1


def test_unreadable_known_file_is_an_error_not_empty(tmp_path, known_file, fake_run):
    known_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _main(tmp_path)
    assert "unreadable" in str(exc.value)


def test_ratchet_violations_against_the_merge_base():
    base = {"budget_seconds": 100, "known": {"a": {}}}
    assert gate.ratchet_violations({"budget_seconds": 90, "known": {"a": {}}}, base) == []
    assert gate.ratchet_violations({"budget_seconds": 100, "known": {}}, base) == []
    assert gate.ratchet_violations({"budget_seconds": 100, "known": {"a": {}, "b": {}}}, base)
    assert gate.ratchet_violations({"budget_seconds": 101, "known": {"a": {}}}, base)
    assert gate.ratchet_violations({"budget_seconds": 1, "known": {"zz": {}}}, None) == []


def test_check_fails_when_the_set_grew_since_the_merge_base(tmp_path, known_file, fake_run, monkeypatch):
    _write(known_file, ["a::t", "added::t"])
    fake_run["failing"] = ["a::t", "added::t"]
    monkeypatch.setattr(gate, "base_known", lambda repo: {"budget_seconds": 100, "known": {"a::t": {}}})
    assert _main(tmp_path) == 1


def test_global_id_prefixes_the_plugin_dir():
    class P:
        base = "plugins/shipwright-x"
    assert gate._global_id(P, "tests" + chr(92) + "test_a.py::t") == "plugins/shipwright-x/tests/test_a.py::t"


def test_pytest_cmd_keeps_each_roots_own_addopts():
    class P:
        base = "plugins/shipwright-grade"
        marker_expr = None
    cmd = gate._pytest_cmd(P, ["tests/test_a.py"])
    assert "addopts=" not in " ".join(cmd) and "-m" not in cmd
    class Q:
        base = ""
        marker_expr = "not slow and not cross_plugin"
    assert "-m" in gate._pytest_cmd(Q, [])
