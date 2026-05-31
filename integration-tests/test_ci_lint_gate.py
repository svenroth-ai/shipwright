"""Drift-protection for the CI lint gate (iterate-2026-05-31-ci-lint-gate-ruff).

Pins the invariants of `.github/workflows/ci.yml` so a future edit cannot
silently re-neuter the ruff lint step or re-claim type-checking in the job
name. Lives under integration-tests/ (not shared/tests/) because that is the
suite CI actually executes — a drift test that never runs in CI gates nothing.

Invariants:

1.  The ``python-checks`` job name does not claim "type": type-checking is a
    deliberate won't-do for this repo (dismissed triage trg-84f204ba).
2.  The "Lint (ruff)" step GATES — its ``run`` invokes ``ruff check`` and
    contains no ``|| true`` swallow.
3.  The "Lint (ruff)" step carries no ``continue-on-error: true``.
4.  Coupling check: the curated bug-class ruleset the gate depends on exists
    in the root pyproject.toml (``[tool.ruff.lint]`` selects pyflakes ``F``).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _python_checks_job() -> dict:
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert "python-checks" in jobs, "python-checks job missing from ci.yml"
    return jobs["python-checks"]


def _lint_step(job: dict) -> dict:
    for step in job["steps"]:
        if str(step.get("name", "")).startswith("Lint"):
            return step
    raise AssertionError("No 'Lint' step found in the python-checks job")


def test_job_name_does_not_claim_type():
    name = _python_checks_job()["name"]
    assert "type" not in name.lower(), (
        f"python-checks job name claims type-checking ({name!r}), but the repo "
        "deliberately does not type-check (dismissed trg-84f204ba)."
    )


def test_lint_step_gates_and_is_not_neutered():
    step = _lint_step(_python_checks_job())
    run = str(step.get("run", ""))
    # Robust to the invocation form (uvx ruff@X check . / uv run ruff check .).
    assert "ruff" in run and "check" in run, (
        f"Lint step does not run ruff check: {run!r}"
    )
    assert "|| true" not in run, (
        "Lint step swallows ruff's exit code with `|| true` — it gates nothing."
    )
    assert step.get("continue-on-error") is not True, (
        "Lint step has continue-on-error: true — it gates nothing."
    )


def test_curated_ruff_ruleset_present():
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    select = cfg["tool"]["ruff"]["lint"]["select"]
    assert "F" in select, (
        "Root pyproject [tool.ruff.lint] must select the bug-class 'F' "
        "(pyflakes) ruleset that the CI lint gate depends on."
    )
