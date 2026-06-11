"""Repo-relative ``spec_path`` helpers + migration (N1, trg-196f4aa6).

The campaign-status producers used to write a machine-ABSOLUTE sub-iterate
``spec_path`` (``C:\\…``), useless on a fresh clone / a Linux WebUI. These tests
pin: the pure helpers, the projection self-heal (carry + fill), and the one-off
migration over tracked campaigns (idempotent, no spurious churn, no downgrade).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _campaign_status_fixtures import CAMPAIGN_MD, make_committed, make_event

from lib.campaign_paths import campaign_spec_path, relativize_spec_path
from lib.campaign_status import project_campaign_status, regenerate_campaign_status
from lib.campaign_status_io import relativize_tracked_spec_paths

_ABS_WIN = r"C:\01_Development\shipwright\.shipwright\planning\iterate\campaigns\demo\sub-iterates\S1-alpha.md"
_ABS_POSIX = "/home/runner/work/shipwright/.shipwright/planning/iterate/campaigns/demo/sub-iterates/S1-alpha.md"
_REL = ".shipwright/planning/iterate/campaigns/demo/sub-iterates/S1-alpha.md"


class TestRelativizeSpecPath:
    def test_windows_absolute_anchored(self):
        assert relativize_spec_path(_ABS_WIN) == _REL

    def test_posix_absolute_anchored(self):
        assert relativize_spec_path(_ABS_POSIX) == _REL

    def test_already_relative_unchanged(self):
        assert relativize_spec_path(_REL) == _REL

    def test_idempotent(self):
        once = relativize_spec_path(_ABS_WIN)
        assert relativize_spec_path(once) == once

    def test_none_and_empty_passthrough(self):
        assert relativize_spec_path(None) is None
        assert relativize_spec_path("") == ""

    def test_no_drive_no_backslash(self):
        out = relativize_spec_path(_ABS_WIN)
        assert "\\" not in out and ":" not in out


class TestCampaignSpecPath:
    def test_under_shipwright_is_repo_relative(self, tmp_path):
        cdir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "demo"
        out = campaign_spec_path(cdir, "S1", "alpha")
        assert out == _REL
        assert "\\" not in out and ":" not in out

    def test_fixture_dir_falls_back_to_dir_relative(self, tmp_path):
        # campaign_dir not under .shipwright -> campaign-dir-relative
        out = campaign_spec_path(tmp_path / "campaigns" / "demo", "S2", "bravo")
        assert out == "sub-iterates/S2-bravo.md"


class TestProjectionSelfHeals:
    def test_carry_relativizes_absolute(self):
        committed = make_committed(S1={"status": "complete", "spec_path": _ABS_WIN})
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, [], "demo-campaign")
        s1 = {s["id"]: s for s in status["sub_iterates"]}["S1"]
        assert s1["spec_path"] == _REL
        assert s1["status"] == "complete"  # never-downgrade intact

    def test_fill_is_relative(self, tmp_path):
        cdir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "demo-campaign"
        (cdir / "sub-iterates").mkdir(parents=True)
        (cdir / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")  # fresh: no status.json
        status, _ = regenerate_campaign_status(cdir, tmp_path / "nope.jsonl")
        for sub in status["sub_iterates"]:
            assert sub["spec_path"].startswith(".shipwright/planning/iterate/campaigns/demo-campaign/")
            assert "\\" not in sub["spec_path"]


class TestMigration:
    def _campaign(self, tmp_path, *, abs_paths=True):
        cdir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "demo-campaign"
        (cdir / "sub-iterates").mkdir(parents=True)
        (cdir / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
        committed = make_committed()
        if abs_paths:
            for s in committed["sub_iterates"]:
                s["spec_path"] = (rf"C:\X\.shipwright\planning\iterate\campaigns\demo-campaign"
                                  rf"\sub-iterates\{s['id']}-{s['slug']}.md")
        (cdir / "status.json").write_text(json.dumps(committed, indent=2), encoding="utf-8")
        return cdir

    def test_rewrites_absolute_to_relative(self, tmp_path):
        cdir = self._campaign(tmp_path)
        out = relativize_tracked_spec_paths(tmp_path)
        assert out["demo-campaign"] == 3
        data = json.loads((cdir / "status.json").read_text(encoding="utf-8"))
        for s in data["sub_iterates"]:
            assert s["spec_path"] == f".shipwright/planning/iterate/campaigns/demo-campaign/sub-iterates/{s['id']}-{s['slug']}.md"

    def test_idempotent_second_run_noop(self, tmp_path):
        self._campaign(tmp_path)
        relativize_tracked_spec_paths(tmp_path)
        again = relativize_tracked_spec_paths(tmp_path)
        assert again["demo-campaign"] == 0

    def test_regenerate_after_migration_keeps_relative_no_downgrade(self, tmp_path):
        cdir = self._campaign(tmp_path)
        relativize_tracked_spec_paths(tmp_path)
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text(make_event("S1"), encoding="utf-8")
        status, _ = regenerate_campaign_status(cdir, ev)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["S1"]["status"] == "complete"
        for s in status["sub_iterates"]:
            assert s["spec_path"].startswith(".shipwright/") and "\\" not in s["spec_path"]
