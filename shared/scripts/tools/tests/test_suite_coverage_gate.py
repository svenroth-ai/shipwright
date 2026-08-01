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

from scripts.tools.suite_coverage import (
    COVERAGE_XML,
    DATA_DIR,
    GATE_FAILED,
    GATE_PASSED,
    compare_branch,
    missing_data,
    prepare_coverage,
    run_gate,
    verdict,
)
from scripts.tools.suite_units import SuiteConfigError


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


def test_compare_branch_prefers_origin_HEAD(tmp_path):
    """A clone whose default branch is not `main` must diff against ITS default."""
    repo = _repo(tmp_path, "trunk")
    _git(repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    assert compare_branch(repo) == "origin/trunk"


def test_compare_branch_falls_back_to_origin_main(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
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
    monkeypatch.setattr("scripts.tools.suite_coverage.time.sleep", lambda s: None)
    assert prepare_coverage(tmp_path).is_dir()
    assert not (tmp_path / COVERAGE_XML).exists()


# --------------------------------------------------------------------------- #
# run_gate — orchestration with an INJECTED runner (no subprocess)
# --------------------------------------------------------------------------- #
def _runner(*, combine_rc: int = 0, gate_rc: int = 0, raise_on: str | None = None):
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        if raise_on is not None and raise_on in " ".join(argv):
            raise OSError("uvx not found")
        if argv[0] != "uvx" and combine_rc == 0:
            # A real combine WRITES the report; the gate checks that this run did.
            Path(kwargs["cwd"], COVERAGE_XML).write_text("<coverage/>", encoding="utf-8")
        rc = gate_rc if argv[0] == "uvx" else combine_rc
        return subprocess.CompletedProcess(argv, rc, stdout="out\n", stderr="")

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


def test_a_red_suite_skips_the_gate_entirely(tmp_path):
    """AC-5. Coverage measured from a suite that did not finish is not a verdict."""
    run, calls = _runner()
    res = run_gate(tmp_path, expected=_data(tmp_path, 3), suite_green=False,
                   branch="origin/main", runner=run)
    assert calls == []
    assert res.exit_code == GATE_PASSED
    assert any("suite is red" in line for line in res.lines)


def test_run_gate_combines_then_gates(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", runner=run)
    assert [c[0] for c in calls] == ["uv", "uvx"]
    assert res.exit_code == GATE_PASSED


def test_run_gate_maps_a_below_threshold_exit_to_a_failure(tmp_path):
    run, _ = _runner(gate_rc=1)
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", runner=run)
    assert res.exit_code == GATE_FAILED


@pytest.mark.parametrize("raise_on", ["uvx", "combine_coverage"])
def test_a_missing_binary_is_a_closed_gate_not_a_traceback(tmp_path, raise_on):
    """AC-4c. `uvx` off PATH, or a resolution failure, must not crash F0 and must
    not pass — the operator gets an exit code and a phase name."""
    run, _ = _runner(raise_on=raise_on)
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch="origin/main", runner=run)
    assert res.exit_code == GATE_FAILED
    assert any(raise_on.split("_")[0] in line or "could not run" in line
               for line in res.lines)


def test_run_gate_does_not_gate_when_nothing_was_eligible(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path, expected=(), suite_green=True, branch="origin/main",
                   runner=run)
    assert calls == []
    assert res.exit_code == GATE_PASSED


def test_run_gate_refuses_without_a_compare_branch(tmp_path):
    run, calls = _runner()
    res = run_gate(tmp_path, expected=_data(tmp_path, 3),
                   suite_green=True, branch=None, runner=run)
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
                   suite_green=True, branch="origin/main", runner=run)
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
    monkeypatch.setattr("scripts.tools.suite_coverage.time.sleep", lambda s: None)
    with pytest.raises(SuiteConfigError, match="stale coverage state"):
        prepare_coverage(tmp_path)


def test_the_no_config_case_names_the_config_not_the_source_roots(tmp_path):
    """Two different causes reach `eligible == 0`; a message that asserts the wrong
    one sends the operator to look in the wrong place."""
    res = verdict(eligible=0, branch="origin/main", no_config=True)
    assert res.exit_code == GATE_PASSED
    assert "pyproject.toml" in " ".join(res.lines)


def test_a_coverage_xml_this_run_did_not_write_is_not_trusted(tmp_path):
    """The reset deletes the previous report — but a concurrent writer (a second F0,
    a compliance regen) between reset and here re-opens the stale-report false green
    from another door, since `combine_coverage` returns 0 for "n/a" untouched."""
    (tmp_path / COVERAGE_XML).write_text("<coverage/>", encoding="utf-8")
    import os
    old = tmp_path / COVERAGE_XML
    os.utime(old, (0, 0))  # unambiguously predates this run

    def run(argv, **kwargs):  # a combine that writes nothing, then a gate that passes
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    res = run_gate(tmp_path, expected=_data(tmp_path, 1), suite_green=True,
                   branch="origin/main", runner=run)
    assert res.exit_code == GATE_FAILED
    assert any("no combined coverage.xml" in ln for ln in res.lines)


def test_an_origin_HEAD_pointing_at_a_ref_that_does_not_resolve_is_rejected(tmp_path):
    """`symbolic-ref` prints its target without checking it EXISTS. A narrowed
    refspec or pruned default branch hands back a name diff-cover then fails on —
    fail-closed either way, but reported as "add tests" not "fetch the base"."""
    repo = _repo(tmp_path, commit=False)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
    assert compare_branch(repo) is None


def test_git_being_unavailable_is_no_base_rather_than_a_crash(tmp_path):
    """`git` off PATH must reach the same fail-closed refusal as a missing ref. An
    OSError escaping here would be a traceback out of F0 from the one helper whose
    documented contract is to return None."""
    def boom(*a, **k):
        raise OSError("git not found")

    assert compare_branch(tmp_path, runner=boom) is None


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
                   branch="origin/main", runner=run)
    assert res.exit_code == GATE_FAILED
    assert any("no combined coverage.xml" in ln for ln in res.lines)
