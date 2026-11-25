"""Fixes that the P4 reviews asked for (unit P4): the refusals that stop before anything irreversible happens."""

from __future__ import annotations

import pytest

from lib import release_close, release_commit, release_event, release_verify

from .test_release_cli import NOW
from .test_release_p4_cli import GOOD, OK_TAG, VERSION, Fake, close, event_fake, rec, seed

pytestmark = pytest.mark.covers("FR-01.09/AC01")
PATHS = {"evidence_pathspec": [".shipwright/compliance/dashboard.md"], "manifest_pathspec": ["package.json"]}


def test_commit_and_tag_refuses_without_the_pathspecs_sync_kept(tmp_path, plugin_root):
    fake = Fake(**OK_TAG)
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 1 and out["reason"] == "sync_not_run" and "commit" not in fake.keys()


def test_close_phase_refuses_when_the_run_state_is_missing(tmp_path, plugin_root):
    code, out = release_close.close_phase(rec(tmp_path, Fake()), plugin_root, version=VERSION)
    assert code == 1 and out["reason"] == "run_state_missing"


def test_a_driven_release_never_waits_for_the_merge_whatever_its_autonomy():
    """One key (P5 fix round): the mode. The master owns a driven run's PR, so it neither merges nor waits."""
    assert release_verify.waits_for_merge({"mode": "pipeline", "autonomy": "guided"}) is False
    assert release_verify.waits_for_merge({"mode": "standalone", "autonomy": "autonomous"}) is True


def test_a_rerun_after_a_failed_audit_verifies_and_tags_the_release_commit_that_is_already_there(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    fake = Fake(**{**OK_TAG, "last-subject": {"stdout": f"chore(release): v{VERSION}\n"}})
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION, clock=lambda: NOW)
    assert code == 0 and "commit" not in fake.keys() and "tag" in fake.keys()


def test_record_event_on_a_feature_branch_without_a_pr_url_records_and_pushes_nothing(tmp_path, plugin_root):
    fake = event_fake("release/v1.3.0")
    code, out = release_event.record_event(rec(tmp_path, fake), plugin_root, version=VERSION, pr_url="")
    keys = fake.keys()
    assert code == 1 and out["reason"] == "pr_url_missing" and keys[0] == "branch"
    assert set(keys) <= {"branch", "trunk-url", "trunk", "trunk-local"}  # P8a (F5): only reads, which branch is the trunk


def test_close_phase_fails_when_a_hand_invoked_release_leaves_the_tree_dirty(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u")
    code, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"stdout": " M CHANGELOG.md\n"}}))
    assert code == 1 and out["tree_clean"] is False and [c["name"] for c in out["verify"] if not c["ok"]] == ["tree_clean"]


def test_a_failing_canon_writer_stops_the_later_ones(tmp_path, plugin_root):
    seed(tmp_path, mode="pipeline", branch="main", on_trunk=True)
    fake = Fake(**GOOD, dashboard={"exit": 1})
    code, out = close(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "dashboard_failed" and out["written"] == [] and "handoff" not in fake.keys()


def test_a_failing_restore_fails_the_close(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    code, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"restore-derived": {"exit": 1}}))
    assert code == 1 and out["reason"] == "restore-derived_failed"


def test_a_standalone_close_without_a_release_commit_restores_nothing(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake(**GOOD)
    code, out = release_close.close_phase(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 1 and out["reason"] == "release_not_committed" and "restore-derived" not in fake.keys()
