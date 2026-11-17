"""The driver interface and the freeze check of the golden-trace harness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (programme P2a)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "testkit"))

import golden_trace as gt  # noqa: E402


class Fake:
    def __init__(self, name: str, steps: set[str]):
        self.name, self.steps, self.calls = name, frozenset(steps), []

    def run_step(self, step, scratch, **params):
        self.calls.append((step, params))
        return gt.StepResult(step, 0, {"driver": self.name})


def test_run_scenario_runs_the_plan_in_order_with_its_params():
    d = Fake("replay", {"prepare", "aggregate"})
    results = gt.run_scenario(d, object(), [("prepare", {"mode": "guided"}), ("aggregate", {})])
    assert [r.step for r in results] == ["prepare", "aggregate"]
    assert d.calls == [("prepare", {"mode": "guided"}), ("aggregate", {})]


def test_an_unknown_step_is_an_error_not_a_skip():
    d = Fake("replay", {"prepare"})
    with pytest.raises(KeyError, match="sync"):
        gt.run_scenario(d, object(), [("prepare", {}), ("sync", {})])
    assert d.calls == []  # nothing ran before the plan was refused


def test_a_composite_sends_each_step_to_the_driver_that_owns_it():
    replay, cli = Fake("replay", {"prepare", "aggregate", "sync"}), Fake("cli", {"prepare", "aggregate"})
    both = gt.CompositeDriver(cli, replay)
    results = gt.run_scenario(both, object(), [("prepare", {}), ("sync", {})])
    assert [r.output["driver"] for r in results] == ["cli", "replay"]
    assert both.name == "cli+replay" and both.steps == {"prepare", "aggregate", "sync"}


def freeze_tree(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "s1.trace.json").write_text('{"a": 1}\n', encoding="utf-8")
    (tmp_path / "golden_trace.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path, {rel: gt.file_sha256(tmp_path / rel) for rel in ("t/s1.trace.json", "golden_trace.py")}


def test_an_untouched_tree_has_no_freeze_problem(tmp_path):
    root, lock = freeze_tree(tmp_path)
    assert gt.freeze_problems(root, lock, []) == []


def test_the_hash_ignores_line_endings(tmp_path):
    root, lock = freeze_tree(tmp_path)
    (root / "golden_trace.py").write_bytes(b"x = 1\r\n")
    assert gt.freeze_problems(root, lock, []) == []


def test_a_changed_or_missing_frozen_file_is_reported(tmp_path):
    root, lock = freeze_tree(tmp_path)
    (root / "t" / "s1.trace.json").write_text('{"a": 2}\n', encoding="utf-8")
    (root / "golden_trace.py").unlink()
    problems = gt.freeze_problems(root, lock, [])
    assert any("s1.trace.json: changed since the freeze" in p for p in problems)
    assert any("golden_trace.py: frozen file is missing" in p for p in problems)


def delta(rel: str, lock: dict[str, str], root: Path, **over) -> dict:
    entry = {"scenario": rel, "field": "sha256", "before": lock[rel], "after": gt.file_sha256(root / rel),
             "approver": "operator", "date": "2026-11-17"}
    return {**entry, **over}


def test_a_change_covered_by_an_approved_delta_passes(tmp_path):
    root, lock = freeze_tree(tmp_path)
    (root / "golden_trace.py").write_text("x = 2\n", encoding="utf-8")
    assert gt.freeze_problems(root, lock, [delta("golden_trace.py", lock, root)]) == []


@pytest.mark.parametrize("over", [{"after": "0" * 64}, {"before": "0" * 64}, {"approver": ""}, {"date": ""},
                                  {"field": "notes"}, {"scenario": "t/s1.trace.json"}])
def test_a_delta_that_does_not_name_exactly_this_change_does_not_cover_it(tmp_path, over):
    root, lock = freeze_tree(tmp_path)
    (root / "golden_trace.py").write_text("x = 2\n", encoding="utf-8")
    assert gt.freeze_problems(root, lock, [delta("golden_trace.py", lock, root, **over)])
