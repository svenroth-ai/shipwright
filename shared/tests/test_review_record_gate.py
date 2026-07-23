"""Tests for the F11 review-record gate (AC6).

The gate's whole job is that an empty Review row means "genuinely not run".
Every branch below is a way that guarantee could be lost.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    make_entry,
    new_record,
    record_path,
    upsert_review,
    write_record,
)
from tools.verifiers.review_record_check import check_review_record  # noqa: E402

RUN_ID = "iterate-2026-07-21-review-record"
REASON = "trivial docs-only diff; conditional per iteration-reviews.md"


def _project(tmp_path, complexity="medium"):
    iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True)
    (iterates / f"{RUN_ID}.json").write_text(json.dumps({
        "run_id": RUN_ID, "date": "2026-07-21T00:00:00+00:00", "type": "feature",
        "complexity": complexity, "branch": "iterate/review-record", "tests_passed": True,
    }), encoding="utf-8")
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    return tmp_path


def _complete_record(project, **overrides):
    record = new_record(RUN_ID)
    for review_type in REVIEW_TYPES:
        status = overrides.get(review_type, "completed")
        record = upsert_review(
            record,
            make_entry(review_type, status,
                       disposition=REASON if status != "completed" else None),
            force=True,
        )
    write_record(project, RUN_ID, record)
    return record


def test_passes_when_every_type_is_terminal(tmp_path):
    project = _project(tmp_path)
    _complete_record(project)
    result = check_review_record(project, RUN_ID)
    assert result.ok, result.detail


def test_passes_when_types_are_closed_as_not_run(tmp_path):
    project = _project(tmp_path)
    _complete_record(project, doubt="not_applicable", external_code="not_run")
    assert check_review_record(project, RUN_ID).ok


def test_fails_when_a_type_is_still_pending(tmp_path):
    project = _project(tmp_path)
    record = new_record(RUN_ID)
    record = upsert_review(record, make_entry("self", "completed"))
    write_record(project, RUN_ID, record)

    result = check_review_record(project, RUN_ID)

    assert not result.ok
    assert "doubt" in result.detail
    assert "record_review_pass.py" in result.detail


def test_fails_when_the_record_is_missing(tmp_path):
    project = _project(tmp_path)
    result = check_review_record(project, RUN_ID)
    assert not result.ok
    assert "no review record" in result.detail.lower()


def test_fails_when_the_record_is_corrupt(tmp_path):
    """A corrupt record is a data-integrity fault and must be reported as one —
    never as 'missing' and never as a pass."""
    project = _project(tmp_path)
    path = record_path(project, RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    result = check_review_record(project, RUN_ID)

    assert not result.ok
    assert "unreadable" in result.detail.lower() or "invalid" in result.detail.lower()


def test_fails_when_the_record_is_schema_invalid(tmp_path):
    project = _project(tmp_path)
    _complete_record(project)
    path = record_path(project, RUN_ID)
    record = json.loads(path.read_text(encoding="utf-8"))
    del record["reviews"]["doubt"]
    path.write_text(json.dumps(record), encoding="utf-8")

    result = check_review_record(project, RUN_ID)

    assert not result.ok
    assert "doubt" in result.detail


def test_fails_when_the_record_belongs_to_another_run(tmp_path):
    """A record whose run_id disagrees with the run being verified cannot vouch
    for this run — copying one in must not satisfy the gate."""
    project = _project(tmp_path)
    _complete_record(project)
    path = record_path(project, RUN_ID)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["run_id"] = "iterate-2026-01-01-somewhere-else"
    path.write_text(json.dumps(record), encoding="utf-8")

    result = check_review_record(project, RUN_ID)

    assert not result.ok


def test_skips_at_trivial_complexity(tmp_path):
    project = _project(tmp_path, complexity="trivial")
    result = check_review_record(project, RUN_ID)
    assert result.ok
    assert "skipped" in result.detail.lower()


@pytest.mark.parametrize("complexity", ["small", "medium", "large"])
def test_applies_from_small_upwards(tmp_path, complexity):
    project = _project(tmp_path, complexity=complexity)
    assert not check_review_record(project, RUN_ID).ok


def test_skips_when_the_complexity_is_unknown(tmp_path):
    """No iterate entry means the gate cannot know whether it applies. It says
    so rather than inventing a verdict in either direction."""
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    result = check_review_record(tmp_path, RUN_ID)
    assert result.ok
    assert "skipped" in result.detail.lower()


# --- the record must be IN THE COMMIT, not just the worktree ----------------


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)


@pytest.fixture
def git_project(tmp_path):
    project = _project(tmp_path)
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@example.com")
    _git(project, "config", "user.name", "t")
    return project


def test_a_tracked_record_missing_from_the_commit_fails(git_project):
    """F6 stages an explicit per-path list, so an unstaged record is easy to
    produce — and it is deleted with the worktree after the PR merges. A green
    gate must not be compatible with the artifact never shipping."""
    _complete_record(git_project)
    # Commit something else, leaving the record staged-but-not-committed.
    _git(git_project, "add", ".shipwright/agent_docs")
    _git(git_project, "commit", "-q", "-m", "without the record")
    _git(git_project, "add", "-N",
         f".shipwright/planning/iterate/{RUN_ID}/reviews.json")
    head = _git(git_project, "rev-parse", "HEAD").stdout.strip()

    result = check_review_record(git_project, RUN_ID, head)

    assert not result.ok
    assert "NOT in commit" in result.detail


def test_a_committed_record_passes(git_project):
    _complete_record(git_project)
    _git(git_project, "add", ".")
    _git(git_project, "commit", "-q", "-m", "with the record")
    head = _git(git_project, "rev-parse", "HEAD").stdout.strip()

    result = check_review_record(git_project, RUN_ID, head)

    assert result.ok, result.detail


def test_an_untracked_record_skips_the_committed_assertion(git_project):
    """A project that gitignores the path has nothing to assert."""
    _complete_record(git_project)
    _git(git_project, "add", ".shipwright/agent_docs")
    _git(git_project, "commit", "-q", "-m", "base")
    head = _git(git_project, "rev-parse", "HEAD").stdout.strip()

    assert check_review_record(git_project, RUN_ID, head).ok


def test_no_commit_supplied_skips_the_committed_assertion(tmp_path):
    project = _project(tmp_path)
    _complete_record(project)
    assert check_review_record(project, RUN_ID).ok


def test_the_failure_message_lists_every_outstanding_type(tmp_path):
    project = _project(tmp_path)
    write_record(project, RUN_ID, new_record(RUN_ID))
    message = check_review_record(project, RUN_ID).detail
    for review_type in REVIEW_TYPES:
        assert review_type in message
