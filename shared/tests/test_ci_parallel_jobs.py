"""The parallel `tests-shared` job and the fail-closed gather job in ci.yml.

CI-duration iterate 2/3 (iterate-2026-11-06-ci-parallel-jobs). The 8-minute `shared/`
test tier runs in its own job `tests-shared`, plugins + integration + the replay gate in `tests-main`
(neither has `needs`, so they start together); `python-checks` (the one required check, `Python (lint +
test)`) only lints, gathers both tiers' JUnit + coverage data by artifact and runs every gate step.

Parsed YAML, never string matching. Two things here protect a green required check from
hiding a hole:

* a job whose `needs` failed is SKIPPED and GitHub counts a skipped required check as
  passing, so the gather job must run `always()` and turn every non-`success` result into
  a failure itself;
* the coverage data hand-off has no JUnit-style verify of its own, so a dedicated gate
  asserts every expected `.coverage.*` arrived.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GATHER = "python-checks"
SHARED = "tests-shared"
MAIN = "tests-main"
NEEDS_STEP = "Test jobs finished green (fail-closed on needs)"


def _doc() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _jobs() -> dict:
    return _doc()["jobs"]


def _steps(job: str) -> list[dict]:
    return _jobs()[job]["steps"]


def _step(job: str, name: str) -> dict:
    for s in _steps(job):
        if s.get("name") == name:
            return s
    raise AssertionError(f"{job}: step {name!r} not found")


def _order(job: str) -> dict[str, int]:
    return {s["name"]: i for i, s in enumerate(_steps(job)) if s.get("name")}


_TEST_JOBS = (SHARED, MAIN)


def _runs_tests(job: dict) -> bool:
    """True when any step COMMAND invokes pytest or the replay gate, whatever the step is called.
    `--with pytest[-plugin]` is dependency provisioning (the plan step has it), not a test run."""
    for st in job.get("steps", []):
        body = re.sub(r"--with[ =]\"?pytest[\w-]*\"?", "", str(st.get("run", "")))
        if "pytest" in body or "events_replay_gate" in body:
            return True
    return False


def test_the_test_detector_ignores_names_and_dependency_provisioning():
    plan = {"steps": [{"name": "Plan", "run": "uv run --with pytest shared/scripts/tools/ci_junit_plan.py plan"}]}
    renamed = {"steps": [{"name": "Lint more", "run": "uv run pytest shared/tests"}]}
    replay = {"steps": [{"name": "x", "run": "uv run python shared/scripts/tools/events_replay_gate.py"}]}
    assert not _runs_tests(plan)
    assert _runs_tests(renamed) and _runs_tests(replay)


# ---------------------------------------------------------------- AC1 topology

@pytest.mark.covers("FR-01.17/AC02")
def test_the_required_check_gathers_the_shared_tier():
    jobs = _jobs()
    assert jobs[GATHER]["name"] == "Python (lint + test)", "the required check's name is a contract"
    assert jobs[SHARED]["name"] == "Tests (shared)"
    assert jobs[MAIN]["name"] == "Tests (plugins + integration + replay)"
    assert jobs[GATHER]["needs"] == [SHARED, MAIN]


@pytest.mark.covers("FR-01.17/AC02")
def test_every_job_that_runs_tests_is_a_designated_test_job_and_is_gathered():
    """Reverse drift: a test job that is not in `needs` could go red while the required check stays
    green, and `check_ci_gate_coverage` ignores job topology. Detection is by what a step RUNS, never
    by what it is called, and tests may live ONLY in the two designated test jobs."""
    needs = set(_jobs()[GATHER].get("needs") or [])
    for job_id, job in _jobs().items():
        if not _runs_tests(job):
            continue
        assert job_id in _TEST_JOBS, f"job {job_id!r} runs tests but is not one of {_TEST_JOBS}"
        assert job_id in needs, f"job {job_id!r} runs tests but python-checks does not `need` it"


# ---------------------------------------------------------------- AC2 fail closed

@pytest.mark.covers("FR-01.17/AC02")
def test_the_gather_job_runs_always_and_never_via_not_cancelled():
    assert _jobs()[GATHER]["if"] == "always()"


@pytest.mark.covers("FR-01.17/AC02")
def test_no_needed_job_can_swallow_its_own_failure():
    for job_id in _jobs()[GATHER]["needs"]:
        job = _jobs()[job_id]
        assert "continue-on-error" not in job, f"{job_id}: job-level continue-on-error makes its result `success`"


@pytest.mark.covers("FR-01.17/AC02")
def test_the_result_step_is_always_conditioned_and_precedes_the_gates():
    step = _step(GATHER, NEEDS_STEP)
    assert step["if"] == "always()", "steps default to success(); a failed run would skip the check"
    assert step["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    order = _order(GATHER)
    assert order["Lint (ruff)"] < order[NEEDS_STEP] < order["Combine coverage"]


def _result_check(needs_json: dict) -> subprocess.CompletedProcess:
    run = _step(GATHER, NEEDS_STEP)["run"]
    return subprocess.run(
        ["bash", "-c", run], env={**os.environ, "NEEDS": json.dumps(needs_json)},
        capture_output=True, text=True, timeout=60,
    )


def _need_bash_and_jq():
    bash = shutil.which("bash")
    # On Windows `bash` may be the WSL launcher (no env passthrough, no jq): require a working jq.
    if bash and shutil.which("jq") and subprocess.run(
        [bash, "-c", "command -v jq"], capture_output=True, timeout=30
    ).returncode == 0:
        return
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("bash and jq are required in CI to exercise the needs-result step "
                    "(ubuntu-latest ships both)")
    pytest.skip("bash/jq not available locally")


@pytest.mark.covers("FR-01.17/AC02")
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_any_result_other_than_success_fails_the_required_check(result):
    _need_bash_and_jq()
    proc = _result_check({SHARED: {"result": result, "outputs": {}}})
    assert proc.returncode != 0, f"a {result} needed job must fail the gather job"
    assert f"{SHARED}: {result}" in proc.stdout, "the failing job and its result must be named"


@pytest.mark.covers("FR-01.17/AC02")
def test_an_empty_needs_set_is_not_a_pass():
    _need_bash_and_jq()
    assert _result_check({}).returncode != 0, "no needed jobs at all must never read as green"


@pytest.mark.covers("FR-01.17/AC02")
def test_one_red_job_among_green_ones_still_fails():
    _need_bash_and_jq()
    proc = _result_check({SHARED: {"result": "success", "outputs": {}}, MAIN: {"result": "failure", "outputs": {}}})
    assert proc.returncode != 0 and f"{MAIN}: failure" in proc.stdout


@pytest.mark.covers("FR-01.17/AC02")
def test_all_needed_jobs_green_passes():
    _need_bash_and_jq()
    proc = _result_check({j: {"result": "success", "outputs": {}} for j in (SHARED, MAIN)})
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------- AC3 serial

def test_no_pytest_step_runs_with_a_worker_count():
    """The text-level xdist ban lives in test_f0_ci_parity.py::test_ci_stays_SERIAL; this
    pins the parsed-step form for every job (continuations joined, whole step body)."""
    import re

    for job_id, job in _jobs().items():
        for s in job["steps"]:
            body = re.sub(r"\\\s*\n", " ", str(s.get("run", "")))
            if "pytest" not in body:
                continue
            assert not re.search(r"(^|\s)-n\s*\S", body), (job_id, s.get("name"))
            assert "--numprocesses" not in body and "pytest-xdist" not in body, (job_id, s.get("name"))


# ---------------------------------------------------------------- AC4 hand-off

@pytest.mark.covers("FR-01.17/AC02")
@pytest.mark.parametrize("job,artifact", [(SHARED, "ci-tests-shared"), (MAIN, "ci-tests-main")])
def test_each_test_job_uploads_both_hidden_dirs_as_one_artifact(job, artifact):
    step = _step(job, "Upload test-root evidence (JUnit + coverage data)")
    assert step["if"] == "always()"
    w = step["with"]
    assert w["name"] == artifact
    assert [p.strip() for p in w["path"].split() if p.strip()] == [".ci-junit/", ".cov-data/"]
    assert w["include-hidden-files"] is True, "both dirs are hidden; the default skips them"
    assert w["if-no-files-found"] == "error"
    assert w["overwrite"] is True
    assert 3 <= int(w["retention-days"]) <= 10, "long enough for a late 'Re-run failed jobs' to still find the other tier's artifact"


@pytest.mark.covers("FR-01.17/AC02")
def test_the_gather_job_downloads_into_the_workspace_between_the_result_step_and_combine():
    step = _step(GATHER, "Download test-job evidence (JUnit + coverage data)")
    assert step["if"] == "always()"
    w = step["with"]
    assert w["pattern"] == "ci-tests-*" and w["merge-multiple"] is True and w["path"] == "."
    order = _order(GATHER)
    assert order[NEEDS_STEP] < order["Download test-job evidence (JUnit + coverage data)"]
    assert order["Download test-job evidence (JUnit + coverage data)"] < order["Combine coverage"]
    assert order["Verify test-root JUnit coverage (gate)"] > order["Combine coverage"]


@pytest.mark.covers("FR-01.17/AC02")
def test_a_lost_coverage_file_cannot_be_skipped_past():
    step = _step(GATHER, "Coverage data set (gate)")
    assert "check_ci_coverage_data_set.py" in step["run"]
    assert "if" not in step and "continue-on-error" not in step
    order = _order(GATHER)
    assert order["Download test-job evidence (JUnit + coverage data)"] < order["Coverage data set (gate)"]
    assert order["Coverage data set (gate)"] < order["Combine coverage"]


# ---------------------------------------------------------------- AC7 setup

def test_scanners_install_once_where_the_plugin_tests_run_and_lint_once_in_the_gather_job():
    names = [s.get("name") for job in _jobs().values() for s in job["steps"]]
    for n in ("Install Semgrep", "Install Trivy", "Install Gitleaks"):
        assert names.count(n) == 1, n
        assert n in _order(MAIN), "the security plugin's smoke tests need the scanners on PATH"
    assert names.count("Lint (ruff)") == 1 and "Lint (ruff)" in _order(GATHER)


@pytest.mark.covers("FR-01.17/AC02")
def test_a_job_with_needs_runs_no_tests():
    """A job with `needs` does not start before its needs finish, so any test left in it runs AFTER
    the parallel tiers instead of beside them (the original shape of this change did exactly that and
    was slower than before). The gather job must only lint, collect and gate - judged by the commands
    its steps run, so renaming a step cannot smuggle a test back in."""
    for job_id, job in _jobs().items():
        if job.get("needs"):
            assert not _runs_tests(job), f"{job_id} has `needs` but runs tests: they would start after the test jobs"


@pytest.mark.covers("FR-01.17/AC02")
def test_the_plugin_loop_and_the_coverage_set_tool_select_plugins_the_same_way():
    """check_ci_coverage_data_set derives its expected `.coverage.<plugin>` files structurally
    (pyproject + tests + scripts); the CI loop must still apply exactly those conditions."""
    run = _step(MAIN, "Run plugin tests")["run"]
    assert '-f "$plugin/pyproject.toml"' in run and '-d "$plugin/tests"' in run
    assert '-d "$plugin/scripts"' in run and "--cov=scripts" in run


@pytest.mark.covers("FR-01.17/AC02")
def test_the_test_jobs_have_no_needs_so_they_start_together():
    for job_id in (SHARED, MAIN):
        assert not _jobs()[job_id].get("needs"), job_id


def test_the_shared_job_prepares_its_coverage_dir_before_first_use():
    order = _order(SHARED)
    assert order["Prepare coverage data dir"] < order["Run shared tests"]
    prep = _step(SHARED, "Prepare coverage data dir")["run"]
    assert "rm -rf .cov-data" in prep and "mkdir -p .cov-data" in prep


def test_all_jobs_share_one_pinned_setup_sequence():
    def setup(job):
        steps = _steps(job)
        checkout = steps[0]
        assert checkout["uses"].startswith("actions/checkout@")
        assert checkout["with"]["fetch-depth"] == 0
        return [checkout["uses"]] + [s["uses"] if "uses" in s else s["run"] for s in steps[1:4]]

    assert setup(SHARED) == setup(MAIN) == setup(GATHER)
    assert "uv python install 3.11" in setup(GATHER)


# ---------------------------------------------------------------- AC8 advisory

def test_the_new_check_is_declared_advisory_not_required():
    cfg = json.loads((REPO_ROOT / "shipwright_run_config.json").read_text(encoding="utf-8"))
    advisory = cfg.get("required_checks_advisory") or []
    assert "Tests (shared)" in advisory and "Tests (plugins + integration + replay)" in advisory
