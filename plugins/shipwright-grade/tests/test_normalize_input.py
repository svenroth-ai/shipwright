"""Tests for normalize_input — surrounding-quote stripping at the grader seam.

Mirrors the WebUI ``normalize-fs-path`` fix (shipwright-webui #195): a user who
copies a path via Windows Explorer "Copy as path" (which wraps the value in
literal ``"..."``) or pastes a quoted URL out of a README should still get a
grade, not a hard ``TargetError`` on the stray quote character.
"""

from __future__ import annotations

from pathlib import Path

from normalize_input import strip_surrounding_quotes
from resolve_target import ResolvedTarget, open_target


class TestStripSurroundingQuotes:
    def test_strips_double_quote_pair(self):
        assert strip_surrounding_quotes('"/home/x/repo"') == "/home/x/repo"

    def test_strips_single_quote_pair(self):
        assert strip_surrounding_quotes("'/home/x/repo'") == "/home/x/repo"

    def test_strips_windows_copy_as_path(self):
        # Explorer "Copy as path" yields a double-quoted Windows path verbatim.
        assert (
            strip_surrounding_quotes(r'"C:\Users\marcel\Command Center"')
            == r"C:\Users\marcel\Command Center"
        )

    def test_preserves_inner_apostrophe(self):
        # A real path may contain an apostrophe; only the SURROUNDING pair goes.
        assert strip_surrounding_quotes("/home/o'brien/repo") == "/home/o'brien/repo"

    def test_double_quoted_path_keeps_inner_apostrophe(self):
        assert strip_surrounding_quotes('"/home/o\'brien/repo"') == "/home/o'brien/repo"

    def test_leaves_lone_leading_quote_untouched(self):
        assert strip_surrounding_quotes('"/home/x') == '"/home/x'

    def test_leaves_lone_trailing_quote_untouched(self):
        assert strip_surrounding_quotes("/home/x'") == "/home/x'"

    def test_leaves_mismatched_pair_untouched(self):
        assert strip_surrounding_quotes("'/home/x\"") == "'/home/x\""

    def test_trims_surrounding_whitespace(self):
        assert strip_surrounding_quotes("  /home/x  ") == "/home/x"

    def test_trims_whitespace_outside_and_inside_quotes(self):
        assert strip_surrounding_quotes('  "  /home/x  "  ') == "/home/x"

    def test_empty_quote_pair_collapses_to_empty(self):
        assert strip_surrounding_quotes('""') == ""
        assert strip_surrounding_quotes("''") == ""

    def test_empty_and_whitespace_only(self):
        assert strip_surrounding_quotes("") == ""
        assert strip_surrounding_quotes("   ") == ""

    def test_non_string_returned_unchanged(self):
        # Defensive: the seam may hand us a non-str under a bad caller.
        assert strip_surrounding_quotes(None) is None  # type: ignore[arg-type]

    def test_only_one_pair_stripped(self):
        # Nested quoting strips exactly one balanced pair, not both.
        assert strip_surrounding_quotes("\"'/home/x'\"") == "'/home/x'"


class TestOpenTargetSanitisesInput:
    """The seam the grader drives must accept a quoted local path."""

    def test_double_quoted_local_path_resolves(self, well_run_repo: Path):
        quoted = f'"{well_run_repo}"'
        with open_target(quoted, allow_clone=False) as target:
            assert isinstance(target, ResolvedTarget)
            assert target.local_path == well_run_repo.resolve()

    def test_single_quoted_local_path_resolves(self, well_run_repo: Path):
        quoted = f"'{well_run_repo}'"
        with open_target(quoted, allow_clone=False) as target:
            assert target.local_path == well_run_repo.resolve()

    def test_unquoted_local_path_still_resolves(self, well_run_repo: Path):
        with open_target(str(well_run_repo), allow_clone=False) as target:
            assert target.local_path == well_run_repo.resolve()
