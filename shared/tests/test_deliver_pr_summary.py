"""The line the operator actually reads (iterate-2026-07-31-f11-delivery-truth).

Split out of ``test_deliver_pr_self_merge.py`` to keep both files under the 300-line
source limit. Its own subject: *delivered* must never read as "the host confirmed it"
when the host ran no checks, and no non-delivery may read as done.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.deliver_pr import summary  # noqa: E402


# --- the closing line ---------------------------------------------------------

def test_the_summary_names_who_merged_and_on_what_evidence():
    merged_here = {"status": "merged", "merged_by": "shipwright",
                   "checks_observed": 3, "checks_passed": 3}
    assert "merged by Shipwright itself" in summary(merged_here)
    assert "3 passing check(s)" in summary(merged_here)


def test_the_summary_counts_passes_not_rollup_entries():
    """SKIPPED and NEUTRAL count as passes for the merge DECISION (a needs:-skipped
    required job is a pass) but they are not EVIDENCE. Reporting entries let an
    all-skipped rollup say "the host ran 3 check(s)" when the host confirmed nothing —
    the exact sentence FR-01.11's criterion exists to make impossible (Stage 3)."""
    all_skipped = {"status": "merged", "merged_by": "shipwright",
                   "checks_observed": 3, "checks_passed": 0}
    line = summary(all_skipped)
    assert "confirmed NOTHING" in line
    assert "3" not in line, line


def test_a_zero_check_delivery_says_so_loudly():
    """Case C: an unprotected repo often runs no PR checks at all. Merging there is
    correct, but it must never read as "the host confirmed it"."""
    line = summary({"status": "merged", "merged_by": "shipwright",
                    "checks_observed": 0, "checks_passed": 0})
    assert "confirmed NOTHING" in line
    assert "local test suite" in line


def test_the_host_merged_summary_does_not_claim_shipwright_did():
    line = summary({"status": "merged", "merged_by": "host"})
    assert "Shipwright itself" not in line


def test_the_no_merger_summary_tells_the_operator_both_ways_out():
    line = summary({"status": "no_merger", "reason": "the base branch has no protection"})
    assert "Merge it yourself" in line
    assert "SHIPWRIGHT_ITERATE_SELF_MERGE=1" in line


def test_no_summary_ever_claims_done_on_a_pending_verdict():
    for status in ("pending", "checks_failed", "closed", "refused", "host_error"):
        line = summary({"status": status, "reason": "x"})
        assert line.startswith("NOT DELIVERED"), status
