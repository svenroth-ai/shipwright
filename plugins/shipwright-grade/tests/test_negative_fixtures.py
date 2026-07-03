"""Negative / failure-mode fixtures (GPT #13): graceful n/a, never a crash."""

from __future__ import annotations

from pathlib import Path

from grade_inputs_projector import grade_context
from render_markdown import render_markdown
from render_terminal import render_terminal
from repo_context import RepoContext
from resolve_target import resolve_target


def _grade(repo: Path):
    return grade_context(RepoContext(resolve_target(str(repo))))


class TestGracefulDegradation:
    def test_bare_repo_is_not_gradeable_not_a_crash(self, bare_repo: Path):
        model = _grade(bare_repo)
        assert model.gradeable is False
        assert model.grade == "?"

    def test_empty_git_repo_is_not_gradeable(self, empty_git_repo: Path):
        model = _grade(empty_git_repo)
        assert model.gradeable is False

    def test_shallow_repo_still_grades(self, shallow_repo: Path):
        model = _grade(shallow_repo)
        assert model.gradeable is True

    def test_huge_and_binary_files_do_not_crash(self, huge_binary_repo: Path):
        ctx = RepoContext(resolve_target(str(huge_binary_repo)))
        # read_text is bounded by the per-file byte cap.
        assert len(ctx.read_text("big.txt")) <= ctx.caps.max_bytes_per_file
        model = grade_context(ctx)
        assert model.grade in {"A", "B", "C", "D", "F", "?"}


class TestHostileRepoIsSanitizedEndToEnd:
    def test_terminal_output_has_no_control_sequences(self, hostile_repo: Path):
        model = _grade(hostile_repo)
        out = render_terminal(model)
        assert "\x1b" not in out       # no ANSI/ESC
        assert "\x07" not in out       # no BEL
        assert chr(0x202E) not in out  # no bidi override
        assert chr(0x202C) not in out

    def test_markdown_output_has_no_control_sequences(self, hostile_repo: Path):
        out = render_markdown(_grade(hostile_repo))
        assert "\x1b" not in out
        assert chr(0x202E) not in out
