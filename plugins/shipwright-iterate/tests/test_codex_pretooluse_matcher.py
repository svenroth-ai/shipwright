"""Tests for ``codex_pretooluse_matcher.py`` (R2 — AC1a). Split out of
``codex_pretooluse_gate.py`` (bloat gate, 2026-09-22) alongside the module
itself -- this file exercises the pure ``decide()``/tokenization logic
directly, independent of the hook's I/O and activation-record wiring
(covered by ``test_codex_pretooluse_denial.py`` /
``test_codex_pretooluse_tokenization.py`` via ``handle_payload``)."""

from __future__ import annotations

import sys
from pathlib import Path

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "codex_pretooluse_matcher.py"
)
sys.path.insert(0, str(HOOK_SCRIPT.parent))
from codex_pretooluse_matcher import (  # noqa: E402
    _basename,
    _bash_command_matches_setup,
    _is_bare_cd,
    _segments,
    _unquote,
    decide,
)


class TestBasename:
    """`PureWindowsPath`-backed, so these assertions hold on every host --
    unlike `pathlib.Path(...).name`, which only split on `\\` on Windows
    itself (external review, block: this exact gap denied a valid
    Windows-form path on Linux CI while passing locally on a Windows dev
    box)."""

    def test_windows_backslash_path_yields_basename(self):
        assert _basename("C:\\repo\\shared\\scripts\\tools\\setup_iterate_worktree.py") == (
            "setup_iterate_worktree.py"
        )

    def test_posix_forward_slash_path_yields_basename(self):
        assert _basename("shared/scripts/tools/setup_iterate_worktree.py") == (
            "setup_iterate_worktree.py"
        )

    def test_bare_name_is_unchanged(self):
        assert _basename("setup_iterate_worktree.py") == "setup_iterate_worktree.py"


class TestUnquote:
    def test_strips_matching_double_quotes(self):
        assert _unquote('"a b"') == "a b"

    def test_strips_matching_single_quotes(self):
        assert _unquote("'a b'") == "a b"

    def test_leaves_unquoted_token_alone(self):
        assert _unquote("plain") == "plain"

    def test_leaves_mismatched_quote_alone(self):
        assert _unquote('"unbalanced') == '"unbalanced'


class TestSegments:
    def test_no_operator_is_one_segment(self):
        assert _segments(["uv", "run", "x.py"]) == [["uv", "run", "x.py"]]

    def test_splits_on_and_and(self):
        assert _segments(["cd", "x", "&&", "ls"]) == [["cd", "x"], ["ls"]]

    def test_splits_on_semicolon(self):
        assert _segments(["a", ";", "b"]) == [["a"], ["b"]]


class TestIsBareCd:
    def test_bare_cd_is_true(self):
        assert _is_bare_cd(["cd", "/some/path"]) is True

    def test_cd_with_extra_arg_is_false(self):
        assert _is_bare_cd(["cd", "/some/path", "extra"]) is False

    def test_non_cd_is_false(self):
        assert _is_bare_cd(["ls", "-la"]) is False


class TestBashCommandMatchesSetup:
    def test_direct_invocation_matches(self):
        assert _bash_command_matches_setup({"command": "uv run setup_iterate_worktree.py"}) is True

    def test_non_dict_tool_input_does_not_match(self):
        assert _bash_command_matches_setup("not a dict") is False

    def test_missing_command_key_does_not_match(self):
        assert _bash_command_matches_setup({}) is False

    def test_blank_command_does_not_match(self):
        assert _bash_command_matches_setup({"command": "   "}) is False

    def test_unmatched_quote_does_not_raise_and_does_not_match(self):
        assert _bash_command_matches_setup({"command": 'echo "unterminated'}) is False

    def test_redirection_to_arbitrary_file_denies(self):
        # external review, glm medium: a trailing `>` isn't a shell
        # operator this module split segments on, so this used to stay a
        # single matching segment and get wrongly allowed.
        assert _bash_command_matches_setup(
            {"command": "uv run setup_iterate_worktree.py > ~/.bashrc"}
        ) is False

    def test_input_redirection_denies(self):
        assert _bash_command_matches_setup(
            {"command": "uv run setup_iterate_worktree.py < /etc/passwd"}
        ) is False

    def test_subshell_grouping_denies(self):
        assert _bash_command_matches_setup(
            {"command": "(uv run setup_iterate_worktree.py)"}
        ) is False

    def test_uv_run_value_flag_before_target_still_matches(self):
        # external review, glm medium: the flag-skip loop previously
        # consumed only the flag token, not its value, so `.` landed in
        # the target position and this was wrongly DENIED.
        assert _bash_command_matches_setup(
            {"command": "uv run --project-root . setup_iterate_worktree.py"}
        ) is True

    def test_uv_run_multiple_value_flags_before_target_still_matches(self):
        assert _bash_command_matches_setup(
            {"command": "uv run --python 3.11 --directory . setup_iterate_worktree.py"}
        ) is True


class TestDecide:
    def test_bash_class_delegates_to_matcher(self):
        assert decide("Bash", {"command": "uv run setup_iterate_worktree.py"}) is True
        assert decide("Bash", {"command": "rm -rf /"}) is False

    def test_unrecognized_class_denies_by_default(self):
        assert decide("SomeOtherTool", {}) is False
