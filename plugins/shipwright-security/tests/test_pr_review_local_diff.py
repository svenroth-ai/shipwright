"""Tests for `pr_review_local`'s pure diff-building functions.

`main()` orchestration (`pr_review.py --base`/`--diff-file`) lives in
`test_pr_review_local_preflight.py`; split apart to keep both files under the
source-size guideline — see `_pr_review_local_fixtures.py`'s docstring.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_local  # noqa: E402

from _pr_review_local_fixtures import _GIT_ENV, _git, _repo_with_branch_history  # noqa: E402


class TestResolveDiffMode:

    def test_ci_mode_valid(self):
        local_mode, error = pr_review_local.resolve_diff_mode(42, "o/r", None, None)
        assert (local_mode, error) == (False, "")

    def test_local_mode_via_base_valid(self):
        local_mode, error = pr_review_local.resolve_diff_mode(None, None, "origin/main", None)
        assert (local_mode, error) == (True, "")

    def test_local_mode_via_diff_file_valid(self):
        local_mode, error = pr_review_local.resolve_diff_mode(
            None, None, None, Path("x.diff"))
        assert (local_mode, error) == (True, "")

    def test_pr_number_without_repo_errors(self):
        _, error = pr_review_local.resolve_diff_mode(42, None, None, None)
        assert "together" in error

    def test_ci_and_local_combined_errors(self):
        _, error = pr_review_local.resolve_diff_mode(42, "o/r", "origin/main", None)
        assert "cannot be combined" in error

    def test_base_and_diff_file_combined_errors(self):
        _, error = pr_review_local.resolve_diff_mode(
            None, None, "origin/main", Path("x.diff"))
        assert "exactly one" in error

    def test_neither_mode_errors(self):
        _, error = pr_review_local.resolve_diff_mode(None, None, None, None)
        assert "exactly one" in error

    def test_empty_diff_file_path_is_not_a_valid_source(self):
        # argparse(type=Path)("") -> Path(".") -- truthy, so `if s` alone
        # would wrongly accept it (external review, 2026-09-12).
        _, error = pr_review_local.resolve_diff_mode(None, None, None, Path(""))
        assert "exactly one" in error


class TestListDiffPaths:

    def test_extracts_every_header_in_order(self):
        diff = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n+1\n"
                "diff --git a/y.py b/y.py\n--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n+2\n")
        assert pr_review_local.list_diff_paths(diff) == ["x.py", "y.py"]

    def test_empty_diff_returns_empty_list(self):
        assert pr_review_local.list_diff_paths("") == []


class TestReadDiffFile:

    def test_reads_valid_utf8(self, tmp_path):
        p = tmp_path / "x.diff"
        p.write_bytes("diff --git a/x b/x\n+é\n".encode("utf-8"))
        assert "diff --git a/x b/x" in pr_review_local.read_diff_file(p)

    def test_invalid_utf8_bytes_are_replaced_not_raised(self, tmp_path):
        p = tmp_path / "x.diff"
        p.write_bytes(b"diff --git a/x b/x\n+\xff\xfe\n")
        text = pr_review_local.read_diff_file(p)
        assert "diff --git a/x b/x" in text
        assert "�" in text  # the replacement character, not an exception


class TestBuildLocalDiff:

    def test_includes_feature_commit_and_untracked_excludes_unrelated_main(self, tmp_path):
        _repo_with_branch_history(tmp_path)
        diff, error = pr_review_local.build_local_diff(tmp_path, "main")
        assert error == ""
        assert "feature.py" in diff          # committed on the branch
        assert "untracked.py" in diff         # constraint (5): untracked included
        assert "shared.py" not in diff        # constraint (4): main-only commit excluded

    def test_never_touches_the_real_index_or_head(self, tmp_path):
        _repo_with_branch_history(tmp_path)
        status_before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(tmp_path), env=_GIT_ENV,
            capture_output=True, text=True, check=True).stdout
        pr_review_local.build_local_diff(tmp_path, "main")
        status_after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(tmp_path), env=_GIT_ENV,
            capture_output=True, text=True, check=True).stdout
        assert status_before == status_after  # untracked.py still untracked, nothing staged

    def test_diff_invocation_disables_ext_diff_and_textconv(self, tmp_path, monkeypatch):
        # A diff/textconv driver is configured via .gitattributes and could
        # otherwise run an arbitrary local command while comparing blobs.
        _repo_with_branch_history(tmp_path)
        seen_argv = []
        real_run = subprocess.run

        def spy(argv, **kwargs):
            seen_argv.append(argv)
            return real_run(argv, **kwargs)

        monkeypatch.setattr(pr_review_local.subprocess, "run", spy)
        pr_review_local.build_local_diff(tmp_path, "main")
        diff_calls = [a for a in seen_argv if len(a) > 3 and a[3] == "diff"]
        assert diff_calls, "expected a git diff invocation"
        assert "--no-ext-diff" in diff_calls[0]
        assert "--no-textconv" in diff_calls[0]

    def test_unresolvable_base_ref_returns_error_not_raise(self, tmp_path):
        _git(tmp_path, "init", "-q", "-b", "main")
        (tmp_path / "f.py").write_text("x = 1\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "base")
        diff, error = pr_review_local.build_local_diff(tmp_path, "origin/does-not-exist")
        assert diff == ""
        assert error != ""
