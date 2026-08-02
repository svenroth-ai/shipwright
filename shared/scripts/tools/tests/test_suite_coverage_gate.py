"""F0 diff-coverage gate — the side-effecting halves.

Split from `test_suite_coverage.py` (pure argv builders + verdict). Everything here
touches the filesystem or shells out, yet stays drivable IN-PROCESS — `run_gate`
takes its `runner` as a parameter. That is load-bearing, not tidiness: this gate
scores changed lines by what tests EXECUTE, so a design testable only by shelling
out would red-flag its own diff.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.suite_coverage as coverage_mod
from scripts.tools.suite_coverage import (
    COVERAGE_XML,
    DATA_DIR,
    GATE_FAILED,
    GATE_PASSED,
    build_worktree_diff,
    compare_branch,
    coverage_run_lock,
    missing_data,
    prepare_coverage,
    run_gate,
    verdict,
)
from scripts.tools.suite_units import SuiteConfigError
from scripts.tools.suite_worktree_diff import source_fingerprint


# --------------------------------------------------------------------------- #
# compare-branch resolution
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path, branch: str = "main", *, commit: bool = True) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", branch)
    if commit:
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        (repo / "a.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "c")
    return repo


def _origin(repo: Path, branch: str = "main") -> Path:
    bare = repo.parent / "origin.git"
    _git(repo, "init", "-q", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    return bare


def test_compare_branch_uses_ci_origin_main_even_when_origin_HEAD_differs(tmp_path):
    """The local line set must not drift from the action when origin/HEAD differs."""
    repo = _repo(tmp_path, "trunk")
    _origin(repo)
    _git(repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    assert compare_branch(repo) == "origin/main"


def test_compare_branch_returns_origin_main_when_it_resolves(tmp_path):
    repo = _repo(tmp_path)
    _origin(repo)
    assert compare_branch(repo) == "origin/main"


def test_compare_branch_is_None_when_no_base_exists(tmp_path):
    assert compare_branch(_repo(tmp_path, commit=False)) is None


# --------------------------------------------------------------------------- #
# prepare_coverage — stale state must never look like a fresh measurement
# --------------------------------------------------------------------------- #
def _measurable(root: Path) -> Path:
    """A root that will actually measure — `prepare_coverage` deliberately leaves a
    project alone when instrumentation would short-circuit anyway."""
    (root / "pyproject.toml").write_text("[tool.coverage.run]\n", encoding="utf-8")
    return root


def test_prepare_clears_stale_state_and_returns_the_data_dir(tmp_path):
    _measurable(tmp_path)
    stale_dir = tmp_path / DATA_DIR
    stale_dir.mkdir()
    (stale_dir / ".coverage.old").write_text("junk", encoding="utf-8")
    (tmp_path / COVERAGE_XML).write_text("<coverage/>", encoding="utf-8")
    (tmp_path / ".coverage").write_text("junk", encoding="utf-8")

    data_dir = prepare_coverage(tmp_path)

    assert data_dir == tmp_path / DATA_DIR
    assert data_dir.is_dir()
    assert list(data_dir.iterdir()) == []
    assert not (tmp_path / COVERAGE_XML).exists()
    assert not (tmp_path / ".coverage").exists()


def test_prepare_is_safe_on_a_clean_tree(tmp_path):
    assert prepare_coverage(_measurable(tmp_path)).is_dir()


def test_prepare_leaves_a_project_it_will_never_measure_alone(tmp_path):
    """No root pyproject.toml means instrumentation short-circuits, so there is
    nothing to protect from staleness — deleting anyway would be pure downside."""
    keep = tmp_path / COVERAGE_XML
    keep.write_text("<coverage/>", encoding="utf-8")
    prepare_coverage(tmp_path)
    assert keep.exists()


def test_a_momentarily_held_file_is_retried_not_refused(tmp_path, monkeypatch):
    """An editor/indexer/antivirus holds a file briefly — the condition
    `atomic_write` already retries for. Refusing on the first failure would turn a
    self-healing transient into a hard STOP before a single test ran."""
    _measurable(tmp_path)
    (tmp_path / COVERAGE_XML).write_text("<coverage/>", encoding="utf-8")
    real_unlink, calls = Path.unlink, {"n": 0}

    def flaky(self, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("WinError 32: file in use")
        return real_unlink(self, **kw)

    monkeypatch.setattr(Path, "unlink", flaky)
    monkeypatch.setattr(coverage_mod.time, "sleep", lambda s: None)
    assert prepare_coverage(tmp_path).is_dir()
    assert not (tmp_path / COVERAGE_XML).exists()


# --------------------------------------------------------------------------- #
# run_gate — orchestration with an INJECTED runner (no subprocess)
# --------------------------------------------------------------------------- #
def _runner(*, combine_rc: int = 0, gate_rc: int = 0,
            gate_out: str = "out\n", raise_on: str | None = None):
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        if raise_on is not None and raise_on in " ".join(argv):
            raise OSError("uvx not found")
        if argv[0] != "uvx" and combine_rc == 0:
            # A real combine WRITES the report; the gate checks that this run did.
            output = Path(argv[argv.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("<coverage/>", encoding="utf-8")
        rc = gate_rc if argv[0] == "uvx" else combine_rc
        stdout = gate_out if argv[0] == "uvx" else "out\n"
        return subprocess.CompletedProcess(argv, rc, stdout=stdout, stderr="")

    return run, calls


def _data(root: Path, n: int) -> list[str]:
    """`n` instrumented units that each ACTUALLY wrote their data file, so a test
    about something else is not silently answered by the missing-data refusal."""
    d = root / DATA_DIR
    d.mkdir(exist_ok=True)
    out = []
    for i in range(n):
        f = d / f".coverage.u{i}"
        f.write_text("x", encoding="utf-8")
        out.append(str(f))
    return out


def _diff(root: Path) -> Path:
    path = root / DATA_DIR / "worktree.diff"
    path.parent.mkdir(exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_a_red_suite_skips_the_gate_entirely(tmp_path):
    """AC-5. Coverage measured from a suite that did not finish is not a verdict."""
    run, calls = _runner()
    res = run_gate(tmp_path, expected=_data(tmp_path, 3), suite_green=False,
                   branch="origin/main", diff_file=None, runner=run)
    assert calls == []
    assert res.exit_code == GATE_PASSED
    assert any("suite is red" in line for line in res.lines)


def test_run_gate_combines_then_gates(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", diff_file=_diff(tmp_path),
                   runner=run)
    assert [c[0] for c in calls] == ["uv", "uvx"]
    assert res.exit_code == GATE_PASSED


def test_run_gate_maps_a_below_threshold_exit_to_a_failure(tmp_path):
    run, _ = _runner(gate_rc=1, gate_out="Failure. Coverage is below 80%.\n")
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", diff_file=_diff(tmp_path),
                   runner=run)
    assert res.exit_code == GATE_FAILED
    assert any("Add tests" in line for line in res.lines)


def test_uvx_exit_one_without_diff_cover_verdict_is_infrastructure_failure(tmp_path):
    """The launcher can fail with rc=1 too; only diff-cover's pinned threshold
    message licenses the operator-facing advice to add tests."""
    run, _ = _runner(gate_rc=1, gate_out="uvx: package resolution failed\n")
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", diff_file=_diff(tmp_path),
                   runner=run)
    assert res.exit_code == GATE_FAILED
    assert any("diff-cover itself failed" in line for line in res.lines)
    assert not any("Add tests" in line for line in res.lines)


@pytest.mark.parametrize("raise_on", ["uvx", "combine_coverage"])
def test_a_missing_binary_is_a_closed_gate_not_a_traceback(tmp_path, raise_on):
    """AC-4c. `uvx` off PATH, or a resolution failure, must not crash F0 and must
    not pass — the operator gets an exit code and a phase name."""
    run, _ = _runner(raise_on=raise_on)
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", diff_file=_diff(tmp_path),
                   runner=run)
    assert res.exit_code == GATE_FAILED
    assert any(raise_on.split("_")[0] in line or "could not run" in line
               for line in res.lines)


def test_run_gate_does_not_gate_when_nothing_was_eligible(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path, expected=(), suite_green=True, branch="origin/main",
                   diff_file=None, runner=run)
    assert calls == []
    assert res.exit_code == GATE_PASSED


def test_run_gate_refuses_without_a_compare_branch(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch=None, diff_file=None, runner=run)
    assert calls == []
    assert res.exit_code == GATE_FAILED


# --------------------------------------------------------------------------- #
# missing_data — the last PASS-without-measurement path
# --------------------------------------------------------------------------- #
def test_a_unit_that_wrote_no_data_is_named_not_ignored(tmp_path):
    """`eligible` counts UNITS, the combiner counts DATA FILES — so a unit that
    produced nothing is invisible to both, and diff-cover drops its changed lines
    from the DENOMINATOR: a pass over what is left. Detected here instead."""
    expected = _data(tmp_path, 2)
    expected.append(str(tmp_path / DATA_DIR / ".coverage.ghost"))
    assert missing_data(expected) == [".coverage.ghost"]


def test_an_xdist_suffixed_data_file_counts_as_present(tmp_path):
    """pytest-cov appends `.<host>.<pid>.<rand>` under xdist; treating that as
    missing would fail-closed on every allowlisted unit — a false STOP on every run."""
    d = tmp_path / DATA_DIR
    d.mkdir()
    (d / ".coverage.shared.host.123.456").write_text("x", encoding="utf-8")
    assert missing_data([str(d / ".coverage.shared")]) == []


def test_the_gate_refuses_before_measuring_when_a_unit_wrote_nothing(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path,
                   expected=[str(tmp_path / DATA_DIR / ".coverage.ghost")],
                   suite_green=True, branch="origin/main", diff_file=_diff(tmp_path),
                   runner=run)
    assert res.exit_code == GATE_FAILED
    assert calls == [], "no point combining data that is not there"


# --------------------------------------------------------------------------- #
# prepare_coverage — a reset that did not happen must not look like one that did
# --------------------------------------------------------------------------- #
def test_stale_state_that_survives_the_reset_is_refused(tmp_path, monkeypatch):
    """A surviving coverage.xml is the quiet killer: `combine_coverage` exits 0 with
    status `n-a` WITHOUT overwriting the output, so the gate would then measure the
    previous run's report and could pass on it."""
    _measurable(tmp_path)
    (tmp_path / COVERAGE_XML).write_text("<coverage/>", encoding="utf-8")
    monkeypatch.setattr(Path, "unlink", lambda self, **k: None)
    monkeypatch.setattr(coverage_mod.time, "sleep", lambda s: None)
    with pytest.raises(SuiteConfigError, match="stale coverage state"):
        prepare_coverage(tmp_path)


