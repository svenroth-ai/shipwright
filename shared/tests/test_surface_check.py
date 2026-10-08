"""F11 ``check_surface_verification``: ``surface: none`` is re-derived from the diff, numbers from the evidence.

Every case runs against a real git repo and evidence staged by the production
emit-side (``_surface_check_fixtures``). Detection rules in isolation live in
``test_surface_detect.py``; freshness against trunk merges, consolidation,
strays, retries and the staging guard in ``test_surface_freshness.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import git, hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import (  # noqa: E402
    NONE_BLOCK,
    RUN,
    check,
    cli_block,
    playwright,
    stage,
    write_entry,
)
from tools.verifiers import iterate_checks  # noqa: E402

TEST_FILE = {"tests/test_a.py": "def test_x():\n    pass\n"}


# --- surface: none --------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC07")
def test_none_with_a_closed_code_on_a_prose_only_diff_passes(tmp_path):
    root, sha = make_repo(tmp_path, {"README.md": "words\n", "docs/guide.md": "more\n"})
    write_entry(root, NONE_BLOCK)
    result = check(root, sha)
    assert result.ok, result.detail
    assert "docs-only" in result.detail and "justification recorded" in result.detail
    assert "touches no runnable surface" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_none_without_a_reason_code_fails_even_with_a_justification(tmp_path):
    root, sha = make_repo(tmp_path, {"README.md": "words\n"})
    write_entry(root, {k: v for k, v in NONE_BLOCK.items() if k != "reason_code"})
    result = check(root, sha)
    assert result.is_failure
    assert "reason_code" in result.detail and "--reason-code" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_none_with_a_code_outside_the_vocabulary_fails(tmp_path):
    root, sha = make_repo(tmp_path, {"README.md": "words\n"})
    write_entry(root, {**NONE_BLOCK, "reason_code": "trust me"})
    result = check(root, sha)
    assert result.is_failure and "closed surface_none vocabulary" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize(("path", "kind"), [
    ("server/src/routes/tasks.ts", "api_route"),
    ("client/src/Board.tsx", "ui"),
    ("server/src/sse.ts", "realtime"),
    ("api/openapi.yaml", "message_contract"),
])
def test_none_is_refused_when_the_diff_touches_a_runnable_surface(tmp_path, path, kind):
    root, sha = make_repo(tmp_path, {path: "export const x = 1;\n", "README.md": "w\n"})
    write_entry(root, NONE_BLOCK)
    result = check(root, sha)
    assert result.is_failure
    assert "refused" in result.detail and kind in result.detail and path in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_the_diff_wins_over_the_reason_code(tmp_path):
    root, sha = make_repo(tmp_path, {"server/routes/a.ts": "export const a = 1;\n"})
    write_entry(root, {**NONE_BLOCK, "reason_code": "no-startable-surface"})
    result = check(root, sha)
    assert result.is_failure and "no-startable-surface" in result.detail and "refused" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_none_is_refused_when_only_the_changed_lines_reveal_a_route(tmp_path):
    root, sha = make_repo(tmp_path, {"src/app.py": "@app.post('/login')\ndef login():\n    pass\n"})
    write_entry(root, NONE_BLOCK)
    result = check(root, sha)
    assert result.is_failure and "api_route: src/app.py" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_none_cannot_be_confirmed_when_the_diff_is_unmeasurable(tmp_path):
    root, sha = make_repo(tmp_path, {"README.md": "words\n"}, origin=False, trunk="develop")
    write_entry(root, NONE_BLOCK)
    result = check(root, sha)
    assert result.is_failure and "cannot be confirmed" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_none_fails_closed_outside_a_git_work_tree(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    write_entry(root, NONE_BLOCK)
    result = check(root)
    assert result.is_failure and "not a readable git work tree" in result.detail


# --- surface != none: the staged evidence ----------------------------------------

@pytest.mark.covers("FR-01.11/AC07")
def test_fresh_matching_evidence_passes(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    write_entry(root, cli_block())
    stage(root)
    result = check(root, sha)
    assert result.ok, result.detail
    assert "tests_run=2, exit_code=0" in result.detail and "2 passing" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_absent_evidence_fails(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block())
    result = check(root, sha)
    assert result.is_failure and "absent" in result.detail and "stage_f0_evidence.py" in result.detail
    assert "To repair, re-run this run's tests (F0" in result.detail, "the fix is a test run, not a bare re-stage"


@pytest.mark.covers("FR-01.11/AC07")
def test_evidence_staged_for_another_run_is_stale(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block())
    stage(root, run_id="iterate-2026-01-01-someone-else")
    result = check(root, sha)
    assert result.is_failure and "stale" in result.detail and "someone-else" in result.detail


def _commit(root, rel, text, message):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


@pytest.mark.covers("FR-01.11/AC07")
def test_a_code_commit_after_the_f6_commit_makes_the_evidence_stale(tmp_path):
    root, _ = make_repo(tmp_path, {**TEST_FILE})  # the F6 commit carries the tree F0 tested
    write_entry(root, cli_block())
    stage(root)  # staged at the trunk tip, before F6
    records = _commit(root, ".shipwright/planning/iterate/r/reviews.json", "{}", "chore(review): record")
    assert check(root, records).ok, "a records-only commit must not make evidence stale"
    git(root, "checkout", "-q", "main")
    _commit(root, "other.txt", "x\n", "another unit merged")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "iterate/probe")
    git(root, "merge", "-q", "--no-edit", "main")
    assert check(root, git(root, "rev-parse", "HEAD")).ok, "a merge from the trunk must not make it stale"
    fixed = _commit(root, "src/fix.py", "x = 2\n", "fix: a review finding")
    stale = check(root, fixed)
    assert stale.is_failure and "src/fix.py" in stale.detail and "not what the staged results ran against" in stale.detail
    stage(root, head=fixed)  # re-staged after the fix: fresh again
    assert check(root, fixed).ok


@pytest.mark.covers("FR-01.11/AC07")
def test_a_ui_change_must_be_driven_as_web(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "client/src/Board.tsx": "x\n"})
    write_entry(root, cli_block())
    stage(root)
    result = check(root, sha)
    assert result.is_failure and "touches UI" in result.detail and "--surface web" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_failing_staged_test_contradicts_exit_code_zero(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block())
    stage(root, cases={"tests.test_a::test_x": "pass", "tests.test_a::test_y": "fail"})
    result = check(root, sha)
    assert result.is_failure and "failing" in result.detail and "test_y" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_tests_run_above_the_staged_passes_fails(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block(tests_run=5))
    stage(root, cases={"tests.test_a::test_x": "pass", "tests.test_a::test_y": "skip"})
    result = check(root, sha)
    assert result.is_failure and "tests_run=5" in result.detail and "only 1 passing" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_runner_test_path_with_no_staged_pass_fails(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "tests/test_b.py": "def test_z():\n    pass\n"})
    write_entry(root, cli_block(tests_run=1, runner="uv run pytest tests/test_b.py -q"))
    stage(root)
    result = check(root, sha)
    assert result.is_failure and "tests/test_b.py" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_web_needs_a_staged_playwright_report_and_counts_only_its_results(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "client/src/Board.tsx": "x\n"})
    write_entry(root, {**cli_block(tests_run=2, runner="npx playwright test"), "surface": "web"})
    stage(root)
    junit_only = check(root, sha)
    assert junit_only.is_failure and "playwright" in junit_only.detail
    stage(root, pw=playwright(["drag a card"]))
    one_of_two = check(root, sha)
    assert one_of_two.is_failure and "only 1 passing web" in one_of_two.detail
    stage(root, pw=playwright(["drag a card", "drop a card"]))
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
def test_run_all_checks_hands_the_commit_to_the_surface_check(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block())
    stage(root)
    _commit(root, "src/later.py", "x = 3\n", "fix: after staging")  # HEAD now differs from `sha`
    assert check(root).is_failure, "HEAD carries code the evidence never saw"
    by_name = {r.name: r for r in iterate_checks.run_all_checks(root, RUN, sha)}
    assert by_name["F0.5 surface_verification block valid"].ok, "run_all_checks must verify `sha`, not HEAD"


@pytest.mark.covers("FR-01.11/AC07")
def test_an_edit_after_staging_folded_into_the_f6_commit_is_caught(tmp_path):
    root, _ = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    write_entry(root, cli_block())
    stage(root)  # fingerprints the tree as tested
    (root / "src" / "a.py").write_text("x = 'edited after the tests ran'\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--amend", "--no-edit")
    result = check(root, git(root, "rev-parse", "HEAD"))
    assert result.is_failure and "'src/a.py'" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_the_tested_tree_fingerprint_is_the_working_tree_and_leaves_the_index_alone(tmp_path):
    from lib.worktree_tree import working_tree_id
    root, _ = make_repo(tmp_path, {**TEST_FILE})
    assert working_tree_id(root) == git(root, "rev-parse", "HEAD^{tree}")  # clean: the commit's tree
    (root / "new_untracked.py").write_text("y = 1\n", encoding="utf-8")
    dirty = working_tree_id(root)
    assert dirty != git(root, "rev-parse", "HEAD^{tree}")
    assert "new_untracked.py" in git(root, "ls-tree", "--name-only", dirty)
    assert git(root, "status", "--porcelain") == "?? new_untracked.py", "the real index must be untouched"
    assert working_tree_id(tmp_path / "not-a-repo") is None


@pytest.mark.covers("FR-01.11/AC07")
def test_evidence_without_a_tested_tree_fingerprint_is_stale(tmp_path, monkeypatch):
    from lib import evidence_drop
    monkeypatch.setattr(evidence_drop, "working_tree_id", lambda root: None)
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block())
    stage(root)
    result = check(root, sha)
    assert result.is_failure and "tested_tree" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_none_is_refused_when_a_handler_body_changes_under_an_unchanged_decorator(tmp_path):
    root, _ = make_repo(tmp_path, {"svc/app.py": "@app.get('/tasks')\ndef tasks():\n    return 1\n"})
    sha = _commit(root, "svc/app.py", "@app.get('/tasks')\ndef tasks():\n    return 2\n", "body only")
    write_entry(root, NONE_BLOCK)
    result = check(root, sha)
    assert result.is_failure and "api_route: svc/app.py" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_detected_surface_needs_a_runner_that_names_its_test_files(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "server/routes/tasks.ts": "export const t = 1;\n"})
    write_entry(root, {**cli_block(tests_run=1, runner="curl -s http://localhost:3000/tasks"),
                       "surface": "api"})
    stage(root)
    unrelated = check(root, sha)
    assert unrelated.is_failure and "names no test file" in unrelated.detail
    write_entry(root, {**cli_block(tests_run=1), "surface": "api"})  # runner names tests/test_a.py
    assert check(root, sha).ok
