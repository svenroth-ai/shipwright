"""Unit tests for the campaign-status pure helpers + file-loading wrapper.

Covers ``shared/scripts/lib/campaign_status.py`` (campaign S2, anchor
trg-fda5f7a3): skeleton parse, never-downgrade ladder, ``all_subs_complete``
(moved canonical SSoT), and the ``regenerate_campaign_status`` wrapper.
The projection core itself is exercised in ``test_campaign_status_project.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _campaign_status_fixtures import CAMPAIGN_MD, make_committed, make_event

from lib.campaign_status import (
    all_subs_complete,
    merge_status,
    parse_campaign_skeleton,
    regenerate_campaign_status,
)


class TestParseSkeleton:
    def test_basic_order_and_fields(self):
        sk = parse_campaign_skeleton(CAMPAIGN_MD)
        assert [s["id"] for s in sk] == ["S1", "S2", "S3"]
        assert sk[0] == {"id": "S1", "slug": "alpha", "title": "First"}
        assert sk[2]["slug"] == "charlie"

    def test_ignores_status_column(self):
        sk = parse_campaign_skeleton(CAMPAIGN_MD)
        assert all("status" not in s for s in sk)

    def test_missing_table_raises(self):
        with pytest.raises(ValueError):
            parse_campaign_skeleton("# Campaign\n\n## Intent\n\nno table here\n")

    def test_duplicate_id_raises(self):
        md = CAMPAIGN_MD.replace("| S2 | bravo", "| S1 | bravo")
        with pytest.raises(ValueError):
            parse_campaign_skeleton(md)

    def test_empty_id_raises(self):
        md = CAMPAIGN_MD.replace("| S2 | bravo | Second |", "|  | bravo | Second |")
        with pytest.raises(ValueError):
            parse_campaign_skeleton(md)


class TestMergeStatus:
    def test_never_downgrade_complete_over_pending(self):
        assert merge_status("complete", "pending") == "complete"
        assert merge_status("pending", "complete") == "complete"

    def test_in_progress_over_pending(self):
        assert merge_status("in_progress", "pending") == "in_progress"

    def test_in_progress_advances_to_complete(self):
        # S3-reuse guard: a committed in_progress sub with a work_completed
        # event (projected complete) must advance, not stick at in_progress.
        assert merge_status("in_progress", "complete") == "complete"

    def test_failed_preserved_against_pending(self):
        assert merge_status("failed", "pending") == "failed"
        assert merge_status("escalated", "pending") == "escalated"

    def test_failed_superseded_by_complete(self):
        # a successful re-run (work_completed event) supersedes a stale failed
        assert merge_status("failed", "complete") == "complete"
        assert merge_status("escalated", "complete") == "complete"

    def test_no_keyerror_on_unknown_status(self):
        # defensive: an off-ladder committed string must not crash
        assert merge_status("weird", "pending") in ("weird", "pending")

    def test_none_treated_as_pending(self):
        assert merge_status(None, "complete") == "complete"
        assert merge_status(None, None) == "pending"


class TestAllSubsComplete:
    def test_true_when_all_complete(self):
        assert all_subs_complete({"sub_iterates": [{"status": "complete"}, {"status": "complete"}]})

    def test_false_when_any_incomplete(self):
        assert not all_subs_complete({"sub_iterates": [{"status": "complete"}, {"status": "pending"}]})

    def test_false_on_empty(self):
        assert not all_subs_complete({"sub_iterates": []})
        assert not all_subs_complete({})


class TestRegenerateWrapper:
    def _write_campaign(self, tmp_path, *, with_status=True):
        cdir = tmp_path / "campaigns" / "demo-campaign"
        (cdir / "sub-iterates").mkdir(parents=True)
        (cdir / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
        if with_status:
            (cdir / "status.json").write_text(
                json.dumps(make_committed(), indent=2), encoding="utf-8")
        return cdir

    def test_missing_campaign_md_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            regenerate_campaign_status(empty, tmp_path / "shipwright_events.jsonl")

    def test_roundtrip_from_files(self, tmp_path):
        cdir = self._write_campaign(tmp_path)
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text("\n".join([make_event("S1"), make_event("S2"), make_event("S3")]),
                      encoding="utf-8")
        status, summary = regenerate_campaign_status(cdir, ev)
        assert [s["status"] for s in status["sub_iterates"]] == ["complete"] * 3
        assert status["status"] == "complete"

    def test_no_events_log_ok(self, tmp_path):
        cdir = self._write_campaign(tmp_path)
        status, _ = regenerate_campaign_status(cdir, tmp_path / "nope.jsonl")
        assert [s["status"] for s in status["sub_iterates"]] == ["pending"] * 3

    def test_fills_missing_spec_path(self, tmp_path):
        # fresh campaign (no committed status.json) -> wrapper derives spec_path
        cdir = self._write_campaign(tmp_path, with_status=False)
        status, _ = regenerate_campaign_status(cdir, tmp_path / "nope.jsonl")
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["S1"]["spec_path"].endswith("S1-alpha.md")

    def test_idempotent_serialized(self, tmp_path):
        cdir = self._write_campaign(tmp_path)
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text("\n".join([make_event("S1"), make_event("S2")]), encoding="utf-8")
        first, _ = regenerate_campaign_status(cdir, ev)
        (cdir / "status.json").write_text(json.dumps(first, indent=2), encoding="utf-8")
        second, _ = regenerate_campaign_status(cdir, ev)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_corrupt_committed_status_rebuilds_with_warning(self, tmp_path):
        # external-review: a corrupt committed status.json must not crash the
        # rebuild (it is the file we are regenerating).
        cdir = self._write_campaign(tmp_path)
        (cdir / "status.json").write_text("{ broken json", encoding="utf-8")
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text(make_event("S1"), encoding="utf-8")
        status, summary = regenerate_campaign_status(cdir, ev)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["S1"]["status"] == "complete"  # rebuilt from skeleton + event
        assert [s["id"] for s in status["sub_iterates"]] == ["S1", "S2", "S3"]
        assert any("corrupt" in w.lower() for w in summary["warnings"])
