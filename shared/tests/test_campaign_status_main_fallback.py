"""finalize_campaign_status falls back to the MAIN tree for gitignored campaigns.

`campaigns/` is gitignored, so a fresh campaign's dir exists only in the main
tree; a worktree run used to skip the board write and status.json stayed
`active` forever (observed 2026-11-23, dfp-pilot-changelog-p1-p2p).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _campaign_status_fixtures import CAMPAIGN_MD, make_event

import lib.repo_root as repo_root
from lib.campaign_status_io import _CAMPAIGNS_REL, finalize_campaign_status

pytestmark = pytest.mark.covers("FR-01.11")


@pytest.fixture
def trees(tmp_path, monkeypatch):
    main, wt = tmp_path / "main", tmp_path / "wt"
    cdir = main / _CAMPAIGNS_REL / "demo-campaign"
    cdir.mkdir(parents=True)
    (cdir / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
    wt.mkdir()
    monkeypatch.setattr(repo_root, "main_repo_root_or", lambda start, fallback=None: main)
    return main, wt, cdir


def _events(wt, sids):
    (wt / "shipwright_events.jsonl").write_text(
        "\n".join(make_event(s) for s in sids), encoding="utf-8")


def test_writes_status_into_main_tree_when_worktree_lacks_campaign(trees):
    main, wt, cdir = trees
    _events(wt, ["S1", "S2", "S3"])
    out = finalize_campaign_status(wt, {"campaign": "demo-campaign"})
    assert out.get("main_tree") is True, out
    status = json.loads((cdir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "complete"
    assert not (wt / _CAMPAIGNS_REL).exists()  # nothing leaked into the worktree


def test_unknown_campaign_still_skips(trees):
    _, wt, _ = trees
    out = finalize_campaign_status(wt, {"campaign": "nope"})
    assert out["skipped"] is True


def test_main_baseline_never_downgraded(trees):
    _, wt, cdir = trees
    _events(wt, ["S2"])
    base = json.loads(json.dumps({"campaign": "demo-campaign", "status": "active",
        "sub_iterates": [{"id": "S1", "slug": "alpha", "status": "complete", "commit": "abc"}]}))
    (cdir / "status.json").write_text(json.dumps(base), encoding="utf-8")
    finalize_campaign_status(wt, {"campaign": "demo-campaign"})
    status = json.loads((cdir / "status.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s["status"] for s in status["sub_iterates"]}
    assert by_id["S1"] == "complete" and by_id["S2"] == "complete"


def test_worktree_local_campaign_does_not_touch_main(trees):
    main, wt, cdir = trees
    local = wt / _CAMPAIGNS_REL / "demo-campaign"
    local.mkdir(parents=True)
    (local / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
    _events(wt, ["S1"])
    out = finalize_campaign_status(wt, {"campaign": "demo-campaign"})
    assert out.get("main_tree") is False
    assert (local / "status.json").exists() and not (cdir / "status.json").exists()


def test_invalid_slug_skips_before_touching_main(trees):
    _, wt, cdir = trees
    out = finalize_campaign_status(wt, {"campaign": "../evil"})
    assert out["skipped"] is True and not (cdir / "status.json").exists()


def test_integration_real_git_worktree_projects_into_main_tree(tmp_path):
    """Real `git worktree` + the real main-root resolver + the real projection: the
    gitignored campaign lives only in the main checkout, finalize runs from the
    worktree, and the board lands complete in the main tree (no monkeypatching)."""
    import subprocess

    main, wt = tmp_path / "m", tmp_path / "w"
    main.mkdir()

    def git(*a, cwd=main):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                       env={**__import__("os").environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    git("init", "-q")
    (main / ".gitignore").write_text("/.shipwright/planning/iterate/campaigns/\n", encoding="utf-8")
    (main / "f.txt").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("worktree", "add", "-q", str(wt), "-b", "iterate/demo")
    cdir = main / _CAMPAIGNS_REL / "demo-campaign"
    cdir.mkdir(parents=True)
    (cdir / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
    _events(wt, ["S1", "S2", "S3"])
    out = finalize_campaign_status(wt, {"campaign": "demo-campaign"})
    assert out.get("main_tree") is True, out
    assert json.loads((cdir / "status.json").read_text(encoding="utf-8"))["status"] == "complete"
    assert not (wt / _CAMPAIGNS_REL).exists()
