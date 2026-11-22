"""The driver interface and the freeze check of the golden-trace harness."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers_none("tooling")  # a test of the golden-trace / promise-lock harness: proves no product requirement (infrastructure class, shared/config/infra_test_paths.json)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "testkit"))

import golden_lock as gl  # noqa: E402
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


# ---- the lock writer (shared/testkit/golden_lock.py) --------------------------------------------

PROMISE = '''import pytest


def _judge(x):
    assert x == 1


@pytest.mark.covers("FR-01.09/AC13")
def test_a(scratch):
    _judge(1)


@pytest.mark.covers("FR-01.09/AC02")
def test_b():
    _judge(1)
'''
FREEZE = 'HARNESS = "shared/testkit/golden_trace.py"\nREQUIRED = (HARNESS, "plugins/p/tests/golden/helper.py", "plugins/p/tests/golden/promise.lock.json")\n'
MOVES = "# Spec\n\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.09/AC13` | `FR-01.40/AC13` |\n"
REL = "plugins/p/tests/golden/"
GOLDEN_DIGEST = "4983e81dd2c5181bf128b56266e2e330f9e59754678181c3d5f0080883d7be7b"


def lock_tree(tmp_path: Path, freeze: str = FREEZE) -> tuple[Path, Path, Path]:
    golden = tmp_path / "plugins" / "p" / "tests" / "golden"
    (golden / "sub").mkdir(parents=True)
    (tmp_path / "shared" / "testkit").mkdir(parents=True)
    (tmp_path / gl.HARNESS).write_text("x = 1\n", encoding="utf-8")
    (golden / "helper.py").write_text("y = 1\n", encoding="utf-8")
    (golden / "S1.trace.json").write_text("{}\n", encoding="utf-8")
    (golden / "sub" / "S2.trace.json").write_text("{}\n", encoding="utf-8")
    (golden / "test_trace_freeze.py").write_text(freeze, encoding="utf-8")
    (golden / "test_promise_x.py").write_text(PROMISE, encoding="utf-8")
    (golden / "conftest.py").write_text("import pytest\n\n\n@pytest.fixture\ndef scratch():\n    return 1\n", encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(MOVES, encoding="utf-8")
    return tmp_path, golden, spec


def write_locks(root: Path, golden: Path, spec: Path, **kw) -> list[Path]:
    return gl.write(root, golden, golden / gl.FREEZE_TEST, spec, **kw)


def locks(golden: Path) -> dict[str, bytes]:
    return {n: (golden / n).read_bytes() for n in (gl.GOLDEN_LOCK, gl.PROMISE_LOCK)}


@pytest.mark.covers_none("tooling")
def test_the_writer_locks_every_trace_every_required_file_and_the_harness_and_the_freeze_holds(tmp_path):
    root, golden, spec = lock_tree(tmp_path)
    assert {p.name for p in write_locks(root, golden, spec)} == {gl.GOLDEN_LOCK, gl.PROMISE_LOCK}
    files = json.loads((golden / gl.GOLDEN_LOCK).read_text(encoding="utf-8"))["files"]
    assert set(files) == {gl.HARNESS, REL + "helper.py", REL + "promise.lock.json", REL + "S1.trace.json", REL + "sub/S2.trace.json"}
    assert gl.freeze_problems(root, golden, golden / gl.FREEZE_TEST, spec) == []
    promises = json.loads((golden / gl.PROMISE_LOCK).read_text(encoding="utf-8"))
    assert promises["version"] == 1 and set(promises["promises"]) == {REL + "test_promise_x.py::test_a", REL + "test_promise_x.py::test_b"}
    assert promises["promises"][REL + "test_promise_x.py::test_a"]["acs"] == ["FR-01.40/AC13"]  # resolved through the move map


@pytest.mark.covers_none("tooling")
def test_the_harness_is_locked_even_when_required_does_not_name_it(tmp_path):
    root, golden, spec = lock_tree(tmp_path, FREEZE.replace("HARNESS, ", ""))
    write_locks(root, golden, spec)
    assert gl.HARNESS in json.loads((golden / gl.GOLDEN_LOCK).read_text(encoding="utf-8"))["files"]


@pytest.mark.covers_none("tooling")
def test_the_lock_bytes_are_pinned_lf_and_a_crlf_checkout_of_a_lock_or_a_hashed_file_changes_nothing(tmp_path):
    root, golden, spec = lock_tree(tmp_path)
    write_locks(root, golden, spec)
    first = locks(golden)
    assert all(b"\r\n" not in data and data.endswith(b"}\n") for data in first.values())
    # a literal digest: a change of key order, indent or newline (the byte-stable promise) moves it (3.11 = 3.12 = 3.13)
    assert hashlib.sha256(first[gl.GOLDEN_LOCK]).hexdigest() == GOLDEN_DIGEST
    (golden / "helper.py").write_bytes(b"y = 1\r\n")
    for name, data in first.items():  # what git's autocrlf leaves in a Windows checkout
        (golden / name).write_bytes(data.replace(b"\n", b"\r\n"))
    assert write_locks(root, golden, spec) == [] and gl.main(["--repo-root", str(root), "--spec", "spec.md", "--plugin", "p", "--check"]) == 0


@pytest.mark.covers_none("tooling")
def test_a_changed_promise_test_makes_the_promise_lock_stale(tmp_path):
    root, golden, spec = lock_tree(tmp_path)
    write_locks(root, golden, spec)
    (golden / "test_promise_x.py").write_text(PROMISE.replace("assert x == 1", "assert x >= 1"), encoding="utf-8")
    problems = gl.promise_lock_problems(root, golden, spec)
    assert len(problems) == 2 and all("promise differs from the lock" in p for p in problems)  # the helper is in both closures
    (golden / gl.PROMISE_LOCK).unlink()
    assert any("promise lock is missing" in p for p in gl.promise_lock_problems(root, golden, spec))


@pytest.mark.covers_none("tooling")
def test_an_existing_lock_that_would_change_is_refused_without_repin_and_nothing_is_written(tmp_path):
    root, golden, spec = lock_tree(tmp_path)
    write_locks(root, golden, spec)
    before = locks(golden)
    (golden / "S1.trace.json").write_text('{"changed": 1}\n', encoding="utf-8")
    with pytest.raises(gl.LockError, match="--repin"):
        write_locks(root, golden, spec)
    assert locks(golden) == before
    assert [p.name for p in write_locks(root, golden, spec, repin=True)] == [gl.GOLDEN_LOCK]


@pytest.mark.covers_none("tooling")
def test_check_honours_an_approved_delta_like_the_freeze_test_and_writes_nothing(tmp_path, capsys):
    root, golden, spec = lock_tree(tmp_path)
    write_locks(root, golden, spec)
    args = ["--repo-root", str(root), "--spec", "spec.md", "--plugin", "p", "--check"]
    before, trace = locks(golden), golden / "S1.trace.json"
    locked = json.loads(before[gl.GOLDEN_LOCK])["files"][REL + "S1.trace.json"]
    trace.write_text('{"changed": 1}\n', encoding="utf-8")
    assert gl.main(args) == 1 and locks(golden) == before
    assert "S1.trace.json: changed since the freeze" in capsys.readouterr().out
    delta = {"scenario": REL + "S1.trace.json", "field": "sha256", "before": locked, "after": gt.file_sha256(trace),
             "approver": "operator", "date": "2026-11-23"}
    (golden / gl.DELTAS).write_text(json.dumps([delta]), encoding="utf-8")
    assert gl.main(args) == 0
    (golden / "S3.trace.json").write_text("{}\n", encoding="utf-8")  # a trace added after the freeze
    assert gl.main(args) == 1 and "should be in the golden lock" in capsys.readouterr().out


@pytest.mark.covers_none("tooling")
def test_promise_only_rewrites_the_promise_lock_alone_and_names_the_delta_the_golden_lock_needs(tmp_path, capsys):
    root, golden, spec = lock_tree(tmp_path)
    write_locks(root, golden, spec)
    golden_before = (golden / gl.GOLDEN_LOCK).read_bytes()
    (golden / "test_promise_x.py").write_text(PROMISE.replace("assert x == 1", "assert x >= 1"), encoding="utf-8")
    args = ["--repo-root", str(root), "--spec", "spec.md", "--plugin", "p"]
    assert gl.main([*args, "--promise-only"]) == 2  # an existing lock changes only with --repin
    capsys.readouterr()
    assert gl.main([*args, "--promise-only", "--repin"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["written"] == [REL + gl.PROMISE_LOCK] and (golden / gl.GOLDEN_LOCK).read_bytes() == golden_before
    sha = report["promise_lock_sha256"]
    assert sha["after"] == gt.file_sha256(golden / gl.PROMISE_LOCK) != sha["before"]
    delta = {"scenario": REL + gl.PROMISE_LOCK, "field": "sha256", **sha, "approver": "operator", "date": "2026-11-23"}
    (golden / gl.DELTAS).write_text(json.dumps([delta]), encoding="utf-8")
    assert gl.freeze_problems(root, golden, golden / gl.FREEZE_TEST, spec) == []
    # a second promise change: the delta still starts from what the golden lock holds, not from the first delta's file
    (golden / "test_promise_x.py").write_text(PROMISE.replace("assert x == 1", "assert x > 0"), encoding="utf-8")
    assert gl.main([*args, "--promise-only", "--repin"]) == 0
    second = json.loads(capsys.readouterr().out)["promise_lock_sha256"]
    assert second["before"] == sha["before"]
    (golden / gl.DELTAS).write_text(json.dumps([{**delta, **second}]), encoding="utf-8")
    assert gl.freeze_problems(root, golden, golden / gl.FREEZE_TEST, spec) == []


@pytest.mark.covers_none("tooling")
def test_a_full_repin_reports_the_deltas_it_makes_moot(tmp_path, capsys):
    root, golden, spec = lock_tree(tmp_path)
    write_locks(root, golden, spec)
    (golden / gl.DELTAS).write_text('[{"scenario": "x"}]', encoding="utf-8")
    (golden / "S1.trace.json").write_text('{"changed": 1}\n', encoding="utf-8")
    assert gl.main(["--repo-root", str(root), "--spec", "spec.md", "--plugin", "p", "--repin"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["repinned"] == [REL + gl.GOLDEN_LOCK] and report["deltas_made_moot"] == 1
    assert report["entries"] == {"added": [], "removed": [], "changed": [REL + "S1.trace.json"]}  # what moved, per entry


@pytest.mark.covers_none("tooling")
def test_a_required_list_the_writer_cannot_read_is_refused_and_a_constant_after_it_is_fine(tmp_path):
    root, golden, spec = lock_tree(tmp_path)
    (golden / "helper.py").unlink()
    with pytest.raises(gl.LockError, match="helper.py: named for the lock but missing"):
        write_locks(root, golden, spec)
    freeze = golden / gl.FREEZE_TEST
    for source, message in (("REQUIRED = tuple(['a'])\n", "not a literal"), ("REQUIRED = (f'{1}',)\n", "not a string literal"),
                            ("REQUIRED: tuple = ('a',)\n", "annotated or extended"), ("REQUIRED = ('a',)\nREQUIRED += ('b',)\n", "annotated or extended"),
                            ("X = 1\n", "no module-level REQUIRED")):
        freeze.write_text(source, encoding="utf-8")
        with pytest.raises(gl.LockError, match=message):
            gl.required_files(freeze)
    freeze.write_text('REQUIRED = (LATER, "a")\nLATER = "b"\n', encoding="utf-8")
    assert gl.required_files(freeze) == ["b", "a"]


@pytest.mark.covers_none("tooling")
def test_the_cli_takes_the_golden_dir_or_the_plugin_and_refuses_a_missing_spec_or_a_bad_promise_test(tmp_path, capsys):
    root, golden, spec = lock_tree(tmp_path)
    args = ["--repo-root", str(root), "--spec", "spec.md"]
    assert gl.main([*args, "--check", "--plugin", "p"]) == 1  # no lock yet: the freeze does not hold, nothing written
    assert not (golden / gl.GOLDEN_LOCK).exists()
    capsys.readouterr()
    assert gl.main([*args, "--golden-dir", REL]) == 0  # relative to the repo root, not the working directory
    report = json.loads(capsys.readouterr().out)
    assert (report["files"], report["traces"], report["promises"]) == (5, 2, 2)
    assert gl.main([*args, "--check", "--plugin", "p"]) == 0
    assert gl.main([*args, "--plugin", "missing"]) == 2
    assert gl.main(["--repo-root", str(root), "--spec", "nospec.md", "--plugin", "p"]) == 2  # never an empty move map
    (golden / "test_promise_x.py").write_text(PROMISE.replace('@pytest.mark.covers("FR-01.09/AC02")\n', ""), encoding="utf-8")
    assert gl.main([*args, "--plugin", "p", "--repin"]) == 2 and "covers ids" in capsys.readouterr().err
