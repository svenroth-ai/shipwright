"""``scripts/run_full_suite_evidence.py`` — the R1a full-suite evidence runner (E-D/E-E).

Loaded by path (ADR-045: register in ``sys.modules`` BEFORE ``exec_module``), never via
a ``sys.path`` insert — same convention as ``test_verify_local.py`` for a top-level
``scripts/`` subject with no dedicated pytest root of its own.

Split into: (1) pure planning (`plan_root`/`plan_all_roots`/`pytest_command`) — no
subprocess, no filesystem beyond `Path.relative_to`; (2) `run_root` with an injected
fake runner (never spawns real pytest here — a real 18-root run takes 30-60+ minutes and
belongs to the operator's own full-suite invocation, not this test); (3) `stage_all`
against a real (throwaway `tmp_path`) `evidence_drop` call, proving the wiring end to
end without touching the live main tree (`--project-root <scratchpad>` rule).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBJECT = REPO_ROOT / "scripts" / "run_full_suite_evidence.py"


def _load_subject(name: str = "_full_suite_evidence_probe"):
    spec = importlib.util.spec_from_file_location(name, _SUBJECT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # ADR-045: register BEFORE exec
    spec.loader.exec_module(module)
    return module


rfse = _load_subject()


# --- pure planning: root list AND base mapping derived, not hand-maintained (E-E) --

def test_plugin_root_plan_cds_into_the_plugin_and_bases_on_it():
    repo_root = Path("/repo")
    root = repo_root / "plugins" / "shipwright-compliance" / "tests"
    plan = rfse.plan_root(repo_root, root, repo_root / "raw", 1)
    assert plan.cwd == repo_root / "plugins" / "shipwright-compliance"
    assert plan.pytest_arg == "tests"
    assert plan.base == "plugins/shipwright-compliance"
    assert plan.marker_expr is None


def test_a_brand_new_plugin_root_is_planned_identically_with_zero_code_changes():
    # AC: a newly added plugins/<new>/tests must be picked up with no runner changes —
    # the structural rule (parent dir under plugins/) is what does the work, not a name.
    repo_root = Path("/repo")
    root = repo_root / "plugins" / "shipwright-totally-new-plugin" / "tests"
    plan = rfse.plan_root(repo_root, root, repo_root / "raw", 1)
    assert plan.base == "plugins/shipwright-totally-new-plugin"
    assert plan.cwd == repo_root / "plugins" / "shipwright-totally-new-plugin"


def test_shared_family_root_runs_from_repo_root_with_the_shared_marker_expr():
    repo_root = Path("/repo")
    root = repo_root / "shared" / "scripts" / "tools" / "tests"
    plan = rfse.plan_root(repo_root, root, repo_root / "raw", 1)
    assert plan.cwd == repo_root
    assert plan.pytest_arg == "shared/scripts/tools/tests"
    assert plan.base == ""
    assert plan.marker_expr == "not slow and not cross_plugin"


def test_integration_tests_root_runs_from_repo_root_with_no_marker_override():
    repo_root = Path("/repo")
    root = repo_root / "integration-tests"
    plan = rfse.plan_root(repo_root, root, repo_root / "raw", 1)
    assert plan.cwd == repo_root
    assert plan.pytest_arg == "integration-tests"
    assert plan.base == ""
    assert plan.marker_expr is None


def test_plan_all_roots_is_sorted_deterministically():
    repo_root = Path("/repo")
    roots = [
        repo_root / "plugins" / "shipwright-b" / "tests",
        repo_root / "integration-tests",
        repo_root / "plugins" / "shipwright-a" / "tests",
    ]
    plans = rfse.plan_all_roots(repo_root, roots, repo_root / "raw")
    assert [p.rel_root for p in plans] == [
        "integration-tests",
        "plugins/shipwright-a/tests",
        "plugins/shipwright-b/tests",
    ]
    assert [p.junit_out.name for p in plans] == [
        "01-integration-tests.xml",
        "02-plugins_shipwright-a_tests.xml",
        "03-plugins_shipwright-b_tests.xml",
    ]


def test_pytest_command_shape_for_a_plugin_root():
    repo_root = Path("/repo")
    plan = rfse.plan_root(repo_root, repo_root / "plugins" / "x" / "tests", repo_root / "raw", 1)
    cmd = rfse.pytest_command(plan)
    assert cmd[:4] == ["uv", "run", "--with", "pytest"]
    assert "tests" in cmd
    assert any(c.startswith("--junitxml=") for c in cmd)
    assert "-m" not in cmd  # no marker override for a plugin root


def test_pytest_command_carries_the_marker_for_a_shared_root():
    repo_root = Path("/repo")
    plan = rfse.plan_root(repo_root, repo_root / "shared" / "tests", repo_root / "raw", 1)
    cmd = rfse.pytest_command(plan)
    assert "-m" in cmd
    assert cmd[cmd.index("-m") + 1] == "not slow and not cross_plugin"


# --- run_root: injected fake runner, never spawns real pytest -----------------------

class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def test_run_root_reports_success_when_junit_is_produced(tmp_path):
    repo_root = tmp_path
    plan = rfse.plan_root(repo_root, repo_root / "shared" / "tests", tmp_path / "raw", 1)

    def fake_runner(cmd, cwd):
        plan.junit_out.parent.mkdir(parents=True, exist_ok=True)
        plan.junit_out.write_text("<testsuites/>", encoding="utf-8")
        return _FakeProc(0)

    result = rfse.run_root(plan, runner=fake_runner)
    assert result.returncode == 0
    assert result.produced_junit is True


def test_run_root_reports_no_evidence_when_the_process_never_writes_junit(tmp_path):
    repo_root = tmp_path
    plan = rfse.plan_root(repo_root, repo_root / "shared" / "tests", tmp_path / "raw", 1)

    def fake_runner(cmd, cwd):
        return _FakeProc(2)  # crashed before writing any report

    result = rfse.run_root(plan, runner=fake_runner)
    assert result.produced_junit is False


def test_run_root_still_collects_evidence_from_a_root_with_failing_tests(tmp_path):
    # A red root still emits a valid report — its executed:fail entries ARE the wanted
    # evidence, never suppressed just because the return code was nonzero.
    repo_root = tmp_path
    plan = rfse.plan_root(repo_root, repo_root / "shared" / "tests", tmp_path / "raw", 1)

    def fake_runner(cmd, cwd):
        plan.junit_out.parent.mkdir(parents=True, exist_ok=True)
        plan.junit_out.write_text("<testsuites/>", encoding="utf-8")
        return _FakeProc(1)

    result = rfse.run_root(plan, runner=fake_runner)
    assert result.returncode == 1
    assert result.produced_junit is True


# --- stage_all: real evidence_drop call against a throwaway project root ------------

def test_stage_all_stages_every_produced_report_with_its_base(tmp_path):
    repo_root = tmp_path
    plan_a = rfse.plan_root(repo_root, repo_root / "shared" / "tests", tmp_path / "raw", 1)
    plan_a.junit_out.parent.mkdir(parents=True, exist_ok=True)
    plan_a.junit_out.write_text("<testsuites/>", encoding="utf-8")
    plan_b = rfse.plan_root(
        repo_root, repo_root / "plugins" / "shipwright-x" / "tests", tmp_path / "raw", 2
    )
    plan_b.junit_out.write_text("<testsuites/>", encoding="utf-8")

    results = [
        rfse.RootRunResult(plan=plan_a, returncode=0, produced_junit=True),
        rfse.RootRunResult(plan=plan_b, returncode=0, produced_junit=True),
    ]
    prov = rfse.stage_all(repo_root, results, run_id="r1", head_commit="deadbeef")
    entries = prov["reports"]["junit"]
    assert [e["base"] for e in entries] == ["", "plugins/shipwright-x"]


def test_stage_all_skips_roots_with_no_produced_evidence(tmp_path):
    repo_root = tmp_path
    plan = rfse.plan_root(repo_root, repo_root / "shared" / "tests", tmp_path / "raw", 1)
    # junit_out never written — the process crashed before producing one.
    results = [rfse.RootRunResult(plan=plan, returncode=2, produced_junit=False)]
    prov = rfse.stage_all(repo_root, results, run_id="r1", head_commit="")
    assert prov["reports"] == {}


# --- E-E: the loader really reaches conftest.py's own discover_test_roots ----------

def test_load_discover_test_roots_reaches_the_real_repo_root_conftest():
    # Not a fake — proves this tool calls the SAME function the ADR-044 pytest guard
    # uses, rather than a second hand-maintained root list that could silently drift.
    discover_test_roots = rfse._load_discover_test_roots()
    roots = discover_test_roots(REPO_ROOT)
    assert (REPO_ROOT / "shared" / "tests") in roots
    assert (REPO_ROOT / "integration-tests") in roots
    assert any("plugins" in r.parts for r in roots)  # at least one plugins/*/tests root


def test_load_discover_test_roots_honors_a_different_project_root(tmp_path):
    # External-review finding: loading the SCRIPT's own compile-time _REPO_ROOT
    # regardless of --project-root would silently use THIS repo's discovery logic
    # against a DIFFERENT target repo. A distinct conftest.py with a marker-only
    # discover_test_roots proves the loader actually reaches the TARGET's own file.
    (tmp_path / "conftest.py").write_text(
        "def discover_test_roots(repo_root):\n"
        "    return {repo_root / 'marker-only-root'}\n",
        encoding="utf-8",
    )
    discover_test_roots = rfse._load_discover_test_roots(tmp_path)
    roots = discover_test_roots(tmp_path)
    assert roots == {tmp_path / "marker-only-root"}


def test_main_loads_conftest_from_project_root_not_the_scripts_own_repo(tmp_path, monkeypatch):
    # End-to-end: main()'s own wiring must pass --project-root through to the loader,
    # not rely on the script's compile-time _REPO_ROOT.
    (tmp_path / "conftest.py").write_text(
        "def discover_test_roots(repo_root):\n"
        "    return set()\n",  # zero roots — deliberately distinguishable from this repo's 18
        encoding="utf-8",
    )
    monkeypatch.setattr(rfse.subprocess, "run", lambda *a, **k: _FakeProc(0))
    rc = rfse.main([
        "--project-root", str(tmp_path), "--run-id", "iterate-x", "--skip-sync",
        "--head-commit", "deadbeef",
    ])
    # Stage-2 review: zero discovered roots produced NO evidence at all — the same
    # HARD-failure class the module docstring declares for one crashed root, not a
    # quiet success just because nothing individually returned nonzero.
    assert rc == 1
    prov_path = tmp_path / ".shipwright" / "compliance" / "evidence" / "_provenance.json"
    assert prov_path.is_file()
    import json  # noqa: PLC0415
    assert json.loads(prov_path.read_text(encoding="utf-8"))["reports"] == {}


def test_main_clears_stale_evidence_before_running_any_root(tmp_path, monkeypatch):
    # A full-suite pass takes ~20 minutes; a prior run's raw report must not sit
    # under the conventional evidence dir for that whole window (a concurrent test
    # in one of the driven roots can observe — and fail on — a stale file there).
    (tmp_path / "conftest.py").write_text(
        "def discover_test_roots(repo_root):\n"
        "    return set()\n",
        encoding="utf-8",
    )
    evidence_dir = tmp_path / ".shipwright" / "compliance" / "evidence"
    evidence_dir.mkdir(parents=True)
    stale = evidence_dir / "junit.xml"
    stale.write_text("STALE-FROM-BEFORE-THIS-RUN", encoding="utf-8")
    monkeypatch.setattr(rfse.subprocess, "run", lambda *a, **k: _FakeProc(0))
    rc = rfse.main([
        "--project-root", str(tmp_path), "--run-id", "iterate-x", "--skip-sync",
        "--head-commit", "deadbeef",
    ])
    assert rc == 1  # zero roots discovered ⇒ HARD failure (Stage-2 review), unrelated to the clear
    assert not stale.is_file()  # cleared before any root ran, not just at the final stage


# --- main(): wiring smoke test, discover + subprocess both faked -------------------

def test_main_wires_discovery_execution_and_staging_together(tmp_path, monkeypatch):
    repo_root = tmp_path
    (repo_root / "shared").mkdir(parents=True)
    (repo_root / "plugins" / "shipwright-x").mkdir(parents=True)
    fake_roots = {
        repo_root / "shared" / "tests",
        repo_root / "plugins" / "shipwright-x" / "tests",
    }
    monkeypatch.setattr(rfse, "_load_discover_test_roots", lambda _repo_root: (lambda _root: fake_roots))

    def fake_subprocess_run(cmd, cwd=None, check=None):
        # Emulate pytest: write the --junitxml file the real invocation would produce.
        for part in cmd:
            if isinstance(part, str) and part.startswith("--junitxml="):
                out = Path(part.split("=", 1)[1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("<testsuites/>", encoding="utf-8")
        return _FakeProc(0)

    monkeypatch.setattr(rfse.subprocess, "run", fake_subprocess_run)

    rc = rfse.main([
        "--project-root", str(repo_root), "--run-id", "iterate-full-suite-smoke",
        "--skip-sync", "--head-commit", "deadbeef",
    ])
    assert rc == 0
    prov_path = repo_root / ".shipwright" / "compliance" / "evidence" / "_provenance.json"
    assert prov_path.is_file()
