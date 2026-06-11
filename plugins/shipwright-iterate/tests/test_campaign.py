"""Tests for campaign_init.py and campaign_progress.py."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tools"))

from campaign_init import init_campaign, validate_independent_strategy
from campaign_progress import _load_status


@pytest.fixture
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    return tmp_path


class TestCampaignInit:
    def test_creates_directory_structure(self, project):
        subs = [
            {"id": "15.0", "slug": "layout", "title": "Dashboard layout", "scope": "Add grid"},
            {"id": "15.1", "slug": "widgets", "title": "Widget system", "scope": "CRUD widgets"},
        ]
        result = init_campaign(project, "iterate-15", "Add dashboard features", subs, "stacked")

        assert result["sub_iterate_count"] == 2
        assert result["branch_strategy"] == "stacked"

        campaign_dir = Path(result["campaign_dir"])
        assert (campaign_dir / "campaign.md").exists()
        assert (campaign_dir / "status.json").exists()
        assert (campaign_dir / "sub-iterates" / "15.0-layout.md").exists()
        assert (campaign_dir / "sub-iterates" / "15.1-widgets.md").exists()

    def test_status_json_has_correct_shape(self, project):
        subs = [{"id": "15.0", "slug": "layout"}]
        result = init_campaign(project, "test-camp", "Test", subs)

        status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
        assert status["campaign"] == "test-camp"
        assert status["branch_strategy"] == "stacked"
        assert len(status["sub_iterates"]) == 1
        assert status["sub_iterates"][0]["id"] == "15.0"
        assert status["sub_iterates"][0]["status"] == "pending"

    def test_spec_path_is_repo_relative(self, project):
        # N1 (trg-196f4aa6): repo-relative POSIX, not a machine-absolute path.
        result = init_campaign(project, "rel-camp", "Test", [{"id": "S1", "slug": "alpha"}])
        sp = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))["sub_iterates"][0]["spec_path"]
        assert sp == ".shipwright/planning/iterate/campaigns/rel-camp/sub-iterates/S1-alpha.md"

    def test_campaign_md_contains_intent(self, project):
        subs = [{"id": "1.0", "slug": "x"}]
        result = init_campaign(project, "slug", "My big intent", subs)
        md = (Path(result["campaign_dir"]) / "campaign.md").read_text(encoding="utf-8")
        assert "My big intent" in md
        assert "branch_strategy: stacked" in md

    def test_sub_iterate_spec_contains_scope(self, project):
        subs = [{"id": "1.0", "slug": "auth", "scope": "Implement MFA flow"}]
        result = init_campaign(project, "s", "Intent", subs)
        spec = (Path(result["campaign_dir"]) / "sub-iterates" / "1.0-auth.md").read_text(encoding="utf-8")
        assert "Implement MFA flow" in spec


class TestValidateIndependentStrategy:
    def test_no_overlap_ok(self):
        subs = [
            {"id": "1.0", "affected_files": ["a.ts", "b.ts"]},
            {"id": "1.1", "affected_files": ["c.ts", "d.ts"]},
        ]
        assert validate_independent_strategy(subs) == []

    def test_overlap_warns(self):
        subs = [
            {"id": "1.0", "affected_files": ["a.ts", "shared.ts"]},
            {"id": "1.1", "affected_files": ["b.ts", "shared.ts"]},
        ]
        warnings = validate_independent_strategy(subs)
        assert len(warnings) == 1
        assert "shared.ts" in warnings[0]


class TestCampaignProgress:
    def _make_campaign(self, project):
        subs = [
            {"id": "15.0", "slug": "layout"},
            {"id": "15.1", "slug": "widgets"},
        ]
        result = init_campaign(project, "test", "Intent", subs)
        return Path(result["campaign_dir"])

    def test_list_units(self, project, capsys):
        campaign_dir = self._make_campaign(project)
        from campaign_progress import cmd_list_units

        class Args:
            pass
        args = Args()
        args.campaign_dir = str(campaign_dir)
        ret = cmd_list_units(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert len(out["sub_iterates"]) == 2

    def test_update_status(self, project, capsys):
        campaign_dir = self._make_campaign(project)
        from campaign_progress import cmd_update_status

        class Args:
            pass
        args = Args()
        args.campaign_dir = str(campaign_dir)
        args.sub_iterate_id = "15.0"
        args.status = "complete"
        args.commit = "abc123"
        args.branch = "iterate/15.0-layout"
        args.tests_passed = 10
        args.tests_total = 10
        ret = cmd_update_status(args)
        assert ret == 0

        status = _load_status(campaign_dir)
        si = status["sub_iterates"][0]
        assert si["status"] == "complete"
        assert si["commit"] == "abc123"
        assert si["branch"] == "iterate/15.0-layout"

    def test_summary(self, project, capsys):
        campaign_dir = self._make_campaign(project)
        from campaign_progress import cmd_summary

        class Args:
            pass
        args = Args()
        args.campaign_dir = str(campaign_dir)
        ret = cmd_summary(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["total"] == 2
        assert out["pending"] == 2
        assert out["complete"] == 0

    def test_update_nonexistent_returns_1(self, project, capsys):
        campaign_dir = self._make_campaign(project)
        from campaign_progress import cmd_update_status

        class Args:
            pass
        args = Args()
        args.campaign_dir = str(campaign_dir)
        args.sub_iterate_id = "99.0"
        args.status = "complete"
        args.commit = None
        args.branch = None
        args.tests_passed = None
        args.tests_total = None
        ret = cmd_update_status(args)
        assert ret == 1


class TestCampaignLifecycleStatus:
    """Producer-owned campaign lifecycle: draft -> active -> complete.

    Consumer side lives in shipwright-webui (PR #96): the Campaigns lane shows a
    campaign iff top-level ``status == 'active'`` (status.json wins, else the
    campaign.md frontmatter ``status:``); ``draft`` and ``complete`` are hidden;
    a *missing* status is legacy and falls back to the prior ``done<total``.
    Values are canonical lowercase ``draft|active|complete``.
    """

    @property
    def VALID(self) -> set[str]:
        # SSoT: the producer's own declared vocabulary, which must equal the
        # webui consumer's VALID_LIFECYCLE set (draft|active|complete).
        from campaign_progress import LIFECYCLE_STATUSES

        return set(LIFECYCLE_STATUSES)

    def _make(self, project) -> Path:
        subs = [{"id": "15.0", "slug": "layout"}, {"id": "15.1", "slug": "widgets"}]
        result = init_campaign(project, "lifecycle", "Intent", subs)
        return Path(result["campaign_dir"])

    def _start(self, campaign_dir: Path) -> int:
        from campaign_progress import cmd_start

        return cmd_start(Namespace(campaign_dir=str(campaign_dir)))

    def _set_sub(self, campaign_dir: Path, sub_id: str, status: str) -> int:
        from campaign_progress import cmd_update_status

        return cmd_update_status(
            Namespace(
                campaign_dir=str(campaign_dir),
                sub_iterate_id=sub_id,
                status=status,
                commit=None,
                branch=None,
                tests_passed=None,
                tests_total=None,
            )
        )

    def _make_legacy(self, project) -> Path:
        """Campaign whose status.json predates the lifecycle field."""
        campaign_dir = self._make(project)
        status = _load_status(campaign_dir)
        status.pop("status", None)
        (campaign_dir / "status.json").write_text(
            json.dumps(status, indent=2), encoding="utf-8"
        )
        return campaign_dir

    # --- init writes draft -------------------------------------------------

    def test_init_writes_draft_to_status_json(self, project):
        status = _load_status(self._make(project))
        assert status["status"] == "draft"

    def test_init_writes_draft_to_frontmatter(self, project):
        md = (self._make(project) / "campaign.md").read_text(encoding="utf-8")
        assert "status: draft" in md

    # --- start -> active ---------------------------------------------------

    def test_start_sets_active(self, project, capsys):
        campaign_dir = self._make(project)
        assert self._start(campaign_dir) == 0
        assert _load_status(campaign_dir)["status"] == "active"
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "active"

    def test_start_on_legacy_adds_active(self, project):
        campaign_dir = self._make_legacy(project)
        assert self._start(campaign_dir) == 0
        assert _load_status(campaign_dir)["status"] == "active"

    # --- update-status auto-complete --------------------------------------

    def test_partial_complete_keeps_active(self, project):
        campaign_dir = self._make(project)
        self._start(campaign_dir)
        self._set_sub(campaign_dir, "15.0", "complete")
        assert _load_status(campaign_dir)["status"] == "active"

    def test_all_complete_sets_complete(self, project):
        campaign_dir = self._make(project)
        self._start(campaign_dir)
        self._set_sub(campaign_dir, "15.0", "complete")
        self._set_sub(campaign_dir, "15.1", "complete")
        assert _load_status(campaign_dir)["status"] == "complete"

    def test_legacy_auto_completes_on_final_sub(self, project):
        campaign_dir = self._make_legacy(project)
        self._set_sub(campaign_dir, "15.0", "complete")
        self._set_sub(campaign_dir, "15.1", "complete")
        assert _load_status(campaign_dir)["status"] == "complete"

    # --- summary prints top-level status ----------------------------------

    def test_summary_prints_status(self, project, capsys):
        from campaign_progress import cmd_summary

        campaign_dir = self._make(project)
        self._start(campaign_dir)
        capsys.readouterr()  # discard start output
        assert cmd_summary(Namespace(campaign_dir=str(campaign_dir))) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "active"

    def test_summary_legacy_status_is_null(self, project, capsys):
        from campaign_progress import cmd_summary

        campaign_dir = self._make_legacy(project)
        assert cmd_summary(Namespace(campaign_dir=str(campaign_dir))) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] is None

    # --- round-trip / boundary probe --------------------------------------

    def test_lifecycle_roundtrip_canonical_values(self, project):
        campaign_dir = self._make(project)
        assert _load_status(campaign_dir)["status"] == "draft"
        self._start(campaign_dir)
        assert _load_status(campaign_dir)["status"] == "active"
        self._set_sub(campaign_dir, "15.0", "complete")
        self._set_sub(campaign_dir, "15.1", "complete")
        final = _load_status(campaign_dir)["status"]
        assert final == "complete"
        assert final in self.VALID
