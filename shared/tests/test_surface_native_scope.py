"""F0.5 ``surface=native`` - what the native scope refuses or ignores (#989 review fixes).

Companion to ``test_surface_native_gates.py`` (kept apart for the file-size cap).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest  # noqa: E402

from _cascade_trigger_fixtures import hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import check, cli_block, commit, land_branch, write_entry  # noqa: E402
from _surface_native_fixtures import (  # noqa: E402
    APP,
    NATIVE_PKG,
    WEB_PKG,
    jest_json,
    native_block,
    native_repo,
    stage_native,
)


@pytest.mark.covers("FR-01.11/AC07")
def test_a_web_package_that_depends_on_the_native_package_refuses_native(tmp_path):
    # solito pattern: apps/next (web) imports the shared screens of apps/mobile, so they also render in a browser
    web = json.dumps({"name": "next-app", "dependencies": {"next": "15", "react": "19", "mobile": "*"}})
    root, sha = native_repo(tmp_path, {"apps/next/package.json": web})
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "web package" in result.detail and "depends on" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_runnable_file_outside_the_native_package_refuses_native(tmp_path):
    # Jest results of the app do not exercise a backend route, so it needs its own surface
    root, sha = native_repo(tmp_path, {"packages/api/routes/user.ts": "x\n"})
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "packages/api/routes/user.ts" in result.detail and "outside" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_result_for_a_file_that_is_not_tracked_does_not_count(tmp_path):
    # a relative Jest path under the app that names no tracked test file is not evidence of anything
    root, sha = native_repo(tmp_path)
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Ghost.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and ("absent" in result.detail or "no passing" in result.detail)


@pytest.mark.covers("FR-01.11/AC07")
def test_expo_router_html_shell_is_web_only(tmp_path):
    root, _ = native_repo(tmp_path)
    land_branch(root)
    sha = commit(root, f"{APP}/app/+html.tsx", "x\n", "the static export shell")
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}), head=sha)
    result = check(root, sha)
    assert result.is_failure and "+html.tsx" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_real_native_diff_still_passes_beside_these_refusals(tmp_path):
    root, sha = native_repo(tmp_path)
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.ok, result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_browser_file_that_pre_dates_any_manifest_cannot_be_claimed_by_a_new_native_one(tmp_path):
    # A manifest-less repo (static site / Django): frontend/app.jsx is a browser file at the base.
    root, _ = make_repo(tmp_path, {"frontend/app.jsx": "x\n"})
    land_branch(root)
    commit(root, "frontend/app.jsx", "changed\n", "edit the page")
    sha = commit(root, "frontend/package.json", NATIVE_PKG, "a native-looking manifest")
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {"frontend/app.test.jsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "cannot rewrite the declaration" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_new_file_in_a_location_a_web_package_owned_cannot_be_claimed_by_a_new_native_manifest(tmp_path):
    root, _ = make_repo(tmp_path, {"apps/web/package.json": WEB_PKG, "apps/web/src/Page.tsx": "x\n"})
    land_branch(root)
    commit(root, "apps/web/src/package.json", NATIVE_PKG, "nested manifest")
    sha = commit(root, "apps/web/src/NewPage.tsx", "x\n", "a new page")
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {"apps/web/src/NewPage.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "web package that owned this location" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_tests_of_a_nested_package_do_not_back_the_package_that_contains_it(tmp_path):
    # apps/mobile/web is its own (web) package; its passing tests are not apps/mobile's evidence
    root, sha = native_repo(tmp_path, {f"{APP}/web/package.json": WEB_PKG, f"{APP}/web/Page.test.tsx": "x\n"})
    stage_native(root, jest=jest_json(root, {f"{APP}/web/Page.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail
    stage_native(root, jest=jest_json(root, {f"{APP}/web/Page.test.tsx": ["a", "b"], f"{APP}/src/Photo.test.tsx": ["c", "d"]}))
    write_entry(root, native_block(tests_run=2))
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
def test_two_packages_in_two_formats_add_up(tmp_path):
    # package A's tests as Jest JSON, package B's as JUnit: 2 + 2 distinct tests back tests_run=4
    root, sha = native_repo(tmp_path, {"apps/kiosk/package.json": NATIVE_PKG, "apps/kiosk/src/Screen.tsx": "x\n",
                                       "apps/kiosk/src/Screen.test.tsx": "x\n"})
    write_entry(root, native_block(tests_run=4))
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}),
                 junit=[("apps/kiosk", [("src/Screen.test.tsx", "c", "pass"), ("src/Screen.test.tsx", "d", "pass")])])
    result = check(root, sha)
    assert result.ok, result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_jest_json_does_not_inflate_a_cli_block_count(tmp_path):
    # the per-assertion Jest count is native-only: a cli block must still fail when its tests_run exceeds
    # the pytest passes, even though a Jest JSON with duplicate titles is also staged
    root, sha = make_repo(tmp_path, {"tests/test_a.py": "def test_x():\n    pass\n"})
    write_entry(root, cli_block(tests_run=5))
    report = {"testResults": [{"name": str(root / "tests/x.test.ts"), "assertionResults": [
        {"title": "same", "status": "passed"}] * 6}]}
    stage_native(root, jest=report)
    result = check(root, sha)
    assert result.is_failure and "tests_run=5" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("pkg", [
    '{"dependencies": {"react-native": "0.76", "react-dom": "19", "react-native-web": "0.19", "@rsbuild/core": "1"}}',
    '{"dependencies": {"react-native": "0.76", "react-dom": "19", "react-native-web": "0.19"}}',  # no expo: a web target
])
def test_react_native_web_without_expo_or_with_other_bundlers_is_web(tmp_path, pkg):
    root, sha = native_repo(tmp_path, {"apps/site/package.json": pkg, "apps/site/src/Page.tsx": "x\n"})
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "apps/site" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("name", ["user+api.ts", "Photo.web.mjs"])
def test_server_and_web_only_expo_files_refuse_native(tmp_path, name):
    root, _ = native_repo(tmp_path)
    land_branch(root)
    sha = commit(root, f"{APP}/app/{name}", "x\n", "a server or web file")
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}), head=sha)
    assert check(root, sha).is_failure


@pytest.mark.covers("FR-01.11/AC07")
def test_a_non_test_script_is_not_native_evidence(tmp_path):
    root, sha = native_repo(tmp_path, {f"{APP}/babel.config.js": "x\n"})
    stage_native(root, jest=jest_json(root, {f"{APP}/babel.config.js": ["a", "b"]}))
    assert check(root, sha).is_failure
