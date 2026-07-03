"""Tests for repo_context — the memoized, capped snapshot."""

from __future__ import annotations

from pathlib import Path

from repo_context import Caps, RepoContext
from resolve_target import resolve_target


def _ctx(repo: Path, **caps) -> RepoContext:
    target = resolve_target(str(repo))
    return RepoContext(target, caps=Caps(**caps)) if caps else RepoContext(target)


class TestSnapshot:
    def test_files_are_lexicographic_and_prune_dot_git(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo)
        assert ctx.files == sorted(ctx.files)
        assert not any(f.startswith(".git/") for f in ctx.files)
        assert "app/api.py" in ctx.files

    def test_test_files_detected(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo)
        assert "tests/test_api.py" in ctx.test_files
        assert ctx.test_file_count >= 1

    def test_has_ci_and_head_sha(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo)
        assert ctx.has_ci is True
        assert len(ctx.head_sha) == 40

    def test_events_projected(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo)
        assert len(ctx.events) == 4
        assert all(e.sha for e in ctx.events)


class TestDeterministicCaps:
    def test_file_cap_truncates(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo, max_files=3)
        assert len(ctx.files) == 3
        assert ctx.truncated_files is True

    def test_commit_cap_truncates_newest_first(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo, max_commits=2)
        assert len(ctx.events) == 2
        assert ctx.events_truncated is True

    def test_read_text_bounded_by_byte_cap(self, well_run_repo: Path):
        ctx = _ctx(well_run_repo, max_bytes_per_file=10)
        assert len(ctx.read_text("app/api.py")) <= 10

    def test_features_truncated_flag_when_file_walk_truncates(self, well_run_repo: Path):
        # A tiny file cap forces truncation → feature inference is a labelled sample.
        assert _ctx(well_run_repo, max_files=3).features_truncated is True
        assert _ctx(well_run_repo).features_truncated is False
