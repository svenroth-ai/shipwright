"""`lib.main_health_diagnosis` — the failure excerpt, and the claim.

@FR-01.19

Two independent concerns that share the red path.

**The excerpt is untrusted input.** It is text a failing test printed, packaged
for an agent to read. It is reduced to the assertion-bearing lines, capped,
passed through a conservative secret redactor, and labelled — the label matters
as much as the redaction, because it is what stops a log line from being read as
an instruction.

**The claim is a lock, and a lock that cannot be forged.** A pull request from a
fork carrying the right branch name must not be able to suppress the repair
loop; and a claim whose worker died must not wedge it forever.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import main_health_diagnosis as dx  # noqa: E402

OWNER, NAME = "svenroth-ai", "shipwright"
SHA = "3ed41047c2f4d137cf9ce6446db47bc89816b29f"
SHA12 = SHA[:12]


# --------------------------------------------------------------------------
# log reduction
# --------------------------------------------------------------------------

LOG = """\
Python (lint + test)\tRun shared tests\t2026-07-28T10:00:01Z ============ test session starts ============
Python (lint + test)\tRun shared tests\t2026-07-28T10:00:02Z collected 3441 items
Python (lint + test)\tRun shared tests\t2026-07-28T10:00:40Z FAILED shared/tests/test_x.py::test_five_entries
Python (lint + test)\tRun shared tests\t2026-07-28T10:00:40Z E       assert 6 == 5
Python (lint + test)\tRun shared tests\t2026-07-28T10:00:41Z ==== short test summary info ====
"""


def test_reduction_keeps_the_assertion_lines_and_drops_the_setup_noise():
    out = dx.reduce_failure_log(LOG)
    body = "\n".join(out["excerpt"])
    assert "FAILED shared/tests/test_x.py::test_five_entries" in body
    assert "assert 6 == 5" in body
    assert "collected 3441 items" not in body


def test_the_excerpt_is_always_labelled_untrusted():
    assert dx.reduce_failure_log(LOG)["untrusted"] is True
    assert dx.reduce_failure_log("")["untrusted"] is True


def test_the_cap_is_honoured_and_reported():
    many = "\n".join(f"job\tstep\t2026 E   assert {i} == 0" for i in range(200))
    out = dx.reduce_failure_log(many, max_lines=10)
    assert len(out["excerpt"]) == 10
    assert out["truncated"] is True


def test_a_short_excerpt_is_not_marked_truncated():
    assert dx.reduce_failure_log(LOG)["truncated"] is False


def test_a_byte_cap_also_truncates():
    long_line = "job\tstep\t2026 E   assert " + ("x" * 5000)
    out = dx.reduce_failure_log(long_line, max_bytes=200)
    assert out["truncated"] is True
    assert len("\n".join(out["excerpt"]).encode()) <= 200


def test_no_log_at_all_is_an_explicit_absence_not_an_empty_pass():
    out = dx.reduce_failure_log(None)
    assert out["excerpt"] is None
    assert out["reason_code"] == "log_unavailable"


# --------------------------------------------------------------------------
# redaction — defense in depth, never advertised as complete
# --------------------------------------------------------------------------

def test_each_known_secret_shape_is_redacted():
    samples = [
        "ghp_" + "A" * 36,
        "github_pat_" + "B" * 30,
        "sk-" + "C" * 32,
        "AKIA" + "D" * 16,
        "xoxb-" + "1" * 20,
        "Authorization: Bearer " + "E" * 40,
    ]
    for s in samples:
        assert dx.redact(s) != s, f"not redacted: {s[:12]}"
        assert dx.REDACTED in dx.redact(s)


def test_redaction_leaves_ordinary_diagnostic_text_alone():
    line = "assert 6 == 5  # shared/tests/test_x.py:41 in test_five_entries"
    assert dx.redact(line) == line


def test_a_commit_sha_is_not_mistaken_for_a_secret():
    """40 hex characters is the shape of every SHA in this payload. Redacting
    those would blank the one identifier the repair needs."""
    assert dx.redact(SHA) == SHA


# --------------------------------------------------------------------------
# the claim
# --------------------------------------------------------------------------

def _pr(*, state="OPEN", branch=f"iterate/fix-main-{SHA12}", fork=False,
        author="svroch", updated="2026-07-28T10:00:00Z", number=1):
    return {
        "number": number,
        "url": f"https://github.com/{OWNER}/{NAME}/pull/{number}",
        "state": state,
        "headRefName": branch,
        "headRepositoryOwner": {"login": "someone-else" if fork else OWNER},
        "author": {"login": author},
        "updatedAt": updated,
        "createdAt": updated,
    }


NOW = "2026-07-28T10:30:00Z"


def test_the_branch_name_is_the_claim():
    out = dx.match_repair_claim(SHA, prs=[_pr()], refs=[], repo_owner=OWNER, now=NOW)
    assert out["claim"]["number"] == 1
    assert out["claim"]["stale"] is False


def test_a_fork_cannot_claim():
    """Write access is the trust boundary. Anyone can name a branch; only
    someone with push rights can create one in this repository."""
    out = dx.match_repair_claim(SHA, prs=[_pr(fork=True)], refs=[], repo_owner=OWNER, now=NOW)
    assert out["claim"] is None


def test_a_branch_naming_a_different_commit_is_not_this_claim():
    other = _pr(branch="iterate/fix-main-" + "9" * 12)
    out = dx.match_repair_claim(SHA, prs=[other], refs=[], repo_owner=OWNER, now=NOW)
    assert out["claim"] is None


def test_a_short_sha_must_be_a_real_prefix_of_the_attributed_commit():
    almost = _pr(branch=f"iterate/fix-main-{SHA[:11]}f")
    out = dx.match_repair_claim(SHA, prs=[almost], refs=[], repo_owner=OWNER, now=NOW)
    assert out["claim"] is None


def test_a_pushed_branch_with_no_pr_yet_is_already_a_claim():
    """The atomic claim is pushing the branch, not opening the PR — two agents
    that both query before either PR exists would otherwise both proceed."""
    out = dx.match_repair_claim(
        SHA, prs=[], refs=[f"refs/heads/iterate/fix-main-{SHA12}"],
        repo_owner=OWNER, now=NOW,
    )
    assert out["claim"] is not None
    assert out["claim"]["source"] == "branch"
    # A refs listing carries no timestamp, so age is UNKNOWN — saying False
    # asserted "a live worker holds this" about a ref that may have been
    # abandoned before its PR existed (external code review, round 2).
    assert out["claim"]["stale"] is None
    assert "unknown" in out["claim"]["stale_reason"]


def test_a_branch_left_over_by_a_closed_repair_is_NO_claim_at_all():
    """Otherwise one abandoned ref wedges that commit forever. Reporting it as a
    `stale` claim was not enough either: the caller's stale path begins by
    commenting on the pull request — which, for litter, does not exist (Tier-3
    review). No claim is the honest answer; the history stays in
    `failed_attempts`."""
    closed = _pr(state="CLOSED", number=4, updated="2026-07-27T10:00:00Z")
    out = dx.match_repair_claim(
        SHA, prs=[closed], refs=[f"refs/heads/iterate/fix-main-{SHA12}"],
        repo_owner=OWNER, now=NOW,
    )
    assert out["claim"] is None
    assert out["failed_attempts"] == 1


def test_a_claim_untouched_past_the_threshold_is_stale_and_takeable():
    old = _pr(updated="2026-07-28T06:00:00Z")
    out = dx.match_repair_claim(SHA, prs=[old], refs=[], repo_owner=OWNER,
                                now=NOW, stale_minutes=120)
    assert out["claim"]["stale"] is True


def test_closed_unmerged_attempts_are_counted_so_repeat_escalation_is_a_fact():
    prs = [
        _pr(state="CLOSED", number=1, updated="2026-07-27T10:00:00Z"),
        _pr(state="CLOSED", number=2, updated="2026-07-27T12:00:00Z"),
    ]
    out = dx.match_repair_claim(SHA, prs=prs, refs=[], repo_owner=OWNER, now=NOW)
    assert out["claim"] is None
    assert out["failed_attempts"] == 2


def test_a_merged_attempt_is_not_a_failed_attempt():
    out = dx.match_repair_claim(SHA, prs=[_pr(state="MERGED")], refs=[],
                                repo_owner=OWNER, now=NOW)
    assert out["failed_attempts"] == 0


def test_trusted_author_narrowing_is_opt_in_and_rejects_others():
    out = dx.match_repair_claim(SHA, prs=[_pr(author="drive-by")], refs=[],
                                repo_owner=OWNER, now=NOW,
                                trusted_authors=["svroch"])
    assert out["claim"] is None


# --------------------------------------------------------------------------
# escalation
# --------------------------------------------------------------------------

def test_a_finding_class_red_escalates_with_an_idempotent_key():
    out = dx.escalation(bad_sha=SHA, finding_reds=["Security Scan"],
                        partner_count=1, failed_attempts=0)
    assert out["required"] is True
    assert "finding_class_red" in out["reasons"]
    assert out["keys"] == [f"main-red:Security Scan:{SHA12}"]


def test_too_many_implicated_commits_escalates():
    out = dx.escalation(bad_sha=SHA, finding_reds=[], partner_count=99,
                        failed_attempts=0)
    assert "too_many_commits" in out["reasons"]


def test_two_failed_attempts_escalate():
    out = dx.escalation(bad_sha=SHA, finding_reds=[], partner_count=1,
                        failed_attempts=2)
    assert "repeat_attempts" in out["reasons"]


def test_an_ordinary_overlap_does_not_escalate():
    out = dx.escalation(bad_sha=SHA, finding_reds=[], partner_count=2,
                        failed_attempts=0)
    assert out["required"] is False
    assert out["reasons"] == []
