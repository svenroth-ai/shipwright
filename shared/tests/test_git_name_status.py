"""Tests for the ``git diff --name-status -z`` parser.

The index arithmetic here decides what the attribution check sees, and getting it
wrong is silent: a short read reports fewer changed files than really changed, so
the check passes on work it never looked at.

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

import pytest

from lib.git_name_status import NameStatusError, parse, rebase


def _stream(*fields: str) -> str:
    return "\0".join(fields) + "\0"


def test_added_and_modified_share_a_bucket():
    out = parse(_stream("A", "src/new.ts", "M", "src/old.ts"))
    assert out["added_modified"] == ["src/new.ts", "src/old.ts"]
    assert out["deleted"] == [] and out["renamed"] == []


def test_deletions_are_their_own_bucket():
    out = parse(_stream("D", "src/gone.ts"))
    assert out["deleted"] == ["src/gone.ts"]
    assert out["added_modified"] == []


def test_a_rename_puts_the_destination_where_it_is_checked():
    """Bucketing both paths as 'renamed' let a git-mv-plus-rewrite escape."""
    out = parse(_stream("R100", "src/old.ts", "src/new.ts"))
    assert out["renamed"] == ["src/old.ts"]
    assert out["added_modified"] == ["src/new.ts"]


def test_a_copy_behaves_like_a_rename():
    out = parse(_stream("C075", "src/a.ts", "src/b.ts"))
    assert out["renamed"] == ["src/a.ts"]
    assert out["added_modified"] == ["src/b.ts"]


def test_paths_with_spaces_and_quotes_survive():
    out = parse(_stream("M", 'src/my file "x".ts'))
    assert out["added_modified"] == ['src/my file "x".ts']


def test_mixed_stream_keeps_every_record():
    out = parse(_stream("M", "a.ts", "R090", "b.ts", "c.ts", "D", "d.ts", "A", "e.ts"))
    assert out["added_modified"] == ["a.ts", "c.ts", "e.ts"]
    assert out["renamed"] == ["b.ts"]
    assert out["deleted"] == ["d.ts"]


def test_empty_stream_is_empty():
    out = parse("")
    assert out == {"added_modified": [], "deleted": [], "renamed": []}


def test_a_truncated_rename_raises_rather_than_short_reading():
    with pytest.raises(NameStatusError, match="rename/copy"):
        parse(_stream("M", "a.ts", "R100", "src/old.ts"))


def test_a_truncated_single_path_record_raises():
    with pytest.raises(NameStatusError, match="truncated"):
        parse(_stream("M", "a.ts", "D"))


def test_windows_separators_normalize():
    out = parse(_stream("M", r"src\a.ts"))
    assert out["added_modified"] == ["src/a.ts"]


# --------------------------------------------------------------------------
# rebase — repository-root paths onto the project root
# --------------------------------------------------------------------------

def test_no_prefix_is_a_no_op():
    assert rebase("src/a.ts", "") == "src/a.ts"


def test_a_path_under_the_project_is_rebased():
    assert rebase("apps/web/src/a.ts", "apps/web") == "src/a.ts"


def test_a_path_outside_the_project_is_dropped():
    assert rebase("apps/other/src/a.ts", "apps/web") == ""


def test_the_project_root_itself_is_dropped():
    assert rebase("apps/web", "apps/web") == ""


def test_a_sibling_with_a_shared_prefix_is_not_rebased():
    """`apps/web2` must not be mistaken for something inside `apps/web`."""
    assert rebase("apps/web2/src/a.ts", "apps/web") == ""


def test_parse_applies_the_prefix():
    out = parse(_stream("M", "apps/web/src/a.ts", "M", "apps/other/b.ts"), "apps/web")
    assert out["added_modified"] == ["src/a.ts"]
