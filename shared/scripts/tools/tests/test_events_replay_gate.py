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
    monkeypatch.setattr(gate, "preflight", lambda repo: None)
    monkeypatch.setattr(gate, "_plans", lambda repo, only: [object()])
    monkeypatch.setattr(gate, "run_root", lambda plan, timeout: {
        "root": "shared/tests", "files": state["files"], "seconds": 1.0,
        "drops_failed": list(state["failing"]), "baseline_failed": []})
    monkeypatch.setattr(gate, "base_known", lambda repo: ("absent", None))
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
    monkeypatch.setattr(gate, "base_known", lambda repo: ("ok", {"budget_seconds": 100, "known": {"a::t": {}}}))
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


def test_budget_cannot_be_switched_off():
    base = {"budget_seconds": 100, "known": {}}
    assert gate.ratchet_violations({"budget_seconds": 0, "known": {}}, base)
    assert gate.ratchet_violations({"known": {}}, base)


def test_unresolvable_base_fails_in_ci_only(tmp_path, known_file, fake_run, monkeypatch):
    _write(known_file, [])
    monkeypatch.setattr(gate, "base_known", lambda repo: ("unresolved", None))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert _main(tmp_path) == 0
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert _main(tmp_path) == 1


def test_fail_line_keeps_ids_with_spaces():
    m = gate._FAIL_LINE.match("FAILED shared/tests/test_x.py::test_y[hello world] - assert 1 == 2")
    assert m.group(1) == "shared/tests/test_x.py::test_y[hello world]"


class _Proc:
    def __init__(self, rc, out):
        self.returncode, self.stdout = rc, out


class _Plan:
    base = ""
    marker_expr = None
    cwd = Path(".")
    pytest_arg = "shared/tests"
    rel_root = "shared/tests"


def test_run_is_fail_closed(monkeypatch):
    def fake(rc, out):
        monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: _Proc(rc, out))
        return gate._run(_Plan, [], {}, 10)[0]
    assert fake(0, "") == set()
    assert fake(1, "FAILED a.py::t - x") == {"a.py::t"}
    assert any("pytest-exit-1" in n for n in fake(1, "no summary lines"))
    assert any("pytest-exit-2" in n for n in fake(2, "FAILED a.py::t"))

    def boom(*a, **k):
        raise gate.subprocess.TimeoutExpired("pytest", 1)
    monkeypatch.setattr(gate.subprocess, "run", boom)
    assert any("pytest-timeout" in n for n in gate._run(_Plan, [], {}, 1)[0])


def test_baseline_failures_never_hide_collection_errors_and_do_not_make_known_entries_stale(
        tmp_path, known_file, monkeypatch):
    _write(known_file, ["a.py::known"])
    monkeypatch.setattr(gate, "preflight", lambda repo: None)
    monkeypatch.setattr(gate, "_plans", lambda repo, only: [_Plan])
    monkeypatch.setattr(gate, "base_known", lambda repo: ("absent", None))
    monkeypatch.setattr(gate, "select_files", lambda plan: [Path("a.py")])
    calls = []

    def fake_run(plan, args, env, timeout):
        calls.append(env["SHIPWRIGHT_EVENTS_LAYOUT"])
        if env["SHIPWRIGHT_EVENTS_LAYOUT"] == "drops":
            return {"a.py::known", "b.py"}, ""      # `b.py` = collection error (no ::)
        return {"a.py::known"}, ""                   # fails under legacy too
    monkeypatch.setattr(gate, "_run", fake_run)
    monkeypatch.setattr(gate, "_global_id", lambda plan, n: n)
    # the collection error stays a (new) failure; the known entry that also fails under
    # legacy is a platform failure -- neither stale nor new.
    assert _main(tmp_path, "--strict-stale") == 1
    assert calls == ["drops", "legacy"]


def test_budget_may_rise_only_with_a_reason():
    base = {"budget_seconds": 100, "known": {}}
    assert gate.ratchet_violations({"budget_seconds": 200, "known": {}}, base)
    assert gate.ratchet_violations({"budget_seconds": 200, "budget_reason": "  ", "known": {}}, base)
    assert gate.ratchet_violations({"budget_seconds": 200, "budget_reason": "more tests", "known": {}}, base) == []


def test_init_refuses_to_record_a_crashed_root(tmp_path, known_file, fake_run):
    fake_run["failing"] = ["shared/tests::<pytest-exit-2>"]
    assert _main(tmp_path, "init") == 2 and not known_file.exists()


def test_preflight_canary_passes_on_this_repo():
    assert gate.preflight(Path(__file__).resolve().parents[4]) is None
