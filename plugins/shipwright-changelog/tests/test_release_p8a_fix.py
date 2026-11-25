"""Unit P8a, fix round (orchestrator review): the trunk set is additive, ``prepare`` answers ``on_trunk``, the default-branch
lookup names no URL and never waits for a person, and Cancel puts an edited drop back in code.

Each case fails on commit 0b901acf3: there the trunks were ``(default branch, develop)`` only (a ``develop`` default made ``main``
a feature branch, a failed lookup made ``master`` one), ``prepare`` returned no ``on_trunk``, the lookup ran ``git remote get-url``
and passed the URL to ``ls-remote`` with no prompt guard or short timeout, and Cancel after an Edit was a prose instruction.
"""

from __future__ import annotations

import base64
import json
import sys

import pytest

import release
from lib import release_cancel, release_event, release_push, release_runstate
from lib.release_runner import Recorder, subprocess_runner

from .test_release_cli import SETUP, Fake, ok_runner, run_prepare
from .test_release_p4_cli import VERSION, event_fake, seed
from .test_release_p5 import OK, committed

pytestmark = pytest.mark.covers("FR-01.09/AC01")

PR = "https://example.test/pr/1"
FAILED = {"trunk": {"exit": 128, "stderr": "fatal: unable to access 'https://user:s3cret@host.example/x.git/'\n"},
          "trunk-local": {"exit": 1}}


def _symref(branch: str) -> dict:
    return {"stdout": f"ref: refs/heads/{branch}\tHEAD\n{'c' * 40}\tHEAD\nwarning: from https://user:s3cret@host.example/x.git\n"}


def _on(branch: str, **answers) -> Fake:
    return ok_runner(setup={"stdout": json.dumps({**SETUP, "branch": branch})}, **answers)


# ---- item 1: the trunk set is additive ---------------------------------------------------------------------------

@pytest.mark.parametrize(("state", "want"), [
    ({"trunk": "develop", "trunk_source": "remote"}, ("develop", "main")),
    ({"trunk": "main", "trunk_source": "remote"}, ("main", "develop")),
    ({"trunk": "trunk", "trunk_source": "local"}, ("trunk", "main", "develop")),
    ({"trunk": "main", "trunk_source": "fallback"}, ("main", "develop", "master")),
    ({}, ("main", "develop", "master")),  # nothing known: the fallback
])
def test_the_trunks_are_the_default_branch_plus_main_and_develop(state, want):
    assert release_event.trunks(state) == want


def test_with_develop_as_the_default_a_release_on_main_is_a_trunk_release_no_head_push_no_pr(tmp_path, plugin_root):
    code, out = run_prepare(tmp_path, plugin_root, _on("main", trunk=_symref("develop")))
    assert code == 0 and (out["trunk"], out["trunk_source"], out["on_trunk"]) == ("develop", "remote", True)
    fake = event_fake("main")
    code, out = release_event.record_event(Recorder(fake, tmp_path), plugin_root, version="1.3.0")
    assert code == 0 and out["on_trunk"] is True and out["pushed"] is False and "event-push" not in fake.keys()
    assert release_runstate.stored(tmp_path, "1.3.0")["base_branch"] is None  # no PR, so no PR base


# ---- item 2: prepare answers on_trunk; an unknown default makes master a trunk too ---------------------------------

@pytest.mark.parametrize(("branch", "answers", "want"), [
    ("release/next", {"trunk": _symref("main")}, False),
    ("master", {"trunk": _symref("main")}, False),  # the remote says main: master is a branch like any other
    ("master", FAILED, True),  # nothing known: master counts
    ("develop", FAILED, True),
])
def test_prepare_returns_on_trunk_and_the_source(tmp_path, plugin_root, branch, answers, want):
    code, out = run_prepare(tmp_path, plugin_root, _on(branch, **answers))
    assert code == 0 and out["on_trunk"] is want and out["trunk_source"] == ("fallback" if answers is FAILED else "remote")


def test_on_master_with_no_answer_from_the_remote_and_no_origin_head_nothing_is_pushed(tmp_path, plugin_root):
    fake = event_fake("master", **FAILED)  # a run state from before the fix: record-event asks itself
    code, out = release_event.record_event(Recorder(fake, tmp_path), plugin_root, version=VERSION)
    assert code == 0 and out["on_trunk"] is True and out["pushed"] is False and "event-push" not in fake.keys()
    assert release_runstate.stored(tmp_path, VERSION)["trunk_source"] == "fallback"
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="master", on_trunk=True)
    _, push = release_push.push_tag(Recorder(Fake(**{**OK, "push-head": {"stdout": "master\n"}}), tmp_path), plugin_root, version=VERSION)
    assert push["argv"] == ["git", "push", "--atomic", "origin", "master", f"refs/tags/v{VERSION}"]  # the trunk and the tag, once


# ---- items 3 and 4: the lookup names no URL, never prompts, and gives up after 30 s ------------------------------------

