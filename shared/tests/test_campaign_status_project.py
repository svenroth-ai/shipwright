"""Unit tests for ``project_campaign_status`` — the pure projection core (S2).

Exact projection (AC1), never-downgrade (AC2), top-level event keys + commit=''
no-clobber (AC4), ts-latest selection, skeleton-driven order, non-skeleton drop,
lifecycle recompute (AC5), and corrupt-line robustness.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _campaign_status_fixtures import CAMPAIGN_MD, make_committed, make_event

from lib.campaign_status import project_campaign_status


def _by_id(status):
    return {s["id"]: s for s in status["sub_iterates"]}


class TestProjectCore:
    def test_exact_when_all_stamped(self):
        # AC1: every sub has a matching event -> all complete, skeleton-ordered
        events = [make_event("S1"), make_event("S2"), make_event("S3")]
        status, summary = project_campaign_status(CAMPAIGN_MD, make_committed(), events, "demo-campaign")
        assert [s["status"] for s in status["sub_iterates"]] == ["complete"] * 3
        assert summary["matched_events"] == 3
        assert summary["complete"] == 3
        assert status["status"] == "complete"  # AC5 lifecycle

    def test_never_downgrade_unstamped_complete(self):
        # AC2: S2 complete in committed, NO event -> stays complete
        committed = make_committed(S2={"status": "complete", "commit": "cafe123"})
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, [], "demo-campaign")
        by_id = _by_id(status)
        assert by_id["S2"]["status"] == "complete"
        assert by_id["S2"]["commit"] == "cafe123"
        assert by_id["S1"]["status"] == "pending"

    def test_reads_top_level_keys_not_extras(self):
        # AC4: a nested extras event must NOT match
        nested = [make_event("S1", top_level=False)]
        status, summary = project_campaign_status(CAMPAIGN_MD, make_committed(), nested, "demo-campaign")
        assert _by_id(status)["S1"]["status"] == "pending"
        assert summary["matched_events"] == 0

    def test_commit_empty_no_clobber(self):
        # AC4: worktree event commit="" must not erase a committed commit
        committed = make_committed(S1={"status": "complete", "commit": "realsha"})
        events = [make_event("S1", commit="")]
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, events, "demo-campaign")
        by_id = _by_id(status)
        assert by_id["S1"]["commit"] == "realsha"
        assert by_id["S1"]["status"] == "complete"

    def test_nonempty_event_commit_carried(self):
        events = [make_event("S1", commit="newsha", passed=42, total=43)]
        status, _ = project_campaign_status(CAMPAIGN_MD, make_committed(), events, "demo-campaign")
        by_id = _by_id(status)
        assert by_id["S1"]["commit"] == "newsha"
        assert by_id["S1"]["tests_passed"] == 42
        assert by_id["S1"]["tests_total"] == 43

    def test_tests_null_no_clobber(self):
        committed = make_committed(S1={"status": "complete", "tests_passed": 99, "tests_total": 100})
        events = [json.dumps({"type": "work_completed", "campaign": "demo-campaign",
                              "sub_iterate_id": "S1", "ts": "2026-06-10T08:00:00+00:00",
                              "commit": "z"})]  # no tests block
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, events, "demo-campaign")
        by_id = _by_id(status)
        assert by_id["S1"]["tests_passed"] == 99
        assert by_id["S1"]["tests_total"] == 100

    def test_latest_ts_wins(self):
        events = [
            make_event("S1", commit="old", ts="2026-06-10T07:00:00+00:00", passed=1, total=1),
            make_event("S1", commit="new", ts="2026-06-10T09:00:00+00:00", passed=2, total=2),
        ]
        status, _ = project_campaign_status(CAMPAIGN_MD, make_committed(), events, "demo-campaign")
        by_id = _by_id(status)
        assert by_id["S1"]["commit"] == "new"
        assert by_id["S1"]["tests_passed"] == 2

    def test_missing_ts_file_order_fallback(self):
        # neither has ts -> later file line wins (deterministic)
        events = [
            json.dumps({"type": "work_completed", "campaign": "demo-campaign",
                        "sub_iterate_id": "S1", "commit": "first"}),
            json.dumps({"type": "work_completed", "campaign": "demo-campaign",
                        "sub_iterate_id": "S1", "commit": "second"}),
        ]
        status, _ = project_campaign_status(CAMPAIGN_MD, make_committed(), events, "demo-campaign")
        assert _by_id(status)["S1"]["commit"] == "second"

    def test_skeleton_drives_order(self):
        # committed in REVERSE order -> output follows skeleton (S1,S2,S3)
        committed = make_committed()
        committed["sub_iterates"] = list(reversed(committed["sub_iterates"]))
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, [], "demo-campaign")
        assert [s["id"] for s in status["sub_iterates"]] == ["S1", "S2", "S3"]

    def test_drops_non_skeleton_committed_subs(self):
        committed = make_committed()
        committed["sub_iterates"].append({"id": "S9", "slug": "ghost", "status": "complete"})
        status, summary = project_campaign_status(CAMPAIGN_MD, committed, [], "demo-campaign")
        assert [s["id"] for s in status["sub_iterates"]] == ["S1", "S2", "S3"]
        assert "S9" in summary["dropped_subs"]

    def test_lifecycle_all_complete_overrides_prior_failed(self):
        # OpenAI #5: prior top-level failed, all subs complete -> complete
        committed = make_committed()
        committed["status"] = "failed"
        events = [make_event("S1"), make_event("S2"), make_event("S3")]
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, events, "demo-campaign")
        assert status["status"] == "complete"

    def test_lifecycle_partial_preserves_prior(self):
        committed = make_committed()
        committed["status"] = "active"
        events = [make_event("S1")]
        status, _ = project_campaign_status(CAMPAIGN_MD, committed, events, "demo-campaign")
        assert status["status"] == "active"

    def test_corrupt_line_skipped_with_warning(self):
        events = ["not json {{{", "", make_event("S1")]
        status, summary = project_campaign_status(CAMPAIGN_MD, make_committed(), events, "demo-campaign")
        assert _by_id(status)["S1"]["status"] == "complete"
        assert any("corrupt" in w.lower() or "invalid" in w.lower() for w in summary["warnings"])

    def test_valid_json_non_object_line_counted_corrupt(self):
        # external-review L4: a parseable but non-dict line (e.g. 42, []) must
        # not silently vanish from the operability count.
        events = ["42", "[]", make_event("S1")]
        status, summary = project_campaign_status(CAMPAIGN_MD, make_committed(), events, "demo-campaign")
        assert _by_id(status)["S1"]["status"] == "complete"
        assert any("corrupt" in w.lower() for w in summary["warnings"])

    def test_top_level_fields_preserved(self):
        status, _ = project_campaign_status(CAMPAIGN_MD, make_committed(), [], "demo-campaign")
        assert status["campaign"] == "demo-campaign"
        assert status["branch_strategy"] == "stacked"
        assert status["expands_triage"] == "trg-deadbeef"
