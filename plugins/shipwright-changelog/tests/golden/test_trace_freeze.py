"""The trace freeze (programme P9) and the driver interface smoke test.

Before the operator's stop 2 there is no lock: the harness is "unfrozen" and this file only
proves the check works. Stop 2's iterate commits ``golden.lock.json`` (path -> sha256 of the
frozen ``golden_trace.py``, every ``*.trace.json`` and every REQUIRED file), ``promise.lock.json``
(``path::test`` -> AC ids + fingerprint of every promise test) and an empty
``approved_deltas.json``, all written by ``shared/testkit/golden_lock.py``; from then on a diff
to a frozen file fails here unless a delta names exactly that change, and a promise test that
moved fails the promise-lock check. Known limit: deleting the lock reads as "unfrozen"; the stop-2
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


pytestmark = pytest.mark.covers_none("tooling")  # the freeze checker of the golden-trace harness: proves no product requirement (infrastructure class, shared/config/infra_test_paths.json)
import golden_lock as gl
import golden_trace as gt
from .conftest import DELTAS_PATH, GOLDEN_DIR, LOCK_PATH, REPO_ROOT, STEPS

TRACE_SUFFIX = ".trace.json"
HARNESS = "shared/testkit/golden_trace.py"
# What shapes every trace besides the trace files: a lock that leaves one out is refused. P2b added the replay
# driver and its command table, P2b2 the second half of the scenarios, the coverage checks and the seeded regressions; P2p added the promise tests and the hashing helper; the promise-hash hardening adds the lock's two modules, their tests and the conftests above the golden root; P2-op adds the pinned prose copy, the promise lock and the lock writer with its tests.
REQUIRED = (HARNESS, "shared/testkit/gh_stub.py", "shared/testkit/release_scratch.py",
            "plugins/shipwright-changelog/tests/golden/conftest.py",
            "plugins/shipwright-changelog/tests/golden/driver_replay.py",
            "plugins/shipwright-changelog/tests/golden/oracle.py",
            "plugins/shipwright-changelog/tests/golden/scenario_core.py",
            "plugins/shipwright-changelog/tests/golden/scenario_support.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_release.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_rerun.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_version.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_assets.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_branches.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_refusals.py",
            "plugins/shipwright-changelog/tests/golden/scenarios_modes.py",
            "plugins/shipwright-changelog/tests/golden/scenario_index.py",
            "plugins/shipwright-changelog/tests/golden/replay_commands.py",
            # P4 (fix list item 2): the CLI driver (prepare/aggregate since P3, steps 5.4-7 in P4) and the test that runs every scenario through it
            "plugins/shipwright-changelog/tests/golden/driver_cli.py",
            "plugins/shipwright-changelog/tests/golden/test_driver_cli.py",
            "plugins/shipwright-changelog/tests/golden/test_trace_freeze.py",
            # the tests that decide whether a trace is ever compared (deleting one would orphan its traces)
            "plugins/shipwright-changelog/tests/golden/test_scenarios_release.py",
            "plugins/shipwright-changelog/tests/golden/test_scenarios_aggregate.py",
            "plugins/shipwright-changelog/tests/golden/test_scenarios_assets.py",
            "plugins/shipwright-changelog/tests/golden/test_scenarios_branches.py",
            "plugins/shipwright-changelog/tests/golden/test_scenarios_refusals.py",
            "plugins/shipwright-changelog/tests/golden/test_scenarios_modes.py",
            "plugins/shipwright-changelog/tests/golden/test_scenario_index.py",
            "plugins/shipwright-changelog/tests/golden/test_seeded_regressions.py",
            "plugins/shipwright-changelog/tests/golden/test_replay_driver.py",
            # P2p: the promise tests and the checks over the promise list and the judgement scenarios, and the lock's hashing
            "plugins/shipwright-changelog/tests/golden/test_promise_aggregate.py",
            "plugins/shipwright-changelog/tests/golden/test_promise_release.py",
            "plugins/shipwright-changelog/tests/golden/test_promises_meta.py",
            "shared/testkit/promise_hash.py", "shared/testkit/promise_lock.py",
            "shared/tests/test_promise_hash.py", "shared/tests/test_promise_hash_hardening.py",
            # what pytest applies to every promise test without the test naming it: the parent conftests (an autouse fixture or a
            # pytest_* hook there), the root conftest and the package markers. Frozen here instead of hashed into every closure. Known cost: once the lock exists, any edit of these files (the root conftest too) needs an approved delta.
            "conftest.py", "plugins/shipwright-changelog/tests/conftest.py",
            "plugins/shipwright-changelog/tests/__init__.py", "plugins/shipwright-changelog/tests/golden/__init__.py",
            # P2-op (stop 2): the lock writer and its tests, the promise lock it writes, and the pinned prose P8b reads
            "shared/testkit/golden_lock.py", "shared/tests/test_golden_driver_freeze.py",
            "plugins/shipwright-changelog/tests/golden/promise.lock.json",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/SKILL.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/bullet-folding.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/changelog-format.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/compliance-evidence.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/conventional-commits.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/event-fold.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/first-actions.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/manifest-sync.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/release-notes-prompt.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/release-workflow.md.pin",
            "plugins/shipwright-changelog/tests/golden/pinned_prose/references/rerunning-a-release.md.pin",
            # stop-2 follow-up: the pytest config that decides whether this file runs at all (addopts, testpaths, markers;
            # pytest roots the changelog tests here, never at the repo-root pyproject), and the live skill prose until P5
            # thins it. Known cost: a later edit of either (P5, P8) needs an approved delta or a --repin.
            "plugins/shipwright-changelog/pyproject.toml",
            "plugins/shipwright-changelog/skills/changelog/SKILL.md",
            "plugins/shipwright-changelog/skills/changelog/references/bullet-folding.md",
            "plugins/shipwright-changelog/skills/changelog/references/changelog-format.md",
            "plugins/shipwright-changelog/skills/changelog/references/compliance-evidence.md",
            "plugins/shipwright-changelog/skills/changelog/references/conventional-commits.md",
            "plugins/shipwright-changelog/skills/changelog/references/event-fold.md",
            "plugins/shipwright-changelog/skills/changelog/references/first-actions.md",
            "plugins/shipwright-changelog/skills/changelog/references/manifest-sync.md",
            "plugins/shipwright-changelog/skills/changelog/references/release-notes-prompt.md",
            "plugins/shipwright-changelog/skills/changelog/references/release-workflow.md",
            "plugins/shipwright-changelog/skills/changelog/references/rerunning-a-release.md")
LIVE_PROSE = "plugins/shipwright-changelog/skills/changelog"
SPEC = REPO_ROOT / gl.DEFAULT_SPEC


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
    assert LOCK_PATH.name == gl.GOLDEN_LOCK and gl.PROMISE_LOCK in {Path(r).name for r in REQUIRED}


@pytest.mark.covers_none("tooling")
def test_the_promise_lock_holds_once_the_tree_is_frozen():
    """A promise test whose assertions, helpers, fixtures or AC ids moved since the freeze fails here (stale lock), and
    the lock writer's own check (``golden_lock.py --check``: exact file set, deltas honoured) agrees with this file."""
    if LOCK_PATH.is_file():
        assert gl.promise_lock_problems(REPO_ROOT, GOLDEN_DIR, SPEC) == []
        assert gl.freeze_problems(REPO_ROOT, GOLDEN_DIR, Path(__file__), SPEC) == []


