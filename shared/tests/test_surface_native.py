"""F0.5 ``surface=native`` - accepted evidence and what counts as native evidence (#989).

A native-only app (Expo / React Native, no browser build) finishes F0.5 with the Jest results it
really has. Every case runs against a real git repo and evidence staged by the production
emit-side (``_surface_native_fixtures``). Refusals and the production-time gate:
``test_surface_native_gates.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import git, hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import RUN, check, commit, land_branch, stage, write_entry  # noqa: E402
from _surface_native_fixtures import (  # noqa: E402
    APP,
    NATIVE_PKG,
    jest_json,
    native_block,
    native_repo,
    stage_native,
)
from lib import evidence_drop  # noqa: E402

# --- accepted ------------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11/AC07")
def test_native_ui_diff_passes_with_jest_json_under_the_package(tmp_path):
    root, sha = native_repo(tmp_path)
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["renders", "blurs"]}))
    result = check(root, sha)
    assert result.ok, result.detail
    assert "surface=native" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_native_ui_diff_passes_with_junit_that_carries_a_file_attribute(tmp_path):
    root, sha = native_repo(tmp_path)
    # package-relative `file`, rebased by the report's base - the shape a runner started in the package emits
    stage_native(root, junit=[(APP, [("src/Photo.test.tsx", "renders", "pass"), ("src/Photo.test.tsx", "blurs", "pass")])])
    result = check(root, sha)
    assert result.ok, result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_new_screen_in_an_existing_native_package_is_accepted(tmp_path):
    # The package is declared (and native) at the merge-base; the diff only adds a screen to it.
    root, _ = make_repo(tmp_path, {f"{APP}/package.json": NATIVE_PKG, f"{APP}/src/Old.tsx": "x\n"})
    land_branch(root)
    commit(root, f"{APP}/src/NewScreen.test.tsx", "x\n", "its test")
    sha = commit(root, f"{APP}/src/NewScreen.tsx", "x\n", "a new screen")
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/NewScreen.test.tsx": ["a", "b"]}))
    assert check(root, sha).ok


# --- evidence must come from a JS/TS test inside the touched native package -----------------


@pytest.mark.covers("FR-01.11/AC07")
def test_junit_without_a_file_attribute_is_not_native_evidence(tmp_path):
    root, sha = native_repo(tmp_path)
    # the default jest-junit shape: classname is the describe title, so the id is not a path in the package
    path = root.parent / "reports" / "j.xml"
    path.parent.mkdir(exist_ok=True)
    path.write_text('<testsuites><testsuite><testcase classname="Photo renders" name="a"/>'
                    '<testcase classname="Photo renders" name="b"/></testsuite></testsuites>', encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=RUN, head_commit=git(root, "rev-parse", "main"), junit_reports=[("", path)])
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_python_junit_never_satisfies_native_even_inside_the_package(tmp_path):
    # Pins the JS/TS extension filter: without it these pass, because the tests sit under the package root.
    root, sha = native_repo(tmp_path)
    stage(root, cases={f"{APP.replace('/', '.')}.tests.test_a::test_x": "pass",
                       f"{APP.replace('/', '.')}.tests.test_a::test_y": "pass"})
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("other", ["packages/api/src/user.test.ts", "apps/mobile-admin/src/Photo.test.tsx"])
def test_results_from_another_package_do_not_count(tmp_path, other):
    # `apps/mobile-admin` pins path-aware containment: it starts with the string `apps/mobile`.
    root, sha = native_repo(tmp_path)
    stage_native(root, jest=jest_json(root, {other: ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_traversal_in_a_reported_file_path_does_not_borrow_the_package(tmp_path):
    root, sha = native_repo(tmp_path)
    stage_native(root, junit=[(APP, [("../../packages/api/src/user.test.ts", "a", "pass"),
                                      ("../../packages/api/src/user.test.ts", "b", "pass")])])
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_only_the_filtered_results_back_tests_run(tmp_path):
    # 2 passing in the package + 10 elsewhere in the same report: tests_run=5 must not be backed by the 12.
    root, sha = native_repo(tmp_path)
    write_entry(root, native_block(tests_run=5))
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"],
                                             "packages/api/src/user.test.ts": [f"t{i}" for i in range(10)]}))
    result = check(root, sha)
    assert result.is_failure and "only 2 passing native" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_failing_native_test_contradicts_exit_code_zero(tmp_path):
    root, sha = native_repo(tmp_path)
    stage_native(root, junit=[(APP, [("src/Photo.test.tsx", "a", "pass"), ("src/Photo.test.tsx", "b", "fail")])])
    result = check(root, sha)
    assert result.is_failure and "failing" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_native_evidence_is_stale_for_another_run(tmp_path):
    root, sha = native_repo(tmp_path)
    reports = root.parent / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "jest.json").write_text(json.dumps(jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]})), encoding="utf-8")
    evidence_drop.stage_reports(root, run_id="iterate-2026-01-01-someone-else",
                                head_commit=git(root, "rev-parse", "main"), vitest=reports / "jest.json")
    result = check(root, sha)
    assert result.is_failure and "stale" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_new_expo_app_in_a_monorepo_with_a_bare_workspace_root_is_accepted(tmp_path):
    # The ordinary first iterate of an Expo app: the root package.json exists at the base and owns no framework.
    root, _ = make_repo(tmp_path, {"package.json": json.dumps({"name": "mono", "private": True, "workspaces": ["apps/*"]})})
    land_branch(root)
    commit(root, f"{APP}/package.json", NATIVE_PKG, "new expo app")
    commit(root, f"{APP}/src/Photo.test.tsx", "x\n", "its test")
    sha = commit(root, f"{APP}/src/Photo.tsx", "x\n", "its first screen")
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.ok, result.detail
