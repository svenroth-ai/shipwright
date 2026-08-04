"""F0 suite runner — the coverage instrumentation wiring.

Split from `test_run_test_suite.py` the way `test_run_test_suite_faults.py` already
is: that file was at its size budget, and this is a distinct subject — not "does the
suite reach the right verdict" but "is the measurement the gate depends on actually
switched on".

The load-bearing test here is `test_run_suite_reports_the_files_it_told_units_to_write`.
Every other test in this file could pass while the single wiring line in `run_suite`
was deleted, because the fixtures elsewhere build projects with no root
`pyproject.toml`, where instrumentation correctly short-circuits to zero. The gate
would then report "n/a - nothing to measure" and exit 0 on every future run: a
permanent, silent PASS, which is the exact failure this whole change exists to
prevent. Note the diff-coverage gate cannot catch that either — the line IS executed
by the other tests, so it scores as covered. Executed is not asserted.
"""

from __future__ import annotations

from contextlib import contextmanager
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
import scripts.tools.suite_gate_runtime as gate_mod
from scripts.tools.run_test_suite import PASS, build_command, discover_units


@contextmanager
def _leased(root, result):
    source_before, fingerprint_error = mod.source_fingerprint(root)
    yield result, source_before, fingerprint_error


def _project(tmp_path: Path) -> Path:
    """A project shaped like the monorepo, WITH the root pyproject.toml that
    instrumentation requires — the thing the sibling fixtures deliberately lack."""
    for name in ("shipwright-alpha", "shipwright-beta"):
        p = tmp_path / "plugins" / name
        (p / "tests").mkdir(parents=True)
        (p / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "plugins/shipwright-alpha/scripts").mkdir()
    for d in ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests",
              "integration-tests"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[tool.coverage.run]\n", encoding="utf-8")
    (tmp_path / "shipwright_test_config.json").write_text(
        '{"suite": {}}', encoding="utf-8")
    return tmp_path


def test_run_suite_reports_the_files_it_told_units_to_write(tmp_path, monkeypatch):
    """The one line joining "we instrument" to "we gate", asserted end to end.

    Derived from `discover_units` rather than a literal, so adding a shared dir or a
    plugin does not silently narrow what this proves.
    """
    root = _project(tmp_path)
    monkeypatch.setattr(mod, "_exec", lambda *a, **k: (0, "", 0.01, True))
    result = mod.run_suite(root)

    expected = {u.id for u in discover_units(root)} - {"shipwright-beta"}
    assert len(result.cov_files) == len(expected), result.cov_files
    assert len(set(result.cov_files)) == len(result.cov_files), "shared data file"
    assert all(Path(f).parent.name == ".cov-data" for f in result.cov_files)


def test_a_project_without_a_root_pyproject_measures_nothing(tmp_path, monkeypatch):
    """The other half of the same wiring: instrumentation that cannot be honoured is
    reported as nothing-to-gate, not as a broken measurement."""
    root = _project(tmp_path)
    (root / "pyproject.toml").unlink()
    monkeypatch.setattr(mod, "_exec", lambda *a, **k: (0, "", 0.01, True))
    assert mod.run_suite(root).cov_files == ()


def test_an_authoritative_retry_discards_the_failed_attempts_coverage(
        tmp_path, monkeypatch):
    """Only the accepted retry may contribute to diff coverage. In particular,
    xdist suffix files from a failed first attempt must not inflate its report."""
    root = _project(tmp_path)
    calls = {"shipwright-alpha": 0}

    def fake_exec(unit, project_root, workers, tmp_dir, timeout=None):
        if unit.id != "shipwright-alpha":
            return 0, "", 0.01, True
        calls[unit.id] += 1
        base = Path(unit.cov_file)
        if calls[unit.id] == 1:
            base.write_text("failed-base", encoding="utf-8")
            Path(f"{base}.host.1.abc").write_text("failed-xdist", encoding="utf-8")
            return 1, "failed", 0.01, True
        assert not base.exists()
        assert list(base.parent.glob(f"{base.name}.*")) == []
        base.write_text("accepted-retry", encoding="utf-8")
        return 0, "", 0.01, True

    monkeypatch.setattr(mod, "_exec", fake_exec)
    result = mod.run_suite(root)
    accepted = next(Path(p) for p in result.cov_files
                    if p.endswith("shipwright-alpha"))
    assert result.exit_code == 0
    assert accepted.read_text(encoding="utf-8") == "accepted-retry"


