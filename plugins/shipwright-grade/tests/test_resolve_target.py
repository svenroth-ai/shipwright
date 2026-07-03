"""Tests for resolve_target — the input seam."""

from __future__ import annotations

from pathlib import Path

import pytest
from resolve_target import ResolvedTarget, TargetError, resolve_target


class TestResolveTarget:
    def test_resolves_a_local_git_repo(self, well_run_repo: Path):
        target = resolve_target(str(well_run_repo))
        assert isinstance(target, ResolvedTarget)
        assert target.is_git is True
        assert target.input_kind == "local_path"
        assert target.local_path == well_run_repo.resolve()

    def test_bare_repo_is_git(self, bare_repo: Path):
        target = resolve_target(str(bare_repo))
        assert target.is_git is True
        assert target.is_bare is True

    def test_shallow_flag_detected(self, shallow_repo: Path):
        target = resolve_target(str(shallow_repo))
        assert target.is_shallow is True

    def test_rejects_non_git_dir(self, non_git_dir: Path):
        with pytest.raises(TargetError, match="not a git repository"):
            resolve_target(str(non_git_dir))

    def test_rejects_missing_path(self, tmp_path: Path):
        with pytest.raises(TargetError, match="does not exist"):
            resolve_target(str(tmp_path / "nope"))

    def test_rejects_file_target(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(TargetError, match="not a directory"):
            resolve_target(str(f))

    def test_url_is_deferred_to_g4(self):
        with pytest.raises(TargetError, match="URL targets are not supported"):
            resolve_target("https://github.com/x/y")

    def test_ssh_url_is_deferred(self):
        with pytest.raises(TargetError, match="URL targets are not supported"):
            resolve_target("git@github.com:x/y.git")

    def test_empty_input_rejected(self):
        with pytest.raises(TargetError, match="empty target"):
            resolve_target("   ")
