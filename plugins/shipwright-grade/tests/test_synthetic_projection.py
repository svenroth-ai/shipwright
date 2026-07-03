"""Tests for synthetic_projection — pure git-log → WorkEvent parsing."""

from __future__ import annotations

from synthetic_projection import parse_git_log

_US = "\x1f"
_RS = "\x1e"


def _record(sha, date, author, subject, body=""):
    return f"{sha}{_US}{date}{_US}{author}{_US}{subject}{_US}{body}{_RS}"


class TestParseGitLog:
    def test_conventional_and_pr_ref_are_traced_with_provenance(self):
        raw = _record("abc", "2024-01-01T00:00:00+00:00", "A", "feat: thing (#12)")
        (ev,) = parse_git_log(raw)
        assert ev.sha == "abc"
        assert ev.conventional_type == "feat"
        assert ev.ref == "#12"
        assert ev.is_traced is True
        assert ev.has_provenance is True

    def test_conventional_without_ref_is_traced_but_no_provenance(self):
        raw = _record("d1", "2024-01-01T00:00:00+00:00", "A", "fix: no link here")
        (ev,) = parse_git_log(raw)
        assert ev.conventional_type == "fix"
        assert ev.ref is None
        assert ev.is_traced is True
        assert ev.has_provenance is False  # strict: a SHA is not provenance

    def test_plain_subject_is_neither_traced_nor_provenanced(self):
        raw = _record("d2", "2024-01-01T00:00:00+00:00", "A", "just some work")
        (ev,) = parse_git_log(raw)
        assert ev.conventional_type is None
        assert ev.is_traced is False
        assert ev.has_provenance is False

    def test_non_conventional_word_is_not_a_type(self):
        raw = _record("d3", "2024-01-01T00:00:00+00:00", "A", "hello: world")
        (ev,) = parse_git_log(raw)
        assert ev.conventional_type is None

    def test_issue_url_in_body_counts_as_provenance(self):
        raw = _record("d4", "2024-01-01T00:00:00+00:00", "A", "update",
                      "See https://github.com/x/y/issues/7")
        (ev,) = parse_git_log(raw)
        assert ev.ref == "issues/7"
        assert ev.ref_kind == "issue"
        assert ev.has_provenance is True

    def test_merge_pull_request_phrasing(self):
        raw = _record("d5", "2024-01-01T00:00:00+00:00", "A",
                      "Merge pull request #42 from x/y")
        (ev,) = parse_git_log(raw)
        assert ev.ref == "#42"
        assert ev.ref_kind == "pr"

    def test_body_with_newlines_does_not_break_records(self):
        raw = (
            _record("s1", "2024-01-01T00:00:00+00:00", "A", "feat: one (#1)",
                    "line one\nline two\n")
            + _record("s2", "2024-01-02T00:00:00+00:00", "B", "chore: two")
        )
        evs = parse_git_log(raw)
        assert [e.sha for e in evs] == ["s1", "s2"]

    def test_empty_input_is_empty(self):
        assert parse_git_log("") == []
        assert parse_git_log("   \n  ") == []

    def test_files_changed_is_deferred_to_g2(self):
        raw = _record("z1", "2024-01-01T00:00:00+00:00", "A", "feat: x (#1)")
        (ev,) = parse_git_log(raw)
        assert ev.files_changed is None