def test_the_no_config_case_names_the_config_not_the_source_roots(tmp_path):
    """Two different causes reach `eligible == 0`; a message that asserts the wrong
    one sends the operator to look in the wrong place."""
    res = verdict(eligible=0, branch="origin/main", no_config=True)
    assert res.exit_code == GATE_PASSED
    assert "pyproject.toml" in " ".join(res.lines)


def test_a_coverage_xml_this_run_did_not_write_is_not_trusted(tmp_path):
    """Even a freshly written public XML is not this invocation's combine output."""
    (tmp_path / COVERAGE_XML).write_text("<coverage/>", encoding="utf-8")

    def run(argv, **kwargs):  # a combine that writes nothing, then a gate that passes
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    res = run_gate(tmp_path, expected=_data(tmp_path, 1), suite_green=True,
                   branch="origin/main", diff_file=_diff(tmp_path), runner=run)
    assert res.exit_code == GATE_FAILED
    assert any("no combined coverage.xml" in ln for ln in res.lines)


def test_a_dangling_origin_HEAD_falls_back_to_a_valid_origin_main(tmp_path):
    """A stale origin/HEAD cannot hide CI's valid, authoritative origin/main."""
    repo = _repo(tmp_path)
    _origin(repo)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    assert compare_branch(repo) == "origin/main"


