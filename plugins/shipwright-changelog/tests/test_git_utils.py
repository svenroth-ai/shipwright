"""Tests for git_utils module."""

import os
import subprocess

from lib.git_utils import (
    get_commits_since,
    get_last_tag,
    parse_all_commits,
    parse_conventional_commit,
    suggest_version_bump,
)


def test_parse_feat_with_scope():
    c = parse_conventional_commit("abc", "feat(auth): implement login")
    assert c.type == "feat"
    assert c.scope == "auth"
    assert c.description == "implement login"
    assert c.breaking is False


def test_parse_fix_without_scope():
    c = parse_conventional_commit("def", "fix: handle null")
    assert c.type == "fix"
    assert c.scope is None
    assert c.description == "handle null"


def test_parse_breaking_bang():
    c = parse_conventional_commit("ghi", "feat!: redesign onboarding")
    assert c.type == "feat"
    assert c.breaking is True


def test_parse_breaking_footer():
    c = parse_conventional_commit("jkl", "refactor(api): change response format\n\nBREAKING CHANGE: response is now JSON array")
    assert c.type == "refactor"
    assert c.breaking is True


def test_parse_non_conventional():
    c = parse_conventional_commit("mno", "updated the readme")
    assert c.type == "other"
    assert c.description == "updated the readme"


def test_parse_unknown_type():
    c = parse_conventional_commit("pqr", "yolo(stuff): did something")
    assert c.type == "other"


def test_parse_all_commits():
    commits = [
        {"hash": "a1", "message": "feat: add login"},
        {"hash": "b2", "message": "fix: handle error"},
        {"hash": "c3", "message": "random message"},
    ]
    parsed = parse_all_commits(commits)
    assert len(parsed) == 3
    assert parsed[0].type == "feat"
    assert parsed[1].type == "fix"
    assert parsed[2].type == "other"


def test_suggest_version_first_release():
    version, reason = suggest_version_bump([], None)
    assert version == "0.1.0"
    assert "first" in reason


def test_suggest_version_feat():
    from lib.git_utils import ParsedCommit
    commits = [ParsedCommit(hash="a", raw_message="", type="feat", description="x")]
    version, _ = suggest_version_bump(commits, "v0.1.0")
    assert version == "0.2.0"


def test_suggest_version_fix_only():
    from lib.git_utils import ParsedCommit
    commits = [ParsedCommit(hash="a", raw_message="", type="fix", description="x")]
    version, _ = suggest_version_bump(commits, "v0.1.0")
    assert version == "0.1.1"


def test_suggest_version_breaking():
    from lib.git_utils import ParsedCommit
    commits = [ParsedCommit(hash="a", raw_message="", type="feat", description="x", breaking=True)]
    version, _ = suggest_version_bump(commits, "v1.0.0")
    assert version == "2.0.0"


def test_suggest_version_breaking_pre_1():
    from lib.git_utils import ParsedCommit
    commits = [ParsedCommit(hash="a", raw_message="", type="feat", description="x", breaking=True)]
    version, _ = suggest_version_bump(commits, "v0.2.0")
    assert version == "0.3.0"


def test_get_last_tag_in_real_repo(git_repo_with_tag):
    orig = os.getcwd()
    os.chdir(str(git_repo_with_tag))
    try:
        tag = get_last_tag()
        assert tag == "v0.1.0"
    finally:
        os.chdir(orig)


def test_get_commits_since_tag(git_repo_with_tag):
    orig = os.getcwd()
    os.chdir(str(git_repo_with_tag))
    try:
        commits = get_commits_since("v0.1.0")
        assert len(commits) == 3  # feat, fix, docs
        messages = [c["message"] for c in commits]
        assert any("feat(auth)" in m for m in messages)
        assert any("fix(api)" in m for m in messages)
    finally:
        os.chdir(orig)