def test_the_lookup_asks_origin_by_name_and_no_url_reaches_the_json(tmp_path):
    for answers in ({"trunk": _symref("main")}, FAILED):
        fake = Fake(**answers)
        rec = Recorder(fake, tmp_path)
        release_event.trunk(rec)
        assert "trunk-url" not in fake.keys() and not any("get-url" in a for _, a in fake.calls)
        assert fake.argv("trunk") == ["git", "-c", "credential.interactive=never", "ls-remote", "--symref", "origin", "HEAD"]
        assert "s3cret" not in json.dumps(rec.as_json()) and "host.example" not in json.dumps(rec.as_json())
        assert fake.opts["trunk"] == {"env": {"GIT_TERMINAL_PROMPT": "0"}, "timeout": 30}


def test_a_lookup_that_times_out_falls_back_like_one_that_fails(tmp_path):
    fake = Fake(trunk={"exit": 124, "stderr": "timed out after 30 s"}, **{"trunk-local": {"stdout": "origin/trunk\n"}})
    assert release_event.trunk(Recorder(fake, tmp_path)) == ("trunk", "local")


def test_the_runner_adds_env_to_the_environment_and_stops_at_the_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_P8A_KEEP", "kept")
    show = [sys.executable, "-c", "import os; print(os.environ['SHIPWRIGHT_P8A_KEEP'], os.environ['SHIPWRIGHT_P8A_ADD'])"]
    assert subprocess_runner("k", show, tmp_path, env={"SHIPWRIGHT_P8A_ADD": "added"}).stdout.split() == ["kept", "added"]
    slow = subprocess_runner("k", [sys.executable, "-c", "import time; time.sleep(20)"], tmp_path, timeout=0.5)
    assert (slow.exit, slow.stderr) == (124, "timed out after 0.5 s")


# ---- item 5: Cancel puts the edited drop back, in code -----------------------------------------------------------

def _drops(root, **files: bytes) -> None:
    for name, data in files.items():
        path = root / "CHANGELOG-unreleased.d" / "Added" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _cancel(root, fake=None):
    return release_cancel.cancel(Recorder(fake or Fake(**{"tag-check": {"exit": 1}}), root), root, version=VERSION)


def test_prepare_keeps_the_bytes_of_every_drop(tmp_path, plugin_root):
    _drops(tmp_path, a=b"one\r\n")
    run_prepare(tmp_path, plugin_root, ok_runner())
    stored = release_runstate.stored(tmp_path, "1.3.0")["drops_before"]
    assert {k: base64.b64decode(v) for k, v in stored.items()} == {"CHANGELOG-unreleased.d/Added/a.md": b"one\r\n"}


def test_cancel_puts_back_an_edited_and_a_deleted_drop_byte_for_byte_and_never_deletes_a_new_one(tmp_path):
    _drops(tmp_path, a=b"one\r\n", b=b"two\n")
    seed(tmp_path, drops_before=release_cancel.snapshot(tmp_path))
    _drops(tmp_path, a=b"one, reworded\n", c=b"new\n")
    (tmp_path / "CHANGELOG-unreleased.d" / "Added" / "b.md").unlink()
    code, out = _cancel(tmp_path)
    added = tmp_path / "CHANGELOG-unreleased.d" / "Added"
    assert code == 0 and out["restored"] == ["CHANGELOG-unreleased.d/Added/a.md", "CHANGELOG-unreleased.d/Added/b.md"]
    assert (added / "a.md").read_bytes() == b"one\r\n" and (added / "b.md").read_bytes() == b"two\n"
    assert out["left"] == ["CHANGELOG-unreleased.d/Added/c.md"] and (added / "c.md").is_file()
    assert "48 hours" in out["notices"][0] and "drops_before" not in release_runstate.stored(tmp_path, VERSION)


@pytest.mark.parametrize(("setup", "reason"), [
    (lambda root: None, "no_release_in_progress"),
    (lambda root: seed(root, drops_before={}) or (root / "CHANGELOG.md").write_text(f"## [{VERSION}] - 2026-11-25\n", encoding="utf-8"),
     "release_written"),
    (lambda root: seed(root, drops_before={"../outside.md": "eA=="}), "no_drop_snapshot"),
    (lambda root: seed(root), "no_drop_snapshot"),
])
def test_cancel_refuses_what_it_cannot_put_back(tmp_path, setup, reason):
    setup(tmp_path)
    code, out = _cancel(tmp_path)
    assert (code, out["status"], out["reason"]) == (1, "failed", reason) and not (tmp_path / "outside.md").exists()


def test_cancel_after_the_tag_exists_is_refused_and_the_cli_routes_it(tmp_path, capsys):
    seed(tmp_path, drops_before={})
    code, out = _cancel(tmp_path, Fake(**{"tag-check": {"exit": 0}}))
    assert (code, out["reason"]) == (1, "release_written")
    assert release.main(["cancel", "--project-root", str(tmp_path), "--version", VERSION], runner=Fake(**{"tag-check": {"exit": 1}})) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
