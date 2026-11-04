"""F0.5 ``surface=native`` - refusals, and the production-time gate (#989).

``native`` must never be a way around the browser run: only UI that provably lies in a native
package may use it. Accepted evidence: ``test_surface_native.py``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest  # noqa: E402

from _cascade_trigger_fixtures import git, hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import (  # noqa: E402
    check,
    cli_block,
    commit,
    land_branch,
    playwright,
    stage,
    write_entry,
)
from _surface_native_fixtures import (  # noqa: E402
    APP,
    FILES,
    NATIVE_PKG,
    STOCK_EXPO_PKG,
    UNIVERSAL_PKG,
    WEB_PKG,
    jest_json,
    native_block,
    native_repo,
    stage_native,
)
from surface_verification import VALID_SURFACES, parse_tests_run  # noqa: E402
from tools.verifiers import _surface_evidence  # noqa: E402
from tools.verifiers._surface_native import native_packages  # noqa: E402
from tools.verifiers.surface_check import SURFACES  # noqa: E402

# --- native must not be a way around the browser ------------------------------------------


@pytest.mark.covers("FR-01.11/AC07")
def test_a_web_file_in_the_same_diff_refuses_native_and_names_it(tmp_path):
    root, sha = native_repo(tmp_path, {"apps/web/package.json": WEB_PKG, "apps/web/src/Page.tsx": "x\n"})
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "apps/web/src/Page.tsx" in result.detail and "--surface web" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("pkg", [
    UNIVERSAL_PKG,  # react-dom without react-native-web: plain React web
    json.dumps({"dependencies": {"expo": "~52", "next": "15"}}),
    json.dumps({"devDependencies": {"react-native": "0.76", "vite": "6"}}),
    json.dumps({"dependencies": {"react-native": "0.76", "@remix-run/react": "2"}}),
    json.dumps({"dependencies": {"react-native": "0.76", "react-native-web": "0.19", "react-scripts": "5"}}),
    json.dumps({"devDependencies": {"expo": "52", "webpack": "5"}}),
    json.dumps({"dependencies": {"expo": "52", "@sveltejs/kit": "2"}}),
    json.dumps({"dependencies": {"expo": "52", "nuxt": "3"}}),
    json.dumps({"name": "no-rn", "dependencies": {"react": "19"}}),
    "{not json",
    "[]",
])
def test_a_package_that_is_not_native_is_refused(tmp_path, pkg):
    root, sha = make_repo(tmp_path, {f"{APP}/package.json": pkg, f"{APP}/src/Photo.tsx": "x\n"})
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "not in a native package" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_the_stock_expo_template_is_native(tmp_path):
    root, sha = make_repo(tmp_path, {f"{APP}/package.json": STOCK_EXPO_PKG, f"{APP}/src/Photo.tsx": "x\n",
                                      f"{APP}/src/Photo.test.tsx": "x\n"})
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("web_file", ["Photo.web.tsx", "index.html", "Card.vue", "page.jinja2"])
def test_a_web_only_file_in_a_native_package_is_refused(tmp_path, web_file):
    root, sha = native_repo(tmp_path, {f"{APP}/src/{web_file}": "x\n"})
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and web_file in result.detail and "web-only" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_every_touched_native_package_needs_its_own_passing_tests(tmp_path):
    other = {"apps/kiosk/package.json": NATIVE_PKG, "apps/kiosk/src/Screen.tsx": "x\n",
             "apps/kiosk/src/Screen.test.tsx": "x\n"}
    root, sha = native_repo(tmp_path, other)
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "apps/kiosk" in result.detail
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"],
                                             "apps/kiosk/src/Screen.test.tsx": ["c"]}))
    write_entry(root, native_block(tests_run=3))
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
def test_jest_cases_with_one_title_in_two_describes_each_count(tmp_path):
    # Jest prints "Tests: 4 passed"; the reader keys results by file::title, so two
    # `renders` cases fold into one id. tests_run must still be backed.
    root, sha = native_repo(tmp_path)
    write_entry(root, native_block(tests_run=4))
    report = {"testResults": [{"name": str(root / APP / "src/Photo.test.tsx"), "assertionResults": [
        {"title": "renders", "status": "passed"}, {"title": "renders", "status": "passed"},
        {"title": "blurs", "status": "passed"}, {"title": "blurs", "status": "passed"}]}]}
    stage_native(root, jest=report)
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
def test_a_ui_file_with_no_package_json_above_it_is_refused(tmp_path):
    root, sha = make_repo(tmp_path, {"loose/Photo.tsx": "x\n"})
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {"loose/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "loose/Photo.tsx" in result.detail and "no package.json" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_package_that_becomes_native_in_the_same_diff_is_refused(tmp_path):
    # The package.json the diff is judged by must not be one the diff itself just rewrote.
    root, _ = make_repo(tmp_path, {f"{APP}/package.json": WEB_PKG, f"{APP}/src/Photo.tsx": "x\n"})
    land_branch(root)
    commit(root, f"{APP}/src/Photo.tsx", "changed\n", "edit the screen")  # a UI change in the diff ...
    sha = commit(root, f"{APP}/package.json", NATIVE_PKG, "make it native")  # ... and the flip that licenses it
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "cannot rewrite the declaration" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_cli_stays_refused_for_a_native_ui_diff_and_the_message_offers_native(tmp_path):
    root, sha = make_repo(tmp_path, FILES)
    write_entry(root, cli_block())
    stage(root)
    result = check(root, sha)
    assert result.is_failure and "touches UI" in result.detail and "--surface native" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_native_without_any_ui_in_the_diff_is_refused(tmp_path):
    root, sha = make_repo(tmp_path, {"tests/test_a.py": "def test_x():\n    pass\n"})
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "touches no UI" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_web_still_needs_playwright_and_jest_results_do_not_replace_it(tmp_path):
    root, sha = make_repo(tmp_path, {"client/src/Board.tsx": "x\n"})
    write_entry(root, {**cli_block(tests_run=2, runner="npx playwright test"), "surface": "web"})
    stage_native(root, jest=jest_json(root, {"client/src/Board.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "playwright" in result.detail
    stage(root, pw=playwright(["drag a card", "drop a card"]))
    assert check(root, sha).ok


# --- the production-time gate ---------------------------------------------------------------


@pytest.mark.covers("FR-01.11/AC07")
def test_the_orchestrator_accepts_native_and_reads_jests_summary():
    assert "native" in VALID_SURFACES
    summary = "Test Suites: 1400 passed, 1400 total\nTests:       4697 passed, 4697 total\nTime: 80 s\n"
    assert parse_tests_run(summary, "native") == 4697
    assert parse_tests_run("Tests:       2 failed, 4695 passed, 4697 total\n", "native") == 4697


@pytest.mark.covers("FR-01.11/AC07")
def test_jests_other_summary_lines_are_other_units():
    # more snapshots and more suites than tests must not inflate tests_run
    summary = ("Test Suites: 9 passed, 9 total\nTests:       40 passed, 40 total\n"
               "Snapshots:   120 passed, 120 total\nTime:        3 s\n")
    assert parse_tests_run(summary, "native") == 40
    assert parse_tests_run("\x1b[1mTests:\x1b[22m       \x1b[32m7 passed\x1b[39m, 7 total\n", "native") == 7


@pytest.mark.covers("FR-01.11/AC07")
def test_the_two_surface_lists_and_the_two_evidence_vocabularies_stay_apart():
    assert set(SURFACES) == set(VALID_SURFACES)
    kinds, labels = _surface_evidence.SURFACE_REPORT_KINDS, _surface_evidence.SURFACE_RUNNERS
    assert "junit" in kinds["native"] and "junit" not in labels["native"]  # a JUnit RESULT is labelled pytest
    assert "pytest" in labels["native"] and "pytest" not in kinds["native"]
    assert kinds["web"] == labels["web"] == {"playwright"}


@pytest.mark.covers("FR-01.11/AC07")
def test_a_nested_package_json_added_by_the_diff_cannot_relabel_a_web_file(tmp_path):
    # apps/web is a Next app; the diff edits its page AND drops a native-looking package.json next to it.
    root, _ = make_repo(tmp_path, {"apps/web/package.json": WEB_PKG, "apps/web/src/Page.tsx": "x\n"})
    land_branch(root)
    commit(root, "apps/web/src/Page.tsx", "changed\n", "edit the page")
    sha = commit(root, "apps/web/src/package.json", NATIVE_PKG, "nested manifest")
    write_entry(root, native_block())
    stage_native(root, jest=jest_json(root, {"apps/web/src/Page.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "cannot rewrite the declaration" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_deleting_a_nested_web_package_json_cannot_hand_its_files_to_the_native_root(tmp_path):
    root, _ = make_repo(tmp_path, {f"{APP}/package.json": NATIVE_PKG, f"{APP}/web/package.json": WEB_PKG,
                                    f"{APP}/web/Screen.tsx": "x\n"})
    land_branch(root)
    commit(root, f"{APP}/web/Screen.tsx", "changed\n", "edit the web screen")
    git(root, "rm", "-q", f"{APP}/web/package.json")
    git(root, "commit", "-q", "-m", "drop the nested manifest")
    sha = git(root, "rev-parse", "HEAD")
    write_entry(root, native_block())
    time.sleep(1.1)  # the staging guard dates a deletion by its commit, to the second: the report must be newer
    stage_native(root, jest=jest_json(root, {f"{APP}/web/Screen.test.tsx": ["a", "b"]}))
    result = check(root, sha)
    assert result.is_failure and "cannot rewrite the declaration" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_verified_commit_that_is_the_merge_base_has_nothing_to_compare_with(tmp_path):
    root, sha = native_repo(tmp_path)
    scope, why = native_packages(root, sha, sha, [f"{APP}/src/Photo.tsx"])
    assert scope is None and "merge-base" in why


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("foreign", ["C:/other/checkout/src/Photo.test.tsx", "C:\\other\\checkout\\src\\Photo.test.tsx",
                                      "//server/share/src/Photo.test.tsx"])
def test_a_report_path_from_another_machine_does_not_count_for_a_repo_root_package(tmp_path, foreign):
    # root == "" accepts every project-relative path, so a foreign absolute path must be refused on its own
    root, sha = make_repo(tmp_path, {"package.json": NATIVE_PKG, "src/Photo.tsx": "x\n"})
    write_entry(root, native_block())
    report = {"testResults": [{"name": foreign, "assertionResults": [
        {"title": "a", "status": "passed"}, {"title": "b", "status": "passed"}]}]}
    stage_native(root, jest=report)
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_jest_staged_as_json_and_as_junit_is_counted_once(tmp_path):
    # two formats, two id shapes (jest-junit prefixes the describe title): 2 tests must not read as 4
    root, sha = native_repo(tmp_path)
    junit = [(APP, [("src/Photo.test.tsx", "Photo a", "pass"), ("src/Photo.test.tsx", "Photo b", "pass")])]
    jest = jest_json(root, {f"{APP}/src/Photo.test.tsx": ["a", "b"]})
    write_entry(root, native_block(tests_run=4))
    stage_native(root, jest=jest, junit=junit)
    result = check(root, sha)
    assert result.is_failure and "only 2 passing native" in result.detail
    write_entry(root, native_block(tests_run=2))
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("bad", [["not a dict"], [{"name": "x", "assertionResults": ["str"]}]])
def test_a_malformed_jest_report_is_unread_evidence_not_a_crash(tmp_path, bad):
    root, sha = native_repo(tmp_path)
    stage_native(root, jest={"testResults": bad})
    result = check(root, sha)
    assert result.is_failure
