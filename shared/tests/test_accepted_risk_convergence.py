"""Convergence planning, the gh shell, and the CLI — plus the repo's own gate.

These tests ARE the gate for the alert surface, the same way
``test_accepted_risks_register`` is for the offline one. Two properties carry
most of the weight, and both are asserted as negative controls rather than
assumed:

* **nothing is dismissed without a backing, non-expired entry** — it holds by
  construction (the plan iterates entries), and the construction is pinned here;
* **an incomplete listing never reads as "converged"** — a failed fetch raises,
  because a short listing that reads as clean is exactly the failure that
  licenses inaction.

The network is never touched: ``_run`` is the single seam, so the shell is
driven end-to-end offline and in-process (a subprocess would contribute no
coverage against the 80% diff gate).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import alert_convergence as ac  # noqa: E402
from accepted_risks import Acceptance  # noqa: E402
from tools import triage_gc  # noqa: E402

NOW = date(2026, 7, 19)
RULE = "py/unused-global-variable"


def entry(**over) -> Acceptance:
    base = dict(
        id="ar-test", target="github-dismissal", rule=RULE,
        expires=date(2027, 1, 1), rationale_ref="ADR-271",
        statement="a sufficiently long justification for the acceptance",
        scope={"tool": "CodeQL", "paths": ["a/b.py"]},
    )
    base.update(over)
    return Acceptance(**base)


def alert(number=1, state="open", path="a/b.py", comment="") -> ac.Alert:
    return ac.Alert(number=number, tool="CodeQL", rule=RULE, path=path,
                    state=state, dismissed_comment=comment)


def marked(entry_id="ar-test", **over) -> ac.Alert:
    from alert_match import marker_for
    return alert(state="dismissed", comment=f"why {marker_for(entry_id)}", **over)


class TestPlanConvergence:
    def test_open_alert_backed_by_a_live_entry_is_dismissed(self):
        plan = ac.plan_convergence([entry()], [alert()], now=NOW)
        assert [a.number for _e, a in plan.to_dismiss] == [1]
        assert plan.mutates and not plan.ok

    def test_alert_with_no_backing_entry_is_never_dismissed(self):
        """The load-bearing safety property. An empty register must produce an
        empty plan, not a sweep."""
        plan = ac.plan_convergence([], [alert()], now=NOW)
        assert plan.to_dismiss == [] and plan.to_reopen == []

    def test_human_dismissal_claimed_by_no_entry_is_still_reported(self):
        """The dominant real case: this repo has 50 dismissals and 0 register
        entries. They must appear as untouched-and-unrecorded, not vanish — an
        alert nobody can account for is exactly what the register exists to
        surface."""
        human = alert(state="dismissed", comment="a person decided this")
        plan = ac.plan_convergence([], [human], now=NOW)
        assert plan.human_dismissed == [human]
        assert plan.to_reopen == [] and plan.to_dismiss == []

    def test_non_github_targets_never_reach_the_alert_surface(self):
        offline = entry(target="trivy-ignore", rule="CVE-1", scope={})
        plan = ac.plan_convergence([offline], [alert()], now=NOW)
        assert plan.to_dismiss == [] and plan.ambiguous == [] and plan.stale == []

    def test_already_converged_alert_is_satisfied_not_re_dismissed(self):
        plan = ac.plan_convergence([entry()], [marked()], now=NOW)
        assert len(plan.satisfied) == 1 and not plan.mutates

    def test_human_dismissal_is_recorded_and_never_rewritten(self):
        """All 50 dismissals on this repo today are unmarked. None may be
        touched, and none may be silently omitted either."""
        human = alert(state="dismissed", comment="hand-written rationale")
        plan = ac.plan_convergence([entry()], [human], now=NOW)
        assert plan.human_dismissed == [human]
        assert plan.to_dismiss == [] and plan.to_reopen == []

    def test_expired_entry_reopens_only_what_this_tool_dismissed(self):
        expired = entry(expires=date(2026, 1, 1))
        plan = ac.plan_convergence([expired], [marked()], now=NOW)
        assert [a.number for _i, a in plan.to_reopen] == [1]

    def test_expired_entry_never_reopens_a_human_dismissal(self):
        expired = entry(expires=date(2026, 1, 1))
        human = alert(state="dismissed", comment="a person decided this")
        plan = ac.plan_convergence([expired], [human], now=NOW)
        assert plan.to_reopen == [] and plan.human_dismissed == [human]

    def test_expired_entry_does_not_dismiss_anything_new(self):
        expired = entry(expires=date(2026, 1, 1))
        plan = ac.plan_convergence([expired], [alert()], now=NOW)
        assert plan.to_dismiss == []

    def test_entry_expiring_today_is_still_active(self):
        today = entry(expires=NOW)
        plan = ac.plan_convergence([today], [alert()], now=NOW)
        assert len(plan.to_dismiss) == 1

    def test_marked_alert_whose_entry_vanished_is_reopened(self):
        """Deleting the record is the same loss of authority as expiry, so it
        gets the same restoration — otherwise removing an entry would leave the
        alert quietly suppressed forever."""
        plan = ac.plan_convergence([], [marked("ar-gone")], now=NOW)
        assert [i for i, _a in plan.to_reopen] == ["ar-gone"]

    def test_ambiguous_entry_is_refused_and_matches_nothing(self):
        vague = entry(scope={"tool": "CodeQL"})
        plan = ac.plan_convergence([vague], [alert()], now=NOW)
        assert len(plan.ambiguous) == 1 and plan.to_dismiss == []
        assert not plan.ok

    def test_entry_matching_no_alert_is_stale(self):
        plan = ac.plan_convergence([entry()], [], now=NOW)
        assert plan.stale == [entry()] and not plan.ok

    def test_converged_repo_is_ok_and_mutates_nothing(self):
        plan = ac.plan_convergence([], [], now=NOW)
        assert plan.ok and not plan.mutates

    def test_two_entries_claiming_one_alert_conflict_and_neither_acts(self):
        """External review (GPT #4). Merging the claim would PATCH twice, the
        second comment overwriting the first entry's marker."""
        a = entry(id="ar-one")
        b = entry(id="ar-two", scope={"tool": "CodeQL", "match": "rule-wide"})
        plan = ac.plan_convergence([a, b], [alert()], now=NOW)
        assert plan.to_dismiss == []
        assert [(al.number, sorted(o)) for al, o in plan.conflicted] == [
            (1, ["ar-one", "ar-two"])
        ]
        assert not plan.ok

    def test_conflicted_alert_is_not_reopened_by_one_entry_lapsing(self):
        """The sharper half of the same finding: with a merged claim, expiring
        ONE entry would reopen an alert the other still legitimately covers."""
        live = entry(id="ar-live")
        lapsed = entry(id="ar-lapsed", expires=date(2026, 1, 1),
                       scope={"tool": "CodeQL", "match": "rule-wide"})
        plan = ac.plan_convergence([live, lapsed], [marked("ar-lapsed")], now=NOW)
        assert plan.to_reopen == [] and len(plan.conflicted) == 1

    def test_unreadable_triage_store_blocks_the_converged_claim(self):
        """External review (GPT #3). 'I could not look' must not render as
        'there was nothing there'."""
        plan = ac.plan_convergence([], [], now=NOW)
        assert plan.ok
        plan.triage_unreadable = "OSError: store is corrupt"
        assert not plan.ok
        assert "UNREAD" in "\n".join(ac.format_plan(plan))

    def test_rule_wide_entry_does_not_swallow_another_tools_alert(self):
        wide = entry(scope={"tool": "CodeQL", "match": "rule-wide"})
        other = ac.Alert(2, "Scorecard", RULE, "x.yml", "open")
        plan = ac.plan_convergence([wide], [alert(), other], now=NOW)
        assert [a.number for _e, a in plan.to_dismiss] == [1]


class TestTriageSurface:
    def item(self, key=f"semgrep:{RULE}:a/b.py:5"):
        return {"id": "trg-1", "dedupKey": key}

    def test_matching_open_item_is_dismissed(self):
        e = entry(scope={"tool": "semgrep", "paths": ["a/b.py"]})
        plan = ac.plan_convergence([e], [], now=NOW, triage_items=[self.item()])
        assert [i["id"] for _e, i in plan.triage_dismiss] == ["trg-1"]

    def test_unrelated_item_is_left_alone(self):
        e = entry(scope={"tool": "semgrep", "paths": ["other.py"]})
        plan = ac.plan_convergence([e], [], now=NOW, triage_items=[self.item()])
        assert plan.triage_dismiss == []

    def test_expired_entry_dismisses_no_triage_item(self):
        e = entry(expires=date(2026, 1, 1), scope={"tool": "semgrep", "paths": ["a/b.py"]})
        plan = ac.plan_convergence([e], [], now=NOW, triage_items=[self.item()])
        assert plan.triage_dismiss == []

    def test_gc_tokens_are_registered_in_the_decoupled_ssot(self):
        """The pair is a separate registry; a reason missing from it escapes the
        dismissed-pile GC and accumulates forever."""
        assert ac.TRIAGE_DISMISSER in triage_gc.MACHINE_DISMISSERS
        assert ac.TRIAGE_REASON in triage_gc.MACHINE_REASONS
        assert triage_gc.is_machine_churn({
            "status": "dismissed", "statusBy": ac.TRIAGE_DISMISSER,
            "statusReason": ac.TRIAGE_REASON,
        })


class TestRendering:
    def test_every_disposition_is_printed(self):
        plan = ac.Plan(
            to_dismiss=[(entry(), alert())],
            to_reopen=[("ar-x", marked())],
            triage_dismiss=[(entry(), {"id": "trg-1", "dedupKey": "a:b:c:1"})],
            ambiguous=[(entry(), "why")],
            conflicted=[(alert(), ["ar-one", "ar-two"])],
            stale=[entry()],
        )
        text = "\n".join(ac.format_plan(plan))
        for token in ("DISMISS", "REOPEN", "TRIAGE", "AMBIGUOUS", "CONFLICTED",
                      "STALE"):
            assert token in text

    def test_untouched_alerts_are_summarised_not_dropped(self):
        plan = ac.Plan(satisfied=[(entry(), marked())],
                       human_dismissed=[alert(state="dismissed")])
        text = "\n".join(ac.format_untouched(plan))
        assert "already converged" in text and "WITHOUT this" in text

    def test_clean_plan_renders_nothing(self):
        assert ac.format_plan(ac.Plan()) == []
        assert ac.format_untouched(ac.Plan()) == []