def test_compare_branch_refreshes_a_stale_origin_main_before_using_it(tmp_path):
    repo = _repo(tmp_path)
    _origin(repo)
    old = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                         capture_output=True, text=True).stdout.strip()
    (repo / "a.txt").write_text("new", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "advance")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "update-ref", "refs/remotes/origin/main", old)
    assert compare_branch(repo) == "origin/main"
    refreshed = subprocess.run(
        ["git", "rev-parse", "refs/remotes/origin/main"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    assert refreshed == head


def test_a_second_f0_cannot_enter_the_coverage_critical_section(tmp_path):
    with coverage_run_lock(tmp_path):
        with pytest.raises(SuiteConfigError, match="another F0 may be running"):
            with coverage_run_lock(tmp_path):
                pytest.fail("the second lock must not be acquired")
    # The OS lock, unlike an O_EXCL sentinel, is released automatically/reusably.
    with coverage_run_lock(tmp_path):
        pass


def test_coverage_reset_preserves_the_held_lock_rendezvous(tmp_path):
    """Resettable coverage state must never contain the lock path. Unlinking a
    held Unix inode would let another process lock a newly-created path."""
    _measurable(tmp_path)
    lock_path = tmp_path / ".coverage.f0.lock"
    with coverage_run_lock(tmp_path):
        prepare_coverage(tmp_path)
        assert lock_path.is_file()
        with pytest.raises(SuiteConfigError, match="another F0 may be running"):
            with coverage_run_lock(tmp_path):
                pytest.fail("reset must not replace the held lock rendezvous")


def test_missing_merge_base_names_the_shallow_history_fix(
        tmp_path, monkeypatch):
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        monkeypatch.setenv(key, "hostile")

    def no_merge_base(argv, **kwargs):
        assert argv[:3] == ["git", "-C", str(tmp_path.resolve())]
        assert argv[3] == "merge-base"
        assert all(key not in kwargs["env"] for key in
                   ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"))
        assert kwargs["env"]["GIT_INDEX_FILE"].startswith(str(tmp_path.resolve()))
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="no base")

    diff_file, error = build_worktree_diff(
        tmp_path, "origin/main", runner=no_merge_base)
    assert diff_file is None
    assert "git fetch --deepen=100 origin main" in error


def test_git_being_unavailable_is_no_base_rather_than_a_crash(tmp_path):
    """`git` off PATH must reach the same fail-closed refusal as a missing ref. An
    OSError escaping here would be a traceback out of F0 from the one helper whose
    documented contract is to return None."""
    def boom(*a, **k):
        raise OSError("git not found")

    assert compare_branch(tmp_path, runner=boom) is None


def test_compare_fetch_cannot_prompt_or_wait_without_a_bound(
        tmp_path, monkeypatch):
    seen = {}
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        monkeypatch.setenv(key, "hostile")

    def refuse(argv, **kwargs):
        seen.update(argv=argv, kwargs=kwargs)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="auth")

    assert compare_branch(tmp_path, runner=refuse) is None
    assert seen["argv"] == ["git", "-C", str(tmp_path.resolve()), "fetch",
                            "--no-tags", "origin", "main"]
    assert seen["kwargs"]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert all(key not in seen["kwargs"]["env"] for key in
               ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"))
    assert seen["kwargs"]["timeout"] == 120


def test_source_fingerprint_hashes_existing_source_and_root_config(tmp_path):
    repo = _repo(tmp_path)
    source = repo / "source.py"
    config = repo / "pyproject.toml"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    config.write_text("[tool.coverage.run]\n", encoding="utf-8")
    _git(repo, "add", "source.py", "pyproject.toml")
    _git(repo, "commit", "-qm", "add measured inputs")
    before, error = source_fingerprint(repo)
    assert before is not None, error
    source.write_text("VALUE = 2\n", encoding="utf-8")
    after, error = source_fingerprint(repo)
    assert after is not None, error
    assert after != before
    source.write_text("VALUE = 1\n", encoding="utf-8")
    config.write_text("[tool.coverage.run]\nbranch = true\n", encoding="utf-8")
    config_after, error = source_fingerprint(repo)
    assert config_after is not None, error
    assert config_after != before
    config.write_text("[tool.coverage.run]\n", encoding="utf-8")
    (repo / "shipwright_test_config.json").write_text(
        '{"suite":{"max_workers":1}}\n', encoding="utf-8")
    suite_config_after, error = source_fingerprint(repo)
    assert suite_config_after is not None, error
    assert suite_config_after != before


def test_diff_cover_timeout_is_a_phase_specific_closed_gate(tmp_path):
    def timeout(argv, **kwargs):
        if argv[0] != "uvx":
            output = Path(argv[argv.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("<coverage/>", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    res = run_gate(tmp_path, expected=_data(tmp_path, 1), suite_green=True,
                   branch="origin/main", diff_file=_diff(tmp_path), runner=timeout)
    assert res.exit_code == GATE_FAILED
    assert any("could not run diff-cover" in line for line in res.lines)


def test_a_report_that_vanishes_mid_check_is_untrusted_not_a_traceback(tmp_path):
    """TOCTOU, raised by external review: this module explicitly contemplates a
    concurrent coverage writer, so the report can disappear between being written
    and being stat'ed. That must read as an untrusted measurement, never as a
    crash on the path whose whole job is to fail closed."""
    def run(argv, **kwargs):
        if argv[0] != "uvx":
            # A combine that "succeeds" but leaves nothing readable behind.
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError("the gate must not be reached without a trusted report")

    res = run_gate(tmp_path, expected=_data(tmp_path, 1), suite_green=True,
                   branch="origin/main", diff_file=_diff(tmp_path), runner=run)
    assert res.exit_code == GATE_FAILED
    assert any("no combined coverage.xml" in ln for ln in res.lines)
