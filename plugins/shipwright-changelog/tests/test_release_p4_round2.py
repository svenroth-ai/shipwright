"""The second fix round of unit P4 (orchestrator review of a0020b7b1): what the independent reviews found, each proven to fail on the old code."""

from __future__ import annotations

import subprocess

import pytest

from lib import release_commit, release_event, release_runstate
from .test_release_cli import Fake
from .test_release_p4_cli import GOOD, HEAD, OK_TAG, PATHS, VERSION, close, event_fake, rec, seed, verify_with

pytestmark = pytest.mark.covers("FR-01.09/AC01")
AUTO = {"on_trunk": False, "pr_url": "u", "autonomy": "autonomous"}


def test_a_driven_autonomous_release_expects_its_pr_left_open_and_runs_no_ancestry_test(tmp_path, plugin_root):
    fake = Fake(**GOOD)
    checks = verify_with(tmp_path, plugin_root, fake, {**AUTO, "mode": "pipeline"})
    assert checks["pr_state"]["ok"] is True and "verify-merged" not in fake.keys()


def test_a_standalone_autonomous_release_fetches_the_trunk_named_by_the_remote_before_the_ancestry_test(tmp_path, plugin_root):
    fake = Fake(**GOOD, **{"verify-base": {"stdout": "origin/develop\n"}})
    checks = verify_with(tmp_path, plugin_root, fake, {**AUTO, "mode": "standalone"})
    assert checks["pr_state"]["ok"] is True and "develop" in checks["pr_state"]["detail"]
    assert fake.keys().index("verify-fetch") < fake.keys().index("verify-merged") and fake.argv("verify-merged")[-1] == "FETCH_HEAD"


def test_a_missing_local_object_is_unknown_not_unmerged(tmp_path, plugin_root):
    fake = Fake(**GOOD, **{"verify-merged": {"exit": 128, "stderr": "fatal: Not a valid commit name"}})
    check = verify_with(tmp_path, plugin_root, fake, {**AUTO, "mode": "standalone"})["pr_state"]
    assert check["ok"] is False and check["detail"].startswith("unknown:") and "not on origin" not in check["detail"]


def test_a_failed_fetch_is_unknown_too(tmp_path, plugin_root):
    fake = Fake(**GOOD, **{"verify-fetch": {"exit": 1, "stderr": "could not resolve host"}})
    check = verify_with(tmp_path, plugin_root, fake, {**AUTO, "mode": "standalone"})["pr_state"]
    assert check["ok"] is False and check["detail"].startswith("unknown:") and "verify-merged" not in fake.keys()


def test_a_dirt_that_existed_before_the_release_is_not_the_releases(tmp_path, plugin_root):
    line = " M .shipwright/agent_docs/session_handoff.md"
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u", tree_before=[line])
    code, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"stdout": line + "\n"}}))
    assert code == 0 and out["tree_clean"] is True


def test_a_dirt_the_release_made_still_fails_and_the_advisory_finding_matches_in_any_status_form(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u", tree_before=[])
    code, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"exit": 128, "stderr": "fatal"}}))
    assert code == 1 and out["tree_clean"] is False  # a failed status is not a clean tree
    code, _ = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"stdout": " M .shipwright/triage.jsonl\n?? .shipwright/triage.jsonl\n"}}))
    assert code == 0
    code, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"stdout": " M .shipwright/agent_docs/session_handoff.md\n"}}))
    assert code == 1 and out["tree_clean"] is False


def test_the_tag_is_made_on_the_verified_sha_and_a_failed_removal_is_reported(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    fake = Fake(**{**OK_TAG, "tag-commit": {"stdout": "b" * 40 + "\n"}, "tag-remove": {"exit": 1, "stderr": "no such tag"}})
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert fake.argv("tag")[-1] == HEAD and code == 1 and out["reason"] == "tag_remove_failed"


def test_the_rerun_shortcut_needs_a_status_that_could_be_read(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    fake = Fake(**{**OK_TAG, "last-subject": {"stdout": f"chore(release): v{VERSION}\n"}, "pending": {"exit": 128}})
    release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert "commit" in fake.keys()  # an unreadable status is not "clean": the commit is attempted and says why it cannot


def test_a_failing_listing_of_the_staged_event_paths_stops_the_event(tmp_path, plugin_root):
    fake = event_fake("release/v1", **{"event-paths": {"exit": 128, "stderr": "fatal"}})
    code, out = release_event.record_event(rec(tmp_path, fake), plugin_root, version=VERSION, pr_url="u")
    assert code == 128 and out["reason"] == "event_paths_failed" and "event-commit" not in fake.keys()


@pytest.mark.parametrize("commit", ["x", "A" * 40, "a" * 39, "a" * 40 + "\n--upload-pack=x", ""])
def test_a_release_state_with_a_malformed_commit_reads_as_absent(tmp_path, commit):
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": commit})
    assert release_commit.read_state(tmp_path) is None
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": "a" * 64})
    assert release_commit.read_state(tmp_path)["commit"] == "a" * 64  # a sha256 repository


def test_a_decision_drop_in_a_subfolder_counts(tmp_path, plugin_root):
    sub = tmp_path / ".shipwright/agent_docs/decision-drops/bullets"
    sub.mkdir(parents=True)
    (sub / "README.md").write_text("x", encoding="utf-8")
    (sub / "a.tmp").write_text("x", encoding="utf-8")
    assert verify_with(tmp_path, plugin_root, Fake(**GOOD), {"on_trunk": True})["no_decision_drops"]["ok"] is True
    (sub / "learnings--x.md").write_text("x", encoding="utf-8")
    assert verify_with(tmp_path, plugin_root, Fake(**GOOD), {"on_trunk": True})["no_decision_drops"]["ok"] is False


def test_prepare_records_what_was_dirty_before_the_release(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert release_runstate.tree_snapshot(tmp_path) == ["?? a.txt"]
    assert release_runstate.tree_snapshot(tmp_path / "missing") == []


def test_the_summary_and_event_name_the_real_trunk(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="develop", on_trunk=True, tree_before=[])
    _, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"stdout": ""}}))
    assert "Tag + develop pushed to origin" in out["summary"]
