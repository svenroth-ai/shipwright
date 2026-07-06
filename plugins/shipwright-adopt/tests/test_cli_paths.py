"""Tests for lib.cli_paths — a quote-tolerant argparse path type.

A user who pastes a quoted ``--project-root`` (Explorer "Copy as path" wraps the
value in literal ``"..."``; a shell-copied path may carry ``'...'``) should have
adoption resolve the real directory instead of a path with a stray quote in it.
Mirrors the shipwright-grade ``normalize_input`` seam and WebUI ``normalize-fs-path``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lib.cli_paths import strip_surrounding_quotes, unquoted_path


class TestStripSurroundingQuotes:
    def test_strips_double_quote_pair(self):
        assert strip_surrounding_quotes('"/srv/app"') == "/srv/app"

    def test_strips_single_quote_pair(self):
        assert strip_surrounding_quotes("'/srv/app'") == "/srv/app"

    def test_windows_copy_as_path(self):
        assert (
            strip_surrounding_quotes(r'"C:\Users\me\My Project"')
            == r"C:\Users\me\My Project"
        )

    def test_preserves_inner_apostrophe(self):
        assert strip_surrounding_quotes("/home/o'brien/app") == "/home/o'brien/app"

    def test_leaves_lone_quote_untouched(self):
        assert strip_surrounding_quotes('"/srv/app') == '"/srv/app'

    def test_leaves_mismatched_pair_untouched(self):
        assert strip_surrounding_quotes("'/srv/app\"") == "'/srv/app\""

    def test_trims_whitespace(self):
        assert strip_surrounding_quotes('  "  /srv/app  "  ') == "/srv/app"

    def test_empty_inputs(self):
        assert strip_surrounding_quotes("") == ""
        assert strip_surrounding_quotes("   ") == ""
        assert strip_surrounding_quotes('""') == ""


class TestUnquotedPath:
    def test_double_quoted_becomes_clean_path(self):
        assert unquoted_path('"/srv/app"') == Path("/srv/app")

    def test_single_quoted_becomes_clean_path(self):
        assert unquoted_path("'/srv/app'") == Path("/srv/app")

    def test_windows_copy_as_path_becomes_clean_path(self):
        assert unquoted_path(r'"C:\Users\me\repo"') == Path(r"C:\Users\me\repo")

    def test_unquoted_path_unchanged(self):
        assert unquoted_path("/srv/app") == Path("/srv/app")

    def test_returns_path_instance(self):
        assert isinstance(unquoted_path('"/srv/app"'), Path)


class TestArgparseIntegration:
    """The exact mechanism the adopt CLIs use: ``type=unquoted_path``."""

    def _parser(self) -> argparse.ArgumentParser:
        p = argparse.ArgumentParser()
        p.add_argument("--project-root", required=True, type=unquoted_path)
        return p

    def test_quoted_project_root_is_stripped(self):
        args = self._parser().parse_args(["--project-root", '"/srv/app"'])
        assert args.project_root == Path("/srv/app")

    def test_plain_project_root_unaffected(self):
        args = self._parser().parse_args(["--project-root", "/srv/app"])
        assert args.project_root == Path("/srv/app")
