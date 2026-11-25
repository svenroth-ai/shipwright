"""Unit P5: ``release.py push-tag`` (decides, never pushes), the shared "tip is the release" rule, the public tag check, the thin prose.

``push-tag`` answers which literal push line to run (F1a), whether to wait for the merge (F1b) or why not to push (F4); the push itself stays a line in
``SKILL.md`` so the release guard hook sees it. In-process with an injected runner, and on real git where the rule is git's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import release
from lib import release_commit, release_event, release_push, release_runstate, release_verify
from lib.release_runner import Recorder
from .test_release_cli import Fake
from .test_release_p4_cli import HEAD, VERSION, rec, seed

pytestmark = pytest.mark.covers("FR-01.09/AC01")

PLUGIN = Path(__file__).resolve().parents[1]
SKILL_DIR = PLUGIN / "skills" / "changelog"
HOOKS = PLUGIN / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))

OK = {"push-tag-commit": {"stdout": HEAD + "\n"}, "push-head": {"stdout": "main\n"}, "push-tip": {"stdout": HEAD + "\n"}}
MERGED = {**OK, "verify-base": {"stdout": "origin/develop\n"}, "verify-remote-url": {"stdout": "bare\n"}}
PR = "https://example.test/pr/1"
EVENT_LINE = "shipwright_events.jsonl" + chr(10)


def committed(tmp_path: Path) -> None:
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": HEAD, "tag": f"v{VERSION}", "checks_passed": []})


def ask(tmp_path: Path, plugin_root: Path, fake: Fake):
    return release_push.push_tag(rec(tmp_path, fake), plugin_root, version=VERSION)


def feature(tmp_path: Path, **state) -> None:
    committed(tmp_path)
    seed(tmp_path, **{"mode": "standalone", "branch": "release/x", "on_trunk": False, "pr_url": PR, "base_branch": "main", **state})


# ---- F1a: which line to run --------------------------------------------------------------------------------

def test_a_feature_branch_gets_the_tag_only_line_once_the_release_commit_is_on_the_base(tmp_path, plugin_root):
    feature(tmp_path)
    fake = Fake(**MERGED)
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 0 and out["status"] == "ok" and out["argv"] == ["git", "push", "origin", f"refs/tags/v{VERSION}"]
    assert out["line"] == f"git push origin refs/tags/v{VERSION}" and "push-tags" not in fake.keys()  # decides, never pushes
    assert fake.keys().index("verify-fetch") < fake.keys().index("verify-merged") and fake.argv("verify-fetch")[-1] == "main"


def test_the_trunk_gets_the_atomic_line_for_the_recorded_trunk(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="develop", on_trunk=True)

    def git(argv):
        return {"stdout": "\x01\nshipwright_events.jsonl\n"} if argv[1] == "log" else {}

    fake = Fake(**{**OK, "push-head": {"stdout": "develop\n"}, "push-tip": {"stdout": "b" * 40 + "\n"}, "push-git": git})
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 0 and out["argv"] == ["git", "push", "--atomic", "origin", "develop", f"refs/tags/v{VERSION}"]
    assert [a for k, a in fake.calls if k == "push-git"][0][:3] == ["git", "merge-base", "--is-ancestor"]  # the hook's rule, in the hook's order


def test_a_closed_unmerged_pr_is_refused_with_its_own_reason(tmp_path, plugin_root):
    feature(tmp_path)
    fake = Fake(**MERGED, **{"verify-merged": {"exit": 1}, "push-pr-view": {"stdout": json.dumps({"state": "CLOSED", "mergeCommit": None})}})
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "pr_closed_unmerged" and "line" not in out


@pytest.mark.parametrize("trunk", ["main", "develop"])
def test_the_skill_trunk_line_names_the_trunk_you_are_on(tmp_path, plugin_root, trunk):
    skill = " ".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split())
    template = 'git push --atomic origin {branch} "refs/tags/v{version}"'
    assert template in skill
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch=trunk, on_trunk=True)
    fake = Fake(**{**OK, "push-head": {"stdout": trunk + "\n"}, "push-tip": {"stdout": "b" * 40 + "\n"},
                   "push-git": lambda argv: {"stdout": "\x01\n" + EVENT_LINE} if argv[1] == "log" else {}})
    line = ask(tmp_path, plugin_root, fake)[1]["line"]
    assert line == template.replace("{branch}", trunk).replace("{version}", VERSION).replace('"', "")


def test_the_skill_carries_the_literal_lines_push_tag_prints(tmp_path, plugin_root):
    """The prose line and the printed argv are the same push, including --atomic on the trunk."""
    skill = " ".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split())
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake(**{**OK, "push-tip": {"stdout": "b" * 40 + "\n"}, "push-git": lambda argv: {"stdout": "\x01\nshipwright_events.jsonl\n"} if argv[1] == "log" else {}})
    trunk = ask(tmp_path, plugin_root, fake)[1]["line"]
    assert trunk == f"git push --atomic origin main refs/tags/v{VERSION}"
    assert 'git push --atomic origin {branch} "refs/tags/v{version}"' in skill and 'git push origin "refs/tags/v{version}"' in skill
    assert "--atomic" in trunk and "git push" not in skill.replace('git push --atomic origin {branch} "refs/tags/v{version}"', "").replace('git push origin "refs/tags/v{version}"', "").replace("git push origin HEAD", "")


# ---- F1b, one key ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("autonomy", ["guided", "autonomous", "unattended", None])
@pytest.mark.parametrize("mode", ["standalone", "pipeline"])
def test_push_tag_and_the_verify_agree_on_who_waits_for_the_merge(tmp_path, plugin_root, mode, autonomy):
    feature(tmp_path, mode=mode, autonomy=autonomy)
    state = {"mode": mode, "autonomy": autonomy, "on_trunk": False}
    code, out = ask(tmp_path, plugin_root, Fake(**MERGED, **{"verify-merged": {"exit": 1}, "push-pr-view": {"stdout": json.dumps({"state": "OPEN"})}}))
    waits = release_verify.waits_for_merge(state)
    assert waits is (mode == "standalone")
    assert (out["status"] == "waiting_for_merge") is waits and (out["status"] == "ok") is (not waits) and code == (1 if waits else 0)


def test_a_waiting_release_is_not_told_the_pr_is_merged_when_it_is_open(tmp_path, plugin_root):
    feature(tmp_path)
    fake = Fake(**MERGED, **{"verify-merged": {"exit": 1}, "push-pr-view": {"stdout": json.dumps({"state": "OPEN", "mergeCommit": None})}})
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 1 and out["status"] == "waiting_for_merge" and fake.argv("push-pr-view")[:4] == ["gh", "pr", "view", PR]


def test_a_squash_merged_pr_is_refused_not_left_waiting_for_good(tmp_path, plugin_root):
    feature(tmp_path)
    fake = Fake(**MERGED, **{"verify-merged": {"exit": 1}, "push-pr-view": {"stdout": json.dumps({"state": "MERGED", "mergeCommit": {"oid": "c" * 40}})}})
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 1 and out["status"] == "refused" and out["reason"] == "merged_without_release_commit"
    assert "not on the trunk" in out["detail"] and "run this again" not in out["detail"] and "line" not in out


@pytest.mark.parametrize("view", [{"stdout": "not json"}, {"exit": 1}, {"stdout": "[]"}])
def test_an_unreadable_pr_view_keeps_the_release_waiting(tmp_path, plugin_root, view):
    feature(tmp_path)
    code, out = ask(tmp_path, plugin_root, Fake(**MERGED, **{"verify-merged": {"exit": 1}, "push-pr-view": view}))
    assert out["status"] == "waiting_for_merge"


def test_a_missing_pr_url_cannot_prove_a_merge(tmp_path, plugin_root):
    feature(tmp_path, pr_url="")
    fake = Fake(**MERGED, **{"verify-merged": {"exit": 1}})
    assert ask(tmp_path, plugin_root, fake)[1]["status"] == "waiting_for_merge" and "push-pr-view" not in fake.keys()


def test_an_unreadable_merge_state_is_refused(tmp_path, plugin_root):
    feature(tmp_path)
    code, out = ask(tmp_path, plugin_root, Fake(**MERGED, **{"verify-fetch": {"exit": 1, "stderr": "could not resolve host"}}))
    assert code == 1 and out["status"] == "refused" and out["reason"] == "merge_state_unknown" and "could not resolve host" in out["detail"]


# ---- the base the merge check reads --------------------------------------------------------------------------

def test_the_merge_check_reads_the_base_the_pr_was_opened_against_not_origin_head(tmp_path, plugin_root):
    feature(tmp_path, base_branch="main")
    fake = Fake(**MERGED)  # origin/HEAD says develop
    ask(tmp_path, plugin_root, fake)
    assert fake.argv("verify-fetch")[-1] == "main" and "verify-base" not in fake.keys()


def test_record_event_keeps_the_base_of_the_pr_and_none_on_the_trunk(tmp_path, plugin_root):
    from .test_release_p4_cli import event_fake
    release_event.record_event(rec(tmp_path, event_fake("release/x")), plugin_root, version=VERSION, pr_url=PR)
    assert release_runstate.stored(tmp_path, VERSION)["base_branch"] == "main"  # no trunk stored and the fake remote names none: main (F5 fallback)
    release_event.record_event(rec(tmp_path, event_fake("develop")), plugin_root, version=VERSION)
    assert release_runstate.stored(tmp_path, VERSION)["base_branch"] is None


def test_an_unknown_merge_state_names_what_failed_only_when_a_commit_was_recorded(tmp_path):
    fake = Fake(**{"verify-fetch": {"exit": 0}, "verify-merged": {"exit": 128}})
    assert release_verify.on_base(Recorder(fake, tmp_path), {"base_branch": "main"}, HEAD)[2] == "git could not tell"
    assert release_verify.on_base(Recorder(fake, tmp_path), {"base_branch": "main"}, None)[2] == "no release commit recorded"


# ---- refusals ----------------------------------------------------------------------------------------------

def test_nothing_is_decided_for_a_release_that_was_not_cut_or_whose_event_was_not_recorded(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake()
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 1 and out["status"] == "refused" and out["reason"] == "release_not_committed" and fake.calls == []
    committed(tmp_path)
    seed(tmp_path, branch=None)
    assert ask(tmp_path, plugin_root, fake)[1]["reason"] == "event_not_recorded" and fake.calls == []


def test_a_state_without_a_mode_or_with_a_foreign_branch_name_gets_no_line(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, branch="main", on_trunk=True, mode=None)
    fake = Fake()
    assert ask(tmp_path, plugin_root, fake)[1]["reason"] == "run_state_missing"
    seed(tmp_path, mode="standalone", branch="+main")
    assert ask(tmp_path, plugin_root, fake)[1]["reason"] == "branch_not_a_trunk" and fake.calls == []


def test_a_moved_tag_or_a_checkout_on_another_branch_gets_no_line(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    moved = Fake(**{**OK, "push-tag-commit": {"stdout": "b" * 40 + "\n"}})
    assert ask(tmp_path, plugin_root, moved)[1]["reason"] == "tag_not_the_release_commit" and "push-head" not in moved.keys()
    other = Fake(**{**OK, "push-head": {"stdout": "other\n"}})
    assert ask(tmp_path, plugin_root, other)[1]["reason"] == "head_not_on_branch"


def test_the_trunk_that_moved_beyond_the_event_commit_gets_no_line(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake(**{**OK, "push-tip": {"stdout": "b" * 40 + "\n"}, "push-git": lambda argv: {"stdout": "\x01\nsrc/app.py\n"} if argv[1] == "log" else {}})
    code, out = ask(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "head_moved_since_release" and "argv" not in out


def test_the_cli_dispatches_push_tag_and_prints_the_decision(tmp_path, plugin_root, capsys):
    feature(tmp_path, mode="pipeline")
    fake = Fake(**OK)
    code = release.main(["push-tag", "--project-root", str(tmp_path), "--version", VERSION], runner=fake)
    assert code == 0 and json.loads(capsys.readouterr().out)["line"] == f"git push origin refs/tags/v{VERSION}" and "push-tags" not in fake.keys()


@pytest.mark.parametrize(("mode", "autonomy", "pending"), [("standalone", "guided", True), ("standalone", "autonomous", False), ("pipeline", "guided", False)])
def test_only_a_release_left_for_a_person_may_have_its_tag_missing_at_the_close(mode, autonomy, pending):
    """An autonomous hand-invoked release merged at once: a missing remote tag at the close is a failure, not a wait."""
    assert release_verify.tag_may_be_pending({"mode": mode, "autonomy": autonomy, "on_trunk": False}) is pending
