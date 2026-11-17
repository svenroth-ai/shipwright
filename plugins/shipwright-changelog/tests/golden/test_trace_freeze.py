"""The trace freeze (programme P9) and the driver interface smoke test.

Before the operator's stop 2 there is no lock: the harness is "unfrozen" and this file only
proves the check works. Stop 2's iterate commits ``golden.lock.json`` (path -> sha256 of the
frozen ``golden_trace.py`` and every ``*.trace.json``) and, only when needed, an
``approved_deltas.json`` list; from then on a diff to a frozen file fails here unless a delta
names exactly that change. Known limit: deleting the lock reads as "unfrozen"; the stop-2
iterate also pins its existence in review, because a test cannot tell a deletion from a start.
Residual risk, accepted here and handed to the operator procedure: a diff may re-pin a trace and its
hash together, or write an approved delta with any approver string; only review (a sensitive-path rule or
CODEOWNERS) stops that, a test in this file cannot. That review must cover ALL the REQUIRED files below -
this checker (``test_trace_freeze.py``) included, not only the lock and the deltas: the checker also
guards itself only by being in the list, so an edit that weakens it and re-pins its own hash passes it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (programme P2a); the gate refuses removing it (tag-removed), see the P2b1 FINDINGS note
import golden_trace as gt
from .conftest import DELTAS_PATH, GOLDEN_DIR, LOCK_PATH, REPO_ROOT, STEPS

TRACE_SUFFIX = ".trace.json"
HARNESS = "shared/testkit/golden_trace.py"
# What shapes every trace besides the trace files: a lock that leaves one out is refused. P2b added the replay
# driver and its command table; P2-op adds the pinned prose copy and the promise lock to this list.
REQUIRED = (HARNESS, "shared/testkit/gh_stub.py", "shared/testkit/release_scratch.py",
            "plugins/shipwright-changelog/tests/golden/conftest.py",
            "plugins/shipwright-changelog/tests/golden/driver_replay.py",
            "plugins/shipwright-changelog/tests/golden/oracle.py",
            "plugins/shipwright-changelog/tests/golden/scenario_core.py",
            "plugins/shipwright-changelog/tests/golden/scenario_support.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_release.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_rerun.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_version.py",
            "plugins/shipwright-changelog/tests/golden/replay_commands.py",
            "plugins/shipwright-changelog/tests/golden/test_trace_freeze.py")


def tree_problems(repo_root: Path, golden_dir: Path) -> list[str]:
    """Everything wrong with the freeze of ``golden_dir``; ``[]`` for an unfrozen tree or a clean frozen one."""
    lock_path, deltas_path = golden_dir / "golden.lock.json", golden_dir / "approved_deltas.json"
    if not lock_path.is_file():
        return []
    lock = json.loads(lock_path.read_text(encoding="utf-8")).get("files", {})
    deltas = json.loads(deltas_path.read_text(encoding="utf-8")) if deltas_path.is_file() else []
    problems = gt.freeze_problems(repo_root, lock, deltas)
    problems += [f"{rel}: the harness itself is not frozen" for rel in REQUIRED if rel not in lock]
    for trace in sorted(golden_dir.rglob(f"*{TRACE_SUFFIX}")):
        rel = trace.relative_to(repo_root).as_posix()
        if rel not in lock:
            problems.append(f"{rel}: a trace that is not in the lock (added after the freeze)")
    return problems


def test_the_real_tree_respects_the_freeze():
    assert tree_problems(REPO_ROOT, GOLDEN_DIR) == []


def test_the_lock_and_deltas_files_have_one_agreed_home():
    assert LOCK_PATH.parent == DELTAS_PATH.parent == GOLDEN_DIR


def make_tree(tmp_path: Path, *, frozen: bool = True) -> tuple[Path, Path]:
    golden = tmp_path / "plugins" / "p" / "golden"
    (tmp_path / "shared" / "testkit").mkdir(parents=True)
    golden.mkdir(parents=True)
    for rel in REQUIRED:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x = 1\n", encoding="utf-8")
    (golden / f"s1{TRACE_SUFFIX}").write_text("{}\n", encoding="utf-8")
    if frozen:
        rels = [*REQUIRED, f"plugins/p/golden/s1{TRACE_SUFFIX}"]
        lock = {"version": 1, "files": {r: gt.file_sha256(tmp_path / r) for r in rels}}
        (golden / "golden.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return tmp_path, golden


def test_an_unfrozen_tree_passes_whatever_it_holds(tmp_path):
    root, golden = make_tree(tmp_path, frozen=False)
    (golden / f"s2{TRACE_SUFFIX}").write_text("changing\n", encoding="utf-8")
    assert tree_problems(root, golden) == []


def test_a_frozen_tree_that_is_untouched_passes(tmp_path):
    assert tree_problems(*make_tree(tmp_path)) == []


def test_a_changed_trace_after_the_freeze_fails(tmp_path):
    root, golden = make_tree(tmp_path)
    (golden / f"s1{TRACE_SUFFIX}").write_text('{"x": 1}\n', encoding="utf-8")
    assert any("s1.trace.json: changed" in p for p in tree_problems(root, golden))


def test_a_changed_harness_after_the_freeze_fails_unless_a_delta_names_it(tmp_path):
    root, golden = make_tree(tmp_path)
    before = json.loads((golden / "golden.lock.json").read_text(encoding="utf-8"))["files"][HARNESS]
    (root / HARNESS).write_text("x = 2\n", encoding="utf-8")
    assert tree_problems(root, golden)
    delta = {"scenario": HARNESS, "field": "sha256", "before": before, "after": gt.file_sha256(root / HARNESS),
             "approver": "operator", "date": "2026-11-17"}
    (golden / "approved_deltas.json").write_text(json.dumps([delta]), encoding="utf-8")
    assert tree_problems(root, golden) == []


def test_a_trace_added_after_the_freeze_fails(tmp_path):
    root, golden = make_tree(tmp_path)
    (golden / f"s2{TRACE_SUFFIX}").write_text("{}\n", encoding="utf-8")
    assert any("s2.trace.json: a trace that is not in the lock" in p for p in tree_problems(root, golden))


def test_a_lock_that_leaves_out_the_harness_fails(tmp_path):
    root, golden = make_tree(tmp_path)
    lock_path = golden / "golden.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    del lock["files"][HARNESS]
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert any("harness itself is not frozen" in p for p in tree_problems(root, golden))


class StatusDriver:
    """The smallest driver: it implements ``prepare`` by reading git, to prove the interface end to end."""
    name, steps = "status", frozenset({"prepare"})

    def run_step(self, step, scratch, **params):
        done = scratch.run(["git", "status", "--porcelain"])
        return gt.StepResult(step, done.returncode, {"status": "ok" if not done.stdout else "dirty"})


def test_the_step_list_is_ordered_unique_and_the_changelog_flow():
    assert len(set(STEPS)) == len(STEPS) and STEPS[0] == "prepare" and STEPS[-1] == "close-phase"
    assert STEPS.index("commit-and-tag") < STEPS.index("open-pr") < STEPS.index("push-tags")


def test_a_driver_runs_a_step_on_a_scratch_and_the_trace_records_it(scratch):
    results = gt.run_scenario(StatusDriver(), scratch, [("prepare", {})])
    trace = gt.collect(scratch, results)
    assert trace["steps"] == [{"step": "prepare", "exit_code": 0, "fields": {"status": "ok"}}]
    with pytest.raises(KeyError):
        gt.run_scenario(StatusDriver(), scratch, [("commit-and-tag", {})])


def test_a_scratch_can_pin_either_event_layout(events_layout, make_scratch):
    pinned = make_scratch(events_layout=events_layout)
    assert pinned.env["SHIPWRIGHT_EVENTS_LAYOUT"] == events_layout
    assert gt.collect(pinned)["refs"]["tags"].keys() == {"v0.1.0"}
