"""Tests for git_exec — the hardened, bounded, read-only git runner."""

from __future__ import annotations

from pathlib import Path

from git_exec import run_git


class TestRunGit:
    def test_reads_head_from_a_repo(self, well_run_repo: Path):
        rc, out = run_git(["rev-parse", "HEAD"], well_run_repo)
        assert rc == 0
        assert len(out.strip()) == 40

    def test_bounded_read_caps_output(self, well_run_repo: Path):
        rc, out = run_git(
            ["log", "--format=%H"], well_run_repo, max_bytes=10)
        assert len(out) <= 10

    def test_non_repo_returns_nonzero(self, tmp_path: Path):
        rc, out = run_git(["rev-parse", "HEAD"], tmp_path)
        assert rc != 0

    def test_grades_repo_with_foreign_ownership_config(self, well_run_repo: Path):
        # safe.directory=* is passed, so a rev-parse never trips "dubious
        # ownership" even if the target were owned by another user.
        from git_exec import _HARDENING
        assert "safe.directory=*" in _HARDENING
        assert "core.fsmonitor=false" in _HARDENING
