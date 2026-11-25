"""Unit P8a (operator re-scope 2026-11-25): the bugs and contradictions of D7, D8, D12 and D24, each with a case the old code
or prose fails.

Old behaviour, per decision: F5 (D24) named ``main`` as the trunk and the PR base everywhere, so a ``master`` repository was a
"feature branch" with a PR against a branch that does not exist; F2 (D12) ran the real aggregation before the preview, so Cancel
had already written ``CHANGELOG.md`` and consumed the drops, and a guided-preview release filed upgrade-note drops before it asked;
F3 (D7) opened the PR before the branch was pushed; Q2 (D8) stated the merge rule twice in two ways. In-process with an injected
runner; the prose cases read the live ``SKILL.md`` and ``first-actions.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lib import release_event, release_push, release_runstate, release_verify
from lib.release_runner import Recorder

from .test_release_cli import ROWS, Fake, ok_runner, run_prepare
from .test_release_p3_fixes import _runner
from .test_release_p4_cli import VERSION, event_fake, seed
from .test_release_p5 import OK, committed

pytestmark = pytest.mark.covers("FR-01.09/AC01")

PLUGIN = Path(__file__).resolve().parents[1]
SKILL_DIR = PLUGIN / "skills" / "changelog"
PR = "https://example.test/pr/1"


def _skill() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def _symref(branch: str) -> dict:
    return {"stdout": f"ref: refs/heads/{branch}\tHEAD\n{'c' * 40}\tHEAD\n"}


# ---- F5 (D24): the default branch comes from the remote ------------------------------------------------------

@pytest.mark.parametrize(("answers", "want"), [
    ({"trunk-url": {"stdout": "bare\n"}, "trunk": _symref("master")}, "master"),
    ({"trunk-url": {"stdout": "bare\n"}, "trunk": {"exit": 128}, "trunk-local": {"stdout": "origin/trunk\n"}}, "trunk"),
    ({"trunk-url": {"stdout": ""}, "trunk-local": {"exit": 1}}, "main"),
    ({"trunk-url": {"stdout": "bare\n"}, "trunk": _symref("-x;rm")}, "main"),  # never an unsafe name in a push line or --base
])
def test_the_trunk_is_the_remotes_default_branch(tmp_path, answers, want):
    fake = Fake(**answers)
    found = release_event.trunk(Recorder(fake, tmp_path))
    assert found == want
    if answers["trunk-url"]["stdout"]:
        assert fake.argv("trunk")[-3:] == ["--end-of-options", "bare", "HEAD"]


def test_prepare_stores_and_returns_the_trunk(tmp_path, plugin_root):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(**{"trunk-url": {"stdout": "bare\n"}, "trunk": _symref("master")}))
    stored = release_runstate.stored(tmp_path, VERSION)
    assert code == 0 and out["trunk"] == "master" and stored["trunk"] == "master"


def test_record_event_on_the_remotes_default_branch_is_the_trunk_case(tmp_path, plugin_root):
    seed(tmp_path, trunk="master")
    fake = event_fake("master")
    code, out = release_event.record_event(Recorder(fake, tmp_path), plugin_root, version=VERSION)
    assert code == 0 and out["on_trunk"] is True and "event-push" not in fake.keys()  # the trunk is pushed once, with the tag
    assert release_runstate.stored(tmp_path, VERSION)["base_branch"] is None


def test_record_event_keeps_the_default_branch_as_the_prs_base(tmp_path, plugin_root):
    seed(tmp_path, trunk="master")
    code, out = release_event.record_event(Recorder(event_fake("release/x"), tmp_path), plugin_root, version=VERSION, pr_url=PR)
    stored = release_runstate.stored(tmp_path, VERSION)
    assert code == 0 and out["on_trunk"] is False and (stored["base_branch"], stored["trunk"]) == ("master", "master")


def test_record_event_asks_the_remote_when_the_run_state_has_no_trunk(tmp_path, plugin_root):
    fake = event_fake("release/x", **{"trunk-url": {"stdout": "bare\n"}, "trunk": _symref("trunk")})
    release_event.record_event(Recorder(fake, tmp_path), plugin_root, version=VERSION, pr_url=PR)
    assert release_runstate.stored(tmp_path, VERSION)["base_branch"] == "trunk"


def test_push_tag_on_a_master_trunk_gets_the_atomic_line_for_master(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="master", on_trunk=True, trunk="master")
    fake = Fake(**{**OK, "push-head": {"stdout": "master\n"}})
    code, out = release_push.push_tag(Recorder(fake, tmp_path), plugin_root, version=VERSION)
    assert code == 0 and out["argv"] == ["git", "push", "--atomic", "origin", "master", f"refs/tags/v{VERSION}"]


def test_push_tag_still_refuses_a_branch_that_is_not_the_stored_trunk(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True, trunk="master")
    code, out = release_push.push_tag(Recorder(Fake(**OK), tmp_path), plugin_root, version=VERSION)
    assert code == 1 and out["reason"] == "branch_not_a_trunk"


def test_the_skill_opens_the_pr_against_the_trunk_prepare_returned():
    skill = _skill()
    assert '--base "{trunk}"' in skill and "--base main" not in skill and "(not main/develop)" not in skill


# ---- F2 (D12): the preview writes nothing; the real run comes after Accept --------------------------------------

@pytest.mark.covers("FR-01.09/AC10")
def test_a_preview_question_alone_defers_the_upgrade_note(tmp_path, plugin_root):
    rows = [{**r, "policy": "interactive"} if r["gate_id"] == "changelog.entry-preview" else r for r in ROWS]
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({"autonomy": "autonomous"}), encoding="utf-8")
    fake = _runner(tmp_path, gates={"stdout": json.dumps({"gates": rows})})
    _, out = run_prepare(tmp_path, plugin_root, fake)
    assert out["gates"]["version"] == "auto" and out["gates"]["preview"] == "ask"
    assert out["upgrade_notes"]["status"] == "action_drop_deferred" and "upgrade-note-drop" not in fake.keys()
    assert not (tmp_path / "CHANGELOG-unreleased.d").exists()  # Cancel after this preview leaves no drop behind


@pytest.mark.covers("FR-01.09/AC10")
def test_the_skill_asks_after_the_dry_run_and_writes_only_after_accept():
    skill = _skill()
    dry = skill.index('aggregate --project-root "$(pwd)" --version "{version}" --dry-run')
    question = skill.index('question: "Review the changelog entry. Proceed?"')
    real = skill.index('aggregate --project-root "$(pwd)" --version "{version}"\n```')
    assert dry < question < real < skill.index("## Step 5.3")
    step5 = skill[skill.index("## Step 5: Preview and Confirm"):skill.index("## Step 5.3")]
    assert "**Cancel:**" in step5 and "Nothing was written" in step5
    assert "**Edit:**" in step5 and "drop file" in step5 and "preview call of Step 4 again" in step5


# ---- F3 (D7): the branch is pushed right before the PR is opened ------------------------------------------------

def test_the_skill_pushes_the_branch_right_before_gh_pr_create():
    blocks = re.findall(r"```bash\n(.*?)```", _skill(), flags=re.S)
    starts = [b.split()[0:3] for b in blocks]
    push = starts.index(["git", "push", "origin"])
    assert blocks[push].strip() == "git push origin HEAD --no-follow-tags" and blocks[push + 1].startswith("gh pr create")


# ---- Q2 (D8): one merge rule, stated the same way in both texts --------------------------------------------------

def test_skill_and_first_actions_state_the_same_merge_rule():
    skill = " ".join(_skill().split())
    first = " ".join((SKILL_DIR / "references" / "first-actions.md").read_text(encoding="utf-8").split())
    assert "A hand-invoked release with autonomy `autonomous` or `unattended`:** after recording the event, merge immediately" in skill
    assert "**Any other hand-invoked release:** the PR stays open" in skill and "**A driven run** neither merges nor waits" in skill
    assert "a driven run never merges it" in first and "merges it at once only with autonomy `autonomous` or `unattended`" in first
    assert "any other hand-invoked release leaves it open for a person" in first and "not auto-merged" not in first


def test_the_closing_verify_checks_the_stored_trunk_without_asking_again(tmp_path):
    fake = Fake(**{"verify-remote-url": {"stdout": "bare\n"}})
    reached, base, _ = release_verify.on_base(Recorder(fake, tmp_path), {"trunk": "master"}, "a" * 40)
    assert (reached, base) == (True, "master") and "verify-base" not in fake.keys() and fake.argv("verify-fetch")[-1] == "master"


def test_neither_head_push_carries_the_release_tag(tmp_path, plugin_root):
    fake = event_fake("release/x")
    seed(tmp_path, trunk="main")
    release_event.record_event(Recorder(fake, tmp_path), plugin_root, version=VERSION, pr_url=PR)
    assert fake.argv("event-push")[-1] == "--no-follow-tags"  # push.followTags would send the tag before the merge
    assert "git push origin HEAD --no-follow-tags" in _skill()