def _capture_env(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["env"] = kw["env"]
        seen["argv"] = argv
        raise OSError("stop here — we only wanted the environment")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    return seen


def test_an_instrumented_unit_gets_its_own_coverage_file(tmp_path, monkeypatch):
    seen = _capture_env(monkeypatch)
    unit = mod.Unit(id="u", cwd=".", target="tests", cov_file=str(tmp_path / ".cov"))
    mod._exec(unit, tmp_path, None, tmp_path / "t")
    assert seen["env"]["COVERAGE_FILE"] == str(tmp_path / ".cov")


def test_an_uninstrumented_unit_does_not_inherit_an_ambient_coverage_file(
        tmp_path, monkeypatch):
    """AC-10. An operator with COVERAGE_FILE exported would otherwise have one
    unmeasured unit scribble into another tier's data file."""
    monkeypatch.setenv("COVERAGE_FILE", "/somewhere/else/.coverage")
    seen = _capture_env(monkeypatch)
    mod._exec(mod.Unit(id="u", cwd=".", target="tests"), tmp_path, None, tmp_path / "t")
    assert "COVERAGE_FILE" not in seen["env"]


def test_coverage_args_never_split_the_marker_expression(tmp_path):
    """AC-7 — the load-bearing half of landmine (3). A CLI `-m` REPLACES the
    pyproject default, so `-m` and its expression must stay adjacent: anything
    inserted between them would rewrite the shared tier's selection silently."""
    unit = mod.Unit(id="shared/tests", cwd=".", target="shared/tests",
                    markers=("-m", "not slow and not cross_plugin"),
                    cov_args=("--cov=shared", "--cov-report="))
    cmd = build_command(unit, None)
    assert cmd[cmd.index("-m") + 1] == "not slow and not cross_plugin"
    assert cmd.index("--cov=shared") > cmd.index("-m") + 1


def test_an_under_covered_diff_stops_the_run(tmp_path, monkeypatch, capsys):
    """AC-4: a green suite with a failing gate exits 4, and diff-cover's own
    report reaches the operator rather than dying inside the runner."""
    from scripts.tools.suite_coverage import GATE_FAILED, GateResult

    monkeypatch.setattr(gate_mod, "run_gate",
                        lambda *a, **k: GateResult(GATE_FAILED, ["see: foo.py:3"]))
    monkeypatch.setattr(gate_mod, "compare_branch", lambda *a, **k: "origin/main")
    monkeypatch.setattr(mod, "source_fingerprint", lambda *a, **k: ("stable", ""))
    monkeypatch.setattr(gate_mod, "build_worktree_diff",
                        lambda *a, **k: (tmp_path / "worktree.diff", ""))
    monkeypatch.setattr(mod, "_run_host_leased_suite", lambda root, *a, **k: _leased(
        root, mod.SuiteResult([mod.UnitResult("u", PASS, 0, 0.1)],
                              0, 0.1, (), 3)))
    monkeypatch.setattr(sys, "argv", ["run_test_suite.py", "--project-root", str(tmp_path)])

    assert mod.main() == GATE_FAILED
    assert "see: foo.py:3" in capsys.readouterr().out


def test_a_red_suite_never_fetches_or_builds_a_diff(tmp_path, monkeypatch):
    """The red verdict is already authoritative; network work must not delay it."""
    monkeypatch.setattr(mod, "_run_host_leased_suite", lambda root, *a, **k: _leased(
        root, mod.SuiteResult([mod.UnitResult("u", mod.TEST_FAILURE, 1, 0.1)],
                              1, 0.1, (), ("x",))))
    monkeypatch.setattr(
        gate_mod, "compare_branch",
        lambda *a, **k: pytest.fail("a red suite must not fetch origin/main"))
    monkeypatch.setattr(
        gate_mod, "build_worktree_diff",
        lambda *a, **k: pytest.fail("a red suite must not build a diff"))
    monkeypatch.setattr(sys, "argv", ["run_test_suite.py", "--project-root",
                                      str(tmp_path)])
    assert mod.main() == 1


def test_the_gate_is_handed_the_files_not_just_a_count(tmp_path, monkeypatch):
    """The gate must be able to tell "never instrumented" from "instrumented and
    wrote nothing", which a bare count cannot express — so `main` passes the data
    files themselves through, unmodified."""
    captured = {}

    def fake_gate(root, *, expected, branch, diff_file, suite_green):
        captured.update(expected=tuple(expected), suite_green=suite_green,
                        branch=branch, diff_file=diff_file)
        from scripts.tools.suite_coverage import GATE_PASSED, GateResult
        return GateResult(GATE_PASSED, [])

    files = (r"C:\x\.cov-data\.coverage.a", r"C:\x\.cov-data\.coverage.b")
    monkeypatch.setattr(gate_mod, "run_gate", fake_gate)
    monkeypatch.setattr(gate_mod, "compare_branch", lambda *a, **k: "origin/main")
    monkeypatch.setattr(mod, "source_fingerprint", lambda *a, **k: ("stable", ""))
    diff_file = tmp_path / "worktree.diff"
    monkeypatch.setattr(gate_mod, "build_worktree_diff",
                        lambda *a, **k: (diff_file, ""))
    monkeypatch.setattr(mod, "_run_host_leased_suite", lambda root, *a, **k: _leased(
        root, mod.SuiteResult([mod.UnitResult("u", PASS, 0, 0.1)],
                              0, 0.1, (), files)))
    monkeypatch.setattr(sys, "argv", ["run_test_suite.py", "--project-root", str(tmp_path)])

    assert mod.main() == 0
    assert captured == {"expected": files, "suite_green": True,
                        "branch": "origin/main", "diff_file": diff_file}


def test_source_change_during_suite_invalidates_coverage(
        tmp_path, monkeypatch, capsys):
    fingerprints = iter((("before", ""), ("after", "")))
    monkeypatch.setattr(mod, "source_fingerprint", lambda *a, **k: next(fingerprints))
    monkeypatch.setattr(mod, "_run_host_leased_suite", lambda root, *a, **k: _leased(
        root, mod.SuiteResult([mod.UnitResult("u", PASS, 0, 0.1)],
                              0, 0.1, (), ("x",))))
    monkeypatch.setattr(
        gate_mod, "compare_branch",
        lambda *a, **k: pytest.fail("a changed source snapshot must not be gated"))
    monkeypatch.setattr(sys, "argv", ["run_test_suite.py", "--project-root",
                                      str(tmp_path)])

    assert mod.main() == 4
    assert "sources or test/coverage configuration changed" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("fingerprints", "build_calls", "gate_calls"),
    [
        (("same", "changed"), 0, 0),
        (("same", "same", "changed"), 1, 0),
        (("same", "same", "same", "changed"), 1, 1),
    ],
)
def test_source_change_after_fetch_patch_or_gate_invalidates_measurement(
        tmp_path, monkeypatch, fingerprints, build_calls, gate_calls):
    seen = {"build": 0, "gate": 0}
    values = iter((value, "") for value in fingerprints)
    monkeypatch.setattr(mod, "source_fingerprint", lambda *a, **k: next(values))
    monkeypatch.setattr(gate_mod, "compare_branch", lambda *a, **k: "origin/main")

    def build(*args, **kwargs):
        seen["build"] += 1
        return tmp_path / "worktree.diff", ""

    def gate(*args, **kwargs):
        seen["gate"] += 1
        from scripts.tools.suite_coverage import GATE_PASSED, GateResult
        return GateResult(GATE_PASSED, ["pass"])

    monkeypatch.setattr(gate_mod, "build_worktree_diff", build)
    monkeypatch.setattr(gate_mod, "run_gate", gate)
    result = mod.SuiteResult(
        [mod.UnitResult("u", PASS, 0, 0.1)], 0, 0.1, (), ("x",))

    assert mod._gate_green_suite(tmp_path, result, "same").exit_code == 4
    assert seen == {"build": build_calls, "gate": gate_calls}


def test_warm_up_provisions_the_package_instrumentation_adds(monkeypatch):
    """Coverage puts `pytest-cov` in nearly every unit's env key. warm_up exists so
    18 cold `uv run` calls do not race the shared uv cache — a documented Windows
    hardlink-race source — so a package it does not warm re-creates that race."""
    seen = {}
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda argv, **kw: seen.setdefault("argv", argv))
    mod.warm_up(Path("."))
    assert "pytest-cov" in seen["argv"]