@pytest.mark.covers_none("tooling")
def test_the_lock_writer_reads_this_files_required_list_as_it_stands():
    assert gl.required_files(Path(__file__)) == list(REQUIRED)
    assert HARNESS == gl.HARNESS and Path(__file__).name == gl.FREEZE_TEST


@pytest.mark.covers_none("tooling")
def test_every_pinned_prose_file_is_frozen():
    pinned = {p.relative_to(REPO_ROOT).as_posix() for p in (GOLDEN_DIR / "pinned_prose").rglob("*") if p.is_file()}
    assert pinned and pinned <= set(REQUIRED), sorted(pinned - set(REQUIRED))


@pytest.mark.covers_none("tooling")
def test_every_live_prose_file_is_frozen_until_p5():
    live = {p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / LIVE_PROSE).rglob("*") if p.is_file()}
    assert f"{LIVE_PROSE}/SKILL.md" in live and live <= set(REQUIRED), sorted(live - set(REQUIRED))


@pytest.mark.covers_none("tooling")
def test_the_pytest_config_this_session_runs_under_is_frozen(pytestconfig):
    """Whatever config file decided this session's addopts, testpaths and markers is in the lock, so an edit of it is a
    delta. Limit: a NEW ini file or plugin-root conftest that deselects this very file switches this check off with it
    (accepted residual risk; P7's junit reader closes it)."""
    inipath, root = pytestconfig.inipath, REPO_ROOT.resolve()
    assert inipath is not None and root in inipath.resolve().parents, f"pytest config outside the repo: {inipath}"
    assert inipath.resolve().relative_to(root).as_posix() in REQUIRED


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


@pytest.mark.covers_none("tooling")
@pytest.mark.parametrize("rel", ["plugins/shipwright-changelog/skills/changelog/SKILL.md",
                                 "plugins/shipwright-changelog/skills/changelog/references/release-workflow.md",
                                 "plugins/shipwright-changelog/pyproject.toml"])
def test_an_edit_of_the_live_prose_or_the_pytest_config_fails_unless_a_delta_names_it(tmp_path, rel):
    root, golden = make_tree(tmp_path)
    before = gt.file_sha256(root / rel)
    (root / rel).write_text("x = 1\nedited after the freeze\n", encoding="utf-8")
    assert any(p.startswith(f"{rel}: changed") for p in tree_problems(root, golden)), tree_problems(root, golden)
    delta = {"scenario": rel, "field": "sha256", "before": before, "after": gt.file_sha256(root / rel),
             "approver": "operator", "date": "2026-11-23"}
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
