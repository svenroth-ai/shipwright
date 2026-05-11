"""End-to-end empirical test for path-helpers.ts.template + .test.ts.template.

External-review #O10: rather than deferring path-helpers test verification
to a manual F0.5 step, integrate the Vitest execution into the normal
pytest flow. This test stages the two templates into a tmp dir as
real `.ts` files, installs the minimal Vitest toolchain, and asserts the
suite passes.

The test is the empirical proof that AC-10's template ships a working
heuristic — without it the iterate would just be claiming the template
works without ever running it. The shipwright-webui v0.8.5 bug is the
canonical example of why "looks right in code review" is not enough for
cross-platform path logic.

Skipped gracefully when Node (`npx`) is not on PATH — CI machines without
Node still get a green run, but local dev + GitHub Actions CI (where
Node 22 is installed by the matrix template's setup-node step) exercise
the real path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_hygiene import is_ci

# CI-discipline gate (ADR-044 / ADR-045):
# - Local dev (CI unset / "false"): skip the module as before.
# - CI (CI=truthy): hard-fail the module so missing toolchain is loud.
#
# Module-level pytest.fail() is undocumented but works in practice: it
# raises _pytest.outcomes.Failed which pytest treats as a collection
# error and reports as a failure with the message. The exit code is
# non-zero and the test job fails — which is the intent.
if shutil.which("npx") is None:
    _msg = (
        "npx not on PATH — Vitest template verification requires Node 22+. "
        "Install in CI via actions/setup-node@v4 (see "
        "shared/templates/github-actions/ci-*.yml.template)."
    )
    if is_ci():
        # Module-level fail = collection error (non-zero exit). Acceptable.
        pytest.fail(_msg, pytrace=False)
    pytest.skip(_msg, allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "shared" / "templates"
SOURCE_TEMPLATE = TEMPLATE_DIR / "path-helpers.ts.template"
TEST_TEMPLATE = TEMPLATE_DIR / "path-helpers.test.ts.template"


@pytest.fixture(scope="module")
def vitest_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a minimal Vitest project that imports the two templates.

    Module-scoped so the npm install runs once for all assertions.
    """
    project = tmp_path_factory.mktemp("path_helpers_vitest")

    # Copy the two templates as real .ts files.
    shutil.copyfile(SOURCE_TEMPLATE, project / "path-helpers.ts")
    shutil.copyfile(TEST_TEMPLATE, project / "path-helpers.test.ts")

    # Minimal package.json with vitest pinned to a stable major version.
    package_json = {
        "name": "shipwright-path-helpers-vitest-empirical",
        "version": "0.0.0",
        "private": True,
        "type": "module",
        "scripts": {"test": "vitest run --no-coverage"},
        "devDependencies": {
            "vitest": "^3.0.0",
            "typescript": "^5.0.0",
        },
    }
    (project / "package.json").write_text(
        json.dumps(package_json, indent=2), encoding="utf-8"
    )

    # Minimal tsconfig — Vitest can handle TS without an explicit config
    # but having one keeps the test self-contained.
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "strict": True,
            "esModuleInterop": True,
            "skipLibCheck": True,
        },
        "include": ["*.ts"],
    }
    (project / "tsconfig.json").write_text(
        json.dumps(tsconfig, indent=2), encoding="utf-8"
    )

    # Install dependencies. Use --silent to keep test output readable;
    # subprocess raises on non-zero exit so installation failures surface.
    install = subprocess.run(
        ["npm", "install", "--silent", "--no-audit", "--no-fund"],
        cwd=project,
        capture_output=True,
        text=True,
        shell=True,  # Windows: npm.cmd shim resolves via shell PATH
    )
    if install.returncode != 0:
        # AC-3: npm install failures are real errors. Local dev: skip so
        # broken dev setups don't block local pytest. CI: hard-fail so
        # environment regressions surface in the PR run.
        _fail_msg = (
            f"npm install failed (exit {install.returncode}); "
            f"stderr tail: {install.stderr[-500:]!r}. In CI: this is a "
            f"real environment regression — check the cache step and the "
            f"setup-node@v4 action versions in ci-*.yml.template."
        )
        if is_ci():
            pytest.fail(_fail_msg, pytrace=False)
        pytest.skip(_fail_msg)

    return project


@pytest.mark.slow  # subprocess + npm install — exclude from default fast runs
def test_path_helpers_vitest_passes(vitest_project: Path) -> None:
    """Run the path-helpers.test.ts suite and assert exit 0 + tests > 0."""
    result = subprocess.run(
        ["npx", "vitest", "run", "--reporter=json"],
        cwd=vitest_project,
        capture_output=True,
        text=True,
        shell=True,  # Windows: npx.cmd shim resolves via shell PATH
        timeout=180,
    )

    assert result.returncode == 0, (
        f"Vitest failed (exit {result.returncode}).\n"
        f"stdout tail: {result.stdout[-1500:]}\n"
        f"stderr tail: {result.stderr[-1500:]}"
    )

    # Reporter writes JSON to stdout — parse it to confirm > 0 tests ran.
    # External-review #O5 + F0.5 fail-closed condition: tests_run == 0
    # is regression-equivalent to "no test".
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Vitest sometimes prefixes the JSON with log lines — find the
        # first `{` and try again.
        first_brace = result.stdout.find("{")
        if first_brace == -1:
            pytest.fail(
                f"Vitest produced no JSON output; stdout: {result.stdout[:2000]!r}"
            )
        report = json.loads(result.stdout[first_brace:])

    num_tests = report.get("numTotalTests", 0)
    num_passed = report.get("numPassedTests", 0)

    assert num_tests >= 15, (
        f"Expected at least 15 tests in path-helpers suite (Windows-shaped, "
        f"POSIX-shaped, edge-cases, regression), got {num_tests}."
    )
    assert num_passed == num_tests, (
        f"All tests must pass: {num_passed}/{num_tests}.\n"
        f"Report: {json.dumps(report, indent=2)[:2000]}"
    )
