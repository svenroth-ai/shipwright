"""L1 tests of ``release.py sync``, ``commit-and-tag``, ``record-event`` and ``close-phase`` with an injected runner (unit P4, FR-01.09).

No process is started: a fake runner answers by the key of each tool call, so the tests prove what the CLI asks of the existing
tools, in which order, with which flags, when it refuses to tag, and what it writes itself (the run state, ``release_state.json``).
The behaviour changes decided by the operator are proven on real git in ``tests/golden/test_p4_decisions.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import release_close, release_commit, release_event, release_runstate, release_sync, release_verify
from lib.release_runner import Recorder

from .test_release_cli import NOW, Fake

pytestmark = pytest.mark.covers("FR-01.09/AC01")

VERSION, HEAD = "1.3.0", "a" * 40
PR = "https://example.test/pr/1"
PATHS = {"evidence_pathspec": [".shipwright/compliance/dashboard.md"], "manifest_pathspec": ["package.json"]}
OK_SYNC = {"fold-events": {"stdout": json.dumps({"status": "folded"})},
           "sync": {"stdout": json.dumps({"status": "ok", "version": VERSION, "manifest_pathspec": ["package.json"]})},
           "evidence": {"stdout": json.dumps({"status": "ok", "evidence_pathspec": [".shipwright/compliance/dashboard.md"]})}}
OK_TAG = {"head": {"stdout": HEAD + "\n"}, "tag-commit": {"stdout": HEAD + "\n"},
          "verify-tag": {"stdout": json.dumps({"ok": True, "checks": {"tag_exists": {"ok": True, "detail": ""}}})}}


def rec(tmp_path: Path, fake: Fake) -> Recorder:
    return Recorder(fake, tmp_path)


def seed(tmp_path: Path, **fields) -> None:
    release_runstate.patch(tmp_path, VERSION, clock=lambda: NOW, **fields)


def test_sync_runs_the_fold_then_the_manifests_then_the_evidence_and_keeps_both_pathspecs(tmp_path, plugin_root):
    fake = Fake(**OK_SYNC)
    code, out = release_sync.sync(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 0 and out["status"] == "ok" and fake.keys() == ["fold-events", "sync", "evidence"]
    assert fake.argv("sync")[-5:] == ["--version", VERSION, "--stage", "--result-file", ".shipwright/runtime/manifest_sync_result.json"]
    assert fake.argv("evidence")[-3:] == ["--stage", "--release", f"v{VERSION}"]
    assert release_runstate.stored(tmp_path, VERSION)["evidence_pathspec"] == PATHS["evidence_pathspec"]
    assert release_runstate.stored(tmp_path, VERSION)["manifest_pathspec"] == ["package.json"]


@pytest.mark.parametrize(("failing", "reason", "never"), [("sync", "manifest_sync_failed", "evidence"), ("evidence", "evidence_refresh_failed", None)])
def test_sync_stops_on_a_refusal_and_never_goes_on_to_the_next_tool(tmp_path, plugin_root, failing, reason, never):
    answers = {**OK_SYNC, failing: {"exit": 1, "stdout": json.dumps({"status": "unsupported_format"})}}
    fake = Fake(**answers)
    code, out = release_sync.sync(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert (code, out["reason"]) == (1, reason) and (never is None or never not in fake.keys())
    assert release_runstate.stored(tmp_path, VERSION) is None  # a refused sync records no pathspec


def test_a_fold_that_fails_never_blocks_the_release(tmp_path, plugin_root):
    code, out = release_sync.sync(rec(tmp_path, Fake(**{**OK_SYNC, "fold-events": {"exit": 1, "stdout": "{}"}})), plugin_root, version=VERSION)
    assert code == 0 and out["fold"] == {"status": "failed", "exit": 1}


def commit_chain(fake: Fake) -> list[str]:
    return [k for k in fake.keys() if k in ("commit", "verify-evidence", "verify-manifests", "tag")]


def test_commit_and_tag_runs_the_prose_chain_by_explicit_pathspec_and_tags_the_committed_head(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    (tmp_path / ".shipwright/agent_docs").mkdir(parents=True)
    (tmp_path / ".shipwright/agent_docs/architecture.md").write_text("# a\n", encoding="utf-8")
    fake = Fake(**OK_TAG)
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION, clock=lambda: NOW)
    assert code == 0 and out["commit"] == HEAD and commit_chain(fake) == ["commit", "verify-evidence", "verify-manifests", "tag"]
    argv = fake.argv("commit")
    assert argv[:5] == ["git", "commit", "-m", f"chore(release): v{VERSION}", "--"]  # the pathspec after `--`: the worktree is read, not the index
    assert {"CHANGELOG.md", ".shipwright/agent_docs/architecture.md", ".shipwright/compliance/dashboard.md", "package.json",
            ".shipwright/agent_docs/decision-drops/", ".shipwright/planning/adr/"} <= set(argv[5:])
    assert ".shipwright/agent_docs/conventions.md" not in argv  # only a document the project has
    assert fake.keys().index("head") > fake.keys().index("commit")  # HEAD is read only after the commit
    assert fake.argv("verify-evidence")[-3:] == ["--verify-commit", HEAD, "--release-audit"]
    assert fake.argv("verify-manifests")[-4:-2] == ["--verify-commit", HEAD]
    assert fake.argv("tag") == ["git", "tag", "-a", f"v{VERSION}", "-m", f"Release v{VERSION}", HEAD]  # the verified SHA


@pytest.mark.parametrize("failing", ["commit", "verify-evidence", "verify-manifests"])
def test_commit_and_tag_refuses_to_tag_unless_every_step_exits_zero(tmp_path, plugin_root, failing):
    seed(tmp_path, **PATHS)
    fake = Fake(**OK_TAG, **{failing: {"exit": 3, "stderr": "refused"}})
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 3 and out["status"] == "failed" and "tag" not in fake.keys()
    assert not (tmp_path / release_commit.RELEASE_STATE).exists()


def test_a_commit_that_fails_never_reads_head_so_it_cannot_tag_the_previous_commit(tmp_path, plugin_root):
    fake = Fake(**OK_TAG, commit={"exit": 1})
    release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert "head" not in fake.keys() and "tag" not in fake.keys()


def test_f7_a_tag_that_names_another_commit_is_refused_and_removed_again(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    fake = Fake(**{**OK_TAG, "tag-commit": {"stdout": "b" * 40 + "\n"}})
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 1 and out["reason"] == "tag_check_failed" and fake.argv("tag-remove") == ["git", "tag", "-d", f"v{VERSION}"]
    assert not (tmp_path / release_commit.RELEASE_STATE).exists() and "update-step" not in json.dumps(fake.calls)


def test_f7_a_changelog_that_disagrees_with_the_tag_is_refused(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    bad = {"stdout": json.dumps({"ok": False, "checks": {"changelog_matches_tag": {"ok": False, "detail": "top=v1.2.0"}}}), "exit": 1}
    fake = Fake(**{**OK_TAG, "verify-tag": bad})
    code, out = release_commit.commit_and_tag(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 1 and out["reason"] == "tag_check_failed" and "tag-remove" in fake.keys()
    assert out["checks"]["changelog_matches_tag"]["ok"] is False


def test_b1_the_release_state_names_the_committed_head_and_the_checks_that_passed(tmp_path, plugin_root):
    seed(tmp_path, **PATHS)
    code, _ = release_commit.commit_and_tag(rec(tmp_path, Fake(**OK_TAG)), plugin_root, version=VERSION, clock=lambda: NOW)
    record = json.loads((tmp_path / release_commit.RELEASE_STATE).read_text(encoding="utf-8"))
    assert code == 0 and (record["version"], record["commit"], record["tag"]) == (VERSION, HEAD, f"v{VERSION}")
    assert {"commit", "evidence_audit", "manifest_verify", "tag", "tag_exists"} <= set(record["checks_passed"])
    assert release_runstate.stored(tmp_path, VERSION)["release_commit"] == HEAD


def event_fake(branch: str, **over) -> Fake:
    return Fake(branch={"stdout": branch + "\n"}, **{"event-paths": {"stdout": "shipwright_events.jsonl\0"}, **over})


def test_record_event_on_a_feature_branch_commits_only_the_event_paths_and_pushes_the_head(tmp_path, plugin_root):
    fake = event_fake("release/next")
    code, out = release_event.record_event(rec(tmp_path, fake), plugin_root, version=VERSION, pr_url="https://example.test/pr/1")
    assert code == 0 and out["on_trunk"] is False and out["pushed"] is True and out["committed"] == ["shipwright_events.jsonl"]
    assert fake.argv("event-record")[-8:] == ["--type", "phase_completed", "--phase", "changelog", "--run-id", f"release-v{VERSION}",
                                              "--detail", f"v{VERSION} — https://example.test/pr/1"]
    assert fake.argv("event-commit")[-2:] == ["--", "shipwright_events.jsonl"] and fake.argv("event-push") == ["git", "push", "origin", "HEAD", "--no-follow-tags"]
    assert release_runstate.stored(tmp_path, VERSION)["pr_url"] == "https://example.test/pr/1"


@pytest.mark.parametrize("trunk", ["main", "develop"])
def test_record_event_on_the_trunk_commits_but_never_pushes(tmp_path, plugin_root, trunk):
    fake = event_fake(trunk)
    code, out = release_event.record_event(rec(tmp_path, fake), plugin_root, version=VERSION)
    assert code == 0 and out["on_trunk"] is True and "event-push" not in fake.keys()
    assert fake.argv("event-record")[-1] == f"v{VERSION} — tagged on {trunk}"


@pytest.mark.parametrize(("failing", "later"), [("event-record", "event-stage"), ("event-stage", "event-commit"), ("event-commit", "event-push")])
def test_record_event_stops_at_the_first_failing_tool_as_the_and_chain_did(tmp_path, plugin_root, failing, later):
    fake = event_fake("release/next", **{failing: {"exit": 1, "stderr": "no"}})
    code, out = release_event.record_event(rec(tmp_path, fake), plugin_root, version=VERSION, pr_url=PR)
    assert code == 1 and out["status"] == "failed" and later not in fake.keys()


def test_a_rejected_head_push_is_a_failed_record_event(tmp_path, plugin_root):
    code, out = release_event.record_event(rec(tmp_path, event_fake("release/next", **{"event-push": {"exit": 1}})), plugin_root, version=VERSION, pr_url=PR)
    assert (code, out["reason"], out["pushed"]) == (1, "head_push_failed", False)


def nothing_staged_fake() -> Fake:
    return event_fake("release/next", **{"event-paths": {"stdout": ""}})


def test_no_staged_event_path_means_no_commit_but_the_push_still_runs(tmp_path, plugin_root):
    fake = nothing_staged_fake()
    code, _ = release_event.record_event(rec(tmp_path, fake), plugin_root, version=VERSION, pr_url=PR)
    assert code == 0 and "event-commit" not in fake.keys() and "event-push" in fake.keys()


GOOD = {"verify-local-tag": {"stdout": HEAD + "\n"}, "verify-remote-url": {"stdout": "bare\n"},
        "verify-remote-tag": {"stdout": f"{HEAD}\trefs/tags/v{VERSION}\n"}, "verify-event": {"stdout": "shipwright_events.jsonl\n"},
        "verify-tag": {"stdout": json.dumps({"ok": True, "checks": {}})}}


def close(tmp_path, plugin_root, fake, **kw):
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": HEAD, "tag": f"v{VERSION}", "checks_passed": []})
    kw.setdefault("release_status", "ok")
    kw.setdefault("release_url", "https://example.test/r")
    return release_close.close_phase(rec(tmp_path, fake), plugin_root, version=VERSION, session_id="s-1", clock=lambda: NOW, **kw)


def test_close_phase_in_a_driven_run_keeps_the_canon_records_with_the_canon_marker(tmp_path, plugin_root, monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    seed(tmp_path, mode="pipeline", run_id="changelog-v1.3.0-20261123-093000", branch="release/x", on_trunk=False, pr_url="u")
    fake = Fake(**GOOD, **{"tree-status": {"stdout": ""}})
    code, out = close(tmp_path, plugin_root, fake)
    assert code == 0 and out["status"] == "ok" and fake.keys()[:3] == ["dashboard", "handoff", "phase-history"]
    assert "--canon-marker" in fake.argv("handoff") and fake.argv("handoff")[fake.argv("handoff").index("--phase") + 1] == "changelog"
    history = fake.argv("phase-history")
    assert history[history.index("--run-id") + 1] == "changelog-v1.3.0-20261123-093000"  # the run id the master's gate looks for
    assert json.loads(history[-1]) == {"version": f"v{VERSION}", "outcome": "tagged"}
    assert "restore-derived" not in fake.keys()


def test_close_phase_by_hand_writes_nothing_and_restores_the_derived_snapshots(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u")
    fake = Fake(**GOOD, **{"tree-status": {"stdout": ""}})
    code, out = close(tmp_path, plugin_root, fake)
    assert code == 0 and out["tree_clean"] is True and out["written"] == []
    assert {"dashboard", "handoff", "phase-history"}.isdisjoint(fake.keys()) and "restore-derived" in fake.keys()


@pytest.mark.parametrize("mode", ["standalone", "pipeline"])
def test_close_phase_never_calls_the_orchestrator_update_step(tmp_path, plugin_root, mode):
    seed(tmp_path, mode=mode, branch="main", on_trunk=True)
    fake = Fake(**GOOD, **{"tree-status": {"stdout": ""}})
    close(tmp_path, plugin_root, fake)
    assert "update-step" not in json.dumps(fake.calls) and "orchestrator" not in json.dumps(fake.calls)


def test_a9_the_closing_summary_and_the_status_line_are_printed_by_code(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True, commits=7)
    code, out = close(tmp_path, plugin_root, Fake(**GOOD, **{"tree-status": {"stdout": ""}}))
    text = out["summary"]
    assert out["notices"] == [text] and "SHIPWRIGHT-CHANGELOG COMPLETE" in text
    assert "Version:    v1.3.0" in text and "Commits:    7 categorized" in text and "PR:         skipped (on main)" in text
    assert "Release:    https://example.test/r" in text and text.splitlines()[-1].startswith("Status:     tag_local ok")


def verify_with(tmp_path, plugin_root, fake, state, **kw):
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": HEAD})
    return {c["name"]: c for c in release_verify.verify(rec(tmp_path, fake), plugin_root, version=VERSION, state=state,
                                                        release_status=kw.get("status", "ok"), release_note=kw.get("note", "u"))}


@pytest.mark.parametrize(("name", "answers", "state", "kw"), [
    ("tag_local", {"verify-local-tag": {"stdout": "c" * 40 + "\n"}}, {}, {}),
    ("tag_remote", {"verify-remote-tag": {"stdout": ""}}, {"mode": "pipeline", "on_trunk": True}, {}),
    ("tag_remote", {"verify-remote-tag": {"stdout": f"{'d' * 40}\trefs/tags/v{VERSION}\n"}}, {}, {}),
    ("changelog_matches_tag", {"verify-tag": {"exit": 1, "stdout": json.dumps({"ok": False, "checks": {}})}}, {}, {}),
    ("event_committed", {"verify-event": {"exit": 1}}, {}, {}),
    ("pr_state", {}, {"on_trunk": False, "pr_url": ""}, {}),
    ("pr_state", {"verify-trunk": {"stdout": "e" * 40 + "\trefs/heads/main\n"}, "verify-merged": {"exit": 1}},
     {"on_trunk": False, "pr_url": "u", "autonomy": "autonomous", "mode": "standalone"}, {}),
    ("release_page", {}, {}, {"status": None}),
    ("release_page", {}, {}, {"status": "skipped", "note": ""})])
def test_b4_verify_fails_on_each_broken_outcome(tmp_path, plugin_root, name, answers, state, kw):
    fake = Fake(**{**GOOD, **answers})
    assert verify_with(tmp_path, plugin_root, fake, {"mode": "standalone", "autonomy": "guided", "on_trunk": True, **state}, **kw)[name]["ok"] is False


def test_b4_verify_fails_on_a_decision_drop_left_behind(tmp_path, plugin_root):
    drops = tmp_path / ".shipwright/agent_docs/decision-drops"
    drops.mkdir(parents=True)
    (drops / "INDEX.md").write_text("x", encoding="utf-8")
    assert verify_with(tmp_path, plugin_root, Fake(**GOOD), {"on_trunk": True})["no_decision_drops"]["ok"] is True  # the index is not a drop
    (drops / "run-1.json").write_text("{}", encoding="utf-8")
    assert verify_with(tmp_path, plugin_root, Fake(**GOOD), {"on_trunk": True})["no_decision_drops"]["ok"] is False


def test_b4_a_guided_release_waits_for_the_merge_and_that_is_not_a_failure(tmp_path, plugin_root):
    fake = Fake(**{**GOOD, "verify-remote-tag": {"stdout": ""}})
    checks = verify_with(tmp_path, plugin_root, fake, {"mode": "standalone", "autonomy": "guided", "on_trunk": False, "pr_url": "u"},
                         status="waiting", note="waits for the PR merge")
    assert all(c["ok"] for c in checks.values()), checks


def test_b4_is_read_only_it_runs_no_writing_git_command(tmp_path, plugin_root):
    fake = Fake(**GOOD)
    verify_with(tmp_path, plugin_root, fake, {"on_trunk": True})
    verbs = {a[1] for k, a in fake.calls if a[:1] == ["git"] and k.startswith("verify")}
    assert verbs <= {"rev-parse", "remote", "ls-remote", "grep", "merge-base"}
