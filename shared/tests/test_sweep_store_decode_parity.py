"""The three consumers the git-blob-vs-file decode asymmetry broke, end-to-end.

Companion to ``test_store_decode_parity.py``, which pins the seam itself. This module
drives the REAL entry points over a REAL git repo, because the sweep is the most
data-loss-sensitive unit in the campaign and ``_sweep_helpers`` mocks none of it.

Three consumers, three distinct symptoms — all reproduced against the pre-fix code
before this module was written (iterate-2026-08-06-gc-decode-parity):

* :func:`lib.sweep_gc.delivered_membership` — the delivered line is never recognised,
  so the GC never drops it and the gitignored outbox grows forever. This is the
  reported symptom, and it is reachable on the ``status``/unparseable TEXT-membership
  path with no canonical-form rule involved.
* :func:`lib.sweep_drift.plan_main_tracked_drift` — a working log BYTE-IDENTICAL to
  ``HEAD`` reads as ``main_tracked_diverged``, so the WHOLE sweep returns ``skipped``
  and nothing is delivered at all. Strictly worse than the GC symptom.
* :func:`lib.reconcile_triage.reconcile_main_triage` — the "already in HEAD" set
  misses the line, inflating the folded count in the commit subject.

Named ``test_sweep_*`` deliberately: that prefix is what ``conftest``'s autouse
``_sweep_tests_unset_ci`` keys on, so this module gets the ``$CI`` isolation the
sweep entry points require BOTH from that fixture and from the explicit ``delenv``
below. The explicit one is the contract; the name is defence in depth, because a
missing ``$CI`` unset here does not merely fail — it makes the anti-promiscuity probe
pass while asserting nothing (found in Stage-1 spec review).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.reconcile_triage import reconcile_main_triage  # noqa: E402
from lib.sweep_drift import plan_main_tracked_drift  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from lib.sweep_text import decode_store_text, normalize_lines  # noqa: E402

TRIAGE = h.TRIAGE
OUTBOX = h.OUTBOX


@pytest.fixture
def repo(git_origin_repo, monkeypatch):
    """A work/origin pair with ``$CI`` UNSET.

    ``sweep_outbox_to_branch`` and ``reconcile_main_triage`` both return
    ``skipped``/``ci_without_optin`` under ``$CI``, BEFORE they reach the decode seam.
    Asserted explicitly rather than inherited from the module name, so a future rename
    cannot silently turn these into vacuous passes. Same fix, same reason, as
    ``test_store_git_timeout_paths.py``.
    """
    monkeypatch.delenv("CI", raising=False)
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


class TestGcDeliversABrokenLine:
    """AC-3 — the reported symptom, end-to-end through the real sweep."""

    def test_a_delivered_status_line_with_a_broken_byte_is_gc_d(self, repo) -> None:
        work, _ = repo
        broken_status = h.broken(h.spliceable_status("trg-broken1"))

        # The line is DELIVERED: committed to the tracked log and pushed to origin.
        h.seed_tracked(work, h.item("trg-broken1"), broken_status)
        wt = h.make_worktree(work, "gc-broken")
        # ...and still sitting in the gitignored buffer, awaiting GC.
        h.write_outbox(work, broken_status)

        assert broken_status.strip() in h.outbox_lines(work)

        result = sweep_outbox_to_branch(work, wt, default_branch="main")

        assert result.status in {"committed", "no_change"}, result.to_dict()
        assert result.gc_dropped >= 1, (
            f"delivered line was not GC'd: {result.to_dict()}")
        assert broken_status.strip() not in h.outbox_lines(work)

    def test_an_undelivered_line_still_survives(self, repo) -> None:
        """The fail-safe must not be traded away: parity makes matches POSSIBLE, it
        must not make them promiscuous. A broken line that is NOT in origin stays.

        This is the probe that fails if parity were ever bought with a LOSSY
        comparison — the failure mode that would silently delete an operator's
        finding, which is strictly worse than the bug being fixed.

        The pair is built to COLLIDE under ``errors="replace"``: same line, same
        splice offset, DIFFERENT invalid byte. Both render as one ``U+FFFD``, so a
        non-injective rule judges `other` delivered on the strength of `delivered`
        and drops it. Varying the byte's *position* instead would NOT collide, and
        this test would pass against a lossy rule while claiming otherwise
        (found in Stage-2 code review).
        """
        work, _ = repo
        delivered = h.broken(h.spliceable_status("trg-broken2"))
        other = h.broken(h.spliceable_status("trg-broken2"), bad=h.OTHER_BAD_BYTE)
        assert delivered != other
        assert (delivered.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
                == other.encode("utf-8", "surrogateescape").decode("utf-8", "replace")), (
            "the pair must be indistinguishable under a LOSSY decode, or this test "
            "cannot detect a non-injective membership rule")

        h.seed_tracked(work, h.item("trg-broken2"), delivered)
        wt = h.make_worktree(work, "gc-survive")
        h.write_outbox(work, delivered, other)

        result = sweep_outbox_to_branch(work, wt, default_branch="main")

        # The survival claim is only worth anything if the GC actually RAN. Without
        # these two the test passes when the sweep no-ops (`ci_without_optin`) — a
        # false green on the one probe guarding against data loss.
        assert result.status != "skipped", f"sweep never ran: {result.reason}"
        assert result.gc_dropped >= 1, f"GC never fired: {result.to_dict()}"

        assert other.strip() in h.outbox_lines(work), (
            "an UNDELIVERED line was dropped — parity must not become a lossy match")


class TestBoundaryProbeRoundTrip:
    """Boundary Probe for ``touches_io_boundary`` — the WHOLE trip, not one hop.

    bytes on disk -> git blob -> decode -> membership compare -> survivor re-encode ->
    bytes on disk. Every hop must be byte-preserving, or a line that merely SURVIVES
    the GC still comes back corrupted, which would be worse than the bug being fixed.
    """

    def test_a_surviving_broken_line_is_byte_identical_after_the_sweep(self, repo) -> None:
        work, _ = repo
        delivered = h.broken(h.spliceable_status("trg-probe1"))
        survivor_bytes = h.broken_bytes(h.spliceable_status("trg-probe2"))
        survivor = h.broken(h.spliceable_status("trg-probe2"))

        # One delivered line (so the survivor REWRITE actually fires) + one that is not.
        h.seed_tracked(work, h.item("trg-probe1"), h.item("trg-probe2"), delivered)
        wt = h.make_worktree(work, "probe-roundtrip")
        h.write_outbox(work, delivered, survivor)

        assert survivor_bytes in (work / OUTBOX).read_bytes()

        result = sweep_outbox_to_branch(work, wt, default_branch="main")
        assert result.gc_dropped >= 1, f"rewrite never fired: {result.to_dict()}"

        after = (work / OUTBOX).read_bytes()
        assert survivor_bytes in after, (
            "the surviving line's bytes changed across the round trip — the 0xFF was "
            f"not preserved: {after!r}")


class TestDriftPlanStopsFalseRefusing:
    """AC-4 — the site the original finding did not name, and the severe one."""

    def test_an_unchanged_log_with_a_broken_byte_is_not_diverged(self, repo) -> None:
        work, _ = repo
        h.seed_tracked(work, h.broken(h.item("trg-broken3", title="caf")))

        # The working tree is byte-identical to HEAD. Nothing has drifted.
        head = subprocess.run(
            ["git", "-C", str(work), "show", f"HEAD:{TRIAGE}"],
            check=True, capture_output=True).stdout
        assert (work / TRIAGE).read_bytes() == head

        plan = plan_main_tracked_drift(work, work / OUTBOX)

        assert plan.status == "no_drift", (
            f"an UNCHANGED log was reported as {plan.status}: {plan.reason}")

    def test_adopting_drift_over_a_broken_head_moves_it_without_loss(self, repo) -> None:
        """The irreversible path this fix newly UNBLOCKS, driven end-to-end.

        Pre-fix, a broken byte in HEAD made the plan ``refused`` and the sweep
        ``skipped`` — a total no-op. Post-fix the same store reaches
        ``commit_main_tracked_drift``, which rewrites the GITIGNORED outbox and then
        runs ``git checkout -- <triage>`` against MAIN's working tree, discarding the
        uncommitted content. That is a relocation from a tracked file into one
        ``git clean -x`` deletes, so it must be proven lossless rather than assumed
        (Stage-3 doubt review: the only irreversible path the change unblocks was
        also the only one no test drove).
        """
        work, _ = repo
        h.seed_tracked(work, h.broken(h.item("trg-broken6", title="caf")))
        head_bytes = subprocess.run(
            ["git", "-C", str(work), "show", f"HEAD:{TRIAGE}"],
            check=True, capture_output=True).stdout

        drift = h.item("trg-drift6")
        with (work / TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(drift + "\n")

        wt = h.make_worktree(work, "drift-adopt")
        result = sweep_outbox_to_branch(work, wt, default_branch="main")

        assert result.status in {"committed", "no_change"}, result.to_dict()
        assert result.adopted == 1, f"drift was not adopted: {result.to_dict()}"
        # The operator's line survived the relocation...
        assert drift in h.branch_triage_lines(wt) or drift in h.outbox_lines(work), (
            "the adopted drift reached NEITHER the branch nor the buffer — "
            f"{result.to_dict()}")
        # ...and main's tracked log is back to HEAD. Compared line-wise, not byte-wise:
        # ``git checkout --`` runs the smudge filter, so under `core.autocrlf=true` the
        # restored file is legitimately CRLF where the blob is LF. What must hold is
        # that no CONTENT changed and the invalid byte survived the restore untouched.
        restored = (work / TRIAGE).read_bytes()
        assert (normalize_lines(decode_store_text(restored))[0]
                == normalize_lines(decode_store_text(head_bytes))[0])
        assert h.BAD_BYTE in restored, "the restore mangled the invalid byte"
        assert drift not in decode_store_text(restored), "drift was copied, not moved"

    def test_real_drift_is_still_detected_over_a_broken_head(self, repo) -> None:
        """Parity must not blind the detector — a genuine append is still drift."""
        work, _ = repo
        h.seed_tracked(work, h.broken(h.item("trg-broken4", title="caf")))

        with (work / TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(h.item("trg-fresh4") + "\n")

        plan = plan_main_tracked_drift(work, work / OUTBOX)

        assert plan.status == "adoptable", f"{plan.status}: {plan.reason}"
        assert len(plan.fresh) == 1


class TestReconcileFoldCount:
    """AC-5 — the third site: an inflated count in the commit subject."""

    def test_a_broken_head_line_is_not_counted_as_newly_folded(self, repo) -> None:
        work, _ = repo
        h.seed_tracked(work, h.broken(h.item("trg-broken5", title="caf")))

        # Exactly ONE genuinely-new line on top of the committed (broken) one.
        with (work / TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(h.item("trg-fresh5") + "\n")

        result = reconcile_main_triage(work)

        assert result.status == "committed", f"{result.status}: {result.reason}"
        assert result.folded == 1, (
            f"folded={result.folded} — the committed broken line was miscounted as "
            f"new (subject would read {result.commit_subject!r})")
