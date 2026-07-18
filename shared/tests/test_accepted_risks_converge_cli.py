"""The ``converge`` command end-to-end, offline — and this repo's own gate.

The gh seam is monkeypatched, so the command is driven through its real entry
point (``cli.main([...])``, in-process) without a network. The last class is the
binding part: it runs against the REAL register in this repo, so a
``github-dismissal`` entry that could not be resolved unambiguously fails CI
here rather than being discovered the first time somebody runs ``--apply``.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import alert_convergence as ac  # noqa: E402
import alert_match as am  # noqa: E402
import github_code_scanning as gcs  # noqa: E402
from accepted_risks import load_register  # noqa: E402
from tools import accepted_risks_cli as cli  # noqa: E402
from tools import accepted_risks_converge as arc  # noqa: E402

RULE = "py/unused-global-variable"

REGISTER = """\
schema: 1
acceptances:
  - id: ar-live
    target: github-dismissal
    rule: {rule}
    scope:
      tool: CodeQL
      paths: ["a/b.py"]
    expires: {expires}
    rationale_ref: ADR-271
    statement: >-
      a sufficiently long justification for accepting this finding
"""


def repo(tmp_path: Path, *, expires="2027-01-01") -> Path:
    (tmp_path / "shipwright_accepted_risks.yaml").write_text(
        REGISTER.format(rule=RULE, expires=expires), encoding="utf-8"
    )
    return tmp_path


def api_alert(number=1, state="open", path="a/b.py", comment=None) -> dict:
    return {
        "number": number, "state": state, "dismissed_comment": comment,
        "tool": {"name": "CodeQL"}, "rule": {"id": RULE},
        "most_recent_instance": {"location": {"path": path}},
    }


@pytest.fixture
def gh(monkeypatch):
    """A fake GitHub: alerts by state, plus a record of every mutation."""
    state = {"open": [], "dismissed": [], "calls": []}
    monkeypatch.setattr(arc.github_api, "owner_repo", lambda root: "svenroth-ai/shipwright")
    monkeypatch.setattr(gcs, "list_alerts", lambda slug, st: state[st])
    monkeypatch.setattr(gcs, "dismiss_alert", lambda slug, n, *, reason, comment: (
        state["calls"].append(("dismiss", n, reason, comment)), (True, "ok"))[1])
    monkeypatch.setattr(gcs, "reopen_alert", lambda slug, n: (
        state["calls"].append(("reopen", n)), (True, "ok"))[1])
    return state


class TestBuildPlan:
    def test_reads_both_states_and_plans(self, tmp_path, gh):
        gh["open"] = [api_alert()]
        slug, plan = arc.build_plan(repo(tmp_path), now=date(2026, 7, 19))
        assert slug == "svenroth-ai/shipwright"
        assert [a.number for _e, a in plan.to_dismiss] == [1]

    def test_unresolvable_repo_identity_aborts(self, tmp_path, monkeypatch):
        """Refuse rather than fall back to gh's cwd-derived placeholders — the
        register that authorises a mutation must be the checked-out repo's."""
        monkeypatch.setattr(arc.github_api, "owner_repo", lambda root: None)
        with pytest.raises(gcs.RepoIdentityError):
            arc.build_plan(repo(tmp_path))

    def test_failed_listing_aborts_instead_of_reading_as_converged(
        self, tmp_path, monkeypatch, gh
    ):
        """The specific lie this must not tell: an incomplete listing that
        renders as 'nothing left to converge'."""
        monkeypatch.setattr(gcs, "list_alerts", lambda slug, st: None)
        with pytest.raises(gcs.RepoIdentityError, match="incomplete listing"):
            arc.build_plan(repo(tmp_path))

    def test_unkeyable_alerts_are_dropped_not_guessed(self, tmp_path, gh):
        gh["open"] = [api_alert(), {"number": 2, "tool": {}}]
        _slug, plan = arc.build_plan(repo(tmp_path), now=date(2026, 7, 19))
        assert [a.number for _e, a in plan.to_dismiss] == [1]


class TestCmdConverge:
    def test_absent_register_still_reopens_what_this_tool_dismissed(
        self, tmp_path, gh, capsys
    ):
        """External review (GPT #2). Deleting the register is the same loss of
        authority as expiry. An early return would leave marked alerts
        suppressed forever, with nothing left in the repo to explain why."""
        gh["dismissed"] = [api_alert(state="dismissed",
                                     comment=f"x {am.marker_for('ar-gone')}")]
        assert arc.cmd_converge(tmp_path, apply=True) == 0
        assert "no register" in capsys.readouterr().out
        assert gh["calls"] == [("reopen", 1)]

    def test_absent_register_with_nothing_marked_is_clean(self, tmp_path, gh, capsys):
        assert arc.cmd_converge(tmp_path) == 0
        assert gh["calls"] == []

    def test_converged_repo_exits_zero(self, tmp_path, gh, capsys):
        gh["dismissed"] = [api_alert(state="dismissed",
                                     comment=f"x {am.marker_for('ar-live')}")]
        assert arc.cmd_converge(repo(tmp_path)) == 0
        out = capsys.readouterr().out
        assert "converged" in out and "already converged" in out

    def test_divergence_is_reported_read_only_by_default(self, tmp_path, gh, capsys):
        gh["open"] = [api_alert()]
        assert arc.cmd_converge(repo(tmp_path)) == 1
        out = capsys.readouterr().out
        assert "DISMISS" in out and "Read-only" in out
        assert gh["calls"] == [], "read-only mode must not mutate anything"

    def test_apply_dismisses_with_the_registers_own_justification(
        self, tmp_path, gh, capsys
    ):
        gh["open"] = [api_alert()]
        assert arc.cmd_converge(repo(tmp_path), apply=True) == 0
        kind, number, reason, comment = gh["calls"][0]
        assert (kind, number, reason) == ("dismiss", 1, "won't fix")
        assert "sufficiently long justification" in comment
        assert am.marker_in(comment) == "ar-live", "provenance must be stamped"

    def test_apply_reopens_on_expiry(self, tmp_path, gh, capsys):
        gh["dismissed"] = [api_alert(state="dismissed",
                                     comment=f"x {am.marker_for('ar-live')}")]
        assert arc.cmd_converge(repo(tmp_path, expires="2026-01-01"), apply=True) == 0
        assert gh["calls"] == [("reopen", 1)]

    def test_human_dismissals_are_summarised_and_untouched(self, tmp_path, gh, capsys):
        gh["dismissed"] = [api_alert(state="dismissed", comment="a person decided")]
        arc.cmd_converge(repo(tmp_path))
        assert "left untouched" in capsys.readouterr().out
        assert gh["calls"] == []

    def test_a_failed_mutation_is_reported_as_failure(self, tmp_path, gh, monkeypatch,
                                                      capsys):
        gh["open"] = [api_alert()]
        monkeypatch.setattr(gcs, "dismiss_alert",
                            lambda *a, **k: (False, "403 Forbidden"))
        assert arc.cmd_converge(repo(tmp_path), apply=True) == 1
        assert "FAILED" in capsys.readouterr().out


class TestTriageApply:
    def test_absent_triage_store_is_genuinely_empty_not_unreadable(self, tmp_path):
        """A bare test root has no store yet; that is empty input, not a failure
        to look, so it must NOT block the converged claim."""
        assert arc._open_security_items(tmp_path) == ([], None)

    def test_absent_store_and_unreadable_store_are_distinguished(
        self, tmp_path, monkeypatch
    ):
        """FileNotFoundError is "no store yet" (empty, fine); anything else is
        "could not look" (blocks the converged claim). The whole point of the
        split is that these two must not collapse."""
        import triage
        def gone(*_a, **_kw):
            raise FileNotFoundError("no triage.jsonl")
        monkeypatch.setattr(triage, "read_all_items", gone)
        assert arc._open_security_items(tmp_path) == ([], None)

    def test_unreadable_triage_store_reports_a_reason_not_emptiness(
        self, tmp_path, monkeypatch
    ):
        """External review (GPT #3). A broken store must not take down the ALERT
        surface, but it must not be laundered into "there was nothing there"
        either — the run then prints `converged` over unreconciled items."""
        import triage
        def boom(*_a, **_kw):
            raise OSError("store is corrupt")
        monkeypatch.setattr(triage, "read_all_items", boom)
        items, reason = arc._open_security_items(tmp_path)
        assert items == [] and "store is corrupt" in reason

    def test_unreadable_store_blocks_converged_end_to_end(
        self, tmp_path, gh, monkeypatch, capsys
    ):
        import triage
        def boom(*_a, **_kw):
            raise OSError("store is corrupt")
        monkeypatch.setattr(triage, "read_all_items", boom)
        assert arc.cmd_converge(repo(tmp_path)) == 1
        out = capsys.readouterr().out
        assert "UNREAD" in out and "converged - the security surface" not in out

    def test_triage_dismissal_uses_the_registered_gc_tokens(self, tmp_path, monkeypatch,
                                                            capsys):
        seen = {}
        import triage
        monkeypatch.setattr(triage, "mark_status",
                            lambda root, iid, **kw: seen.update(kw, id=iid))
        plan = ac.Plan(triage_dismiss=[(load_register(repo(tmp_path))[0],
                                        {"id": "trg-1"})])
        assert arc._apply_triage(plan, tmp_path) == 0
        assert seen["by"] == ac.TRIAGE_DISMISSER
        assert seen["reason"] == ac.TRIAGE_REASON

    def test_per_item_failure_is_fail_soft(self, tmp_path, monkeypatch, capsys):
        import triage
        def boom(*a, **k):
            raise KeyError("gone")
        monkeypatch.setattr(triage, "mark_status", boom)
        plan = ac.Plan(triage_dismiss=[(load_register(repo(tmp_path))[0],
                                        {"id": "trg-1"})])
        assert arc._apply_triage(plan, tmp_path) == 1

    def test_no_items_needs_no_triage_import(self, tmp_path):
        assert arc._apply_triage(ac.Plan(), tmp_path) == 0


class TestCliDispatch:
    def test_converge_is_reachable_from_the_real_entry_point(self, tmp_path, gh):
        gh["open"] = [api_alert()]
        assert cli.main(["converge", "--project-root", str(repo(tmp_path))]) == 1

    def test_apply_flag_is_wired(self, tmp_path, gh):
        gh["open"] = [api_alert()]
        cli.main(["converge", "--project-root", str(repo(tmp_path)), "--apply"])
        assert gh["calls"] and gh["calls"][0][0] == "dismiss"

    def test_repo_identity_failure_exits_two_not_zero(self, tmp_path, monkeypatch,
                                                      capsys):
        """Exit 2 is fail-closed. Exiting 0 would read as 'converged'."""
        monkeypatch.setattr(arc.github_api, "owner_repo", lambda root: None)
        assert cli.main(["converge", "--project-root", str(repo(tmp_path))]) == 2
        assert "refusing" in capsys.readouterr().err

    def test_offline_subcommands_still_work(self, tmp_path):
        assert cli.main(["check", "--project-root", str(tmp_path)]) == 0
        assert cli.main(["expire", "--project-root", str(tmp_path)]) == 0


class TestThisRepoRegister:
    """Binding gate: run against the register actually committed here."""

    def entries(self):
        return [e for e in load_register(REPO_ROOT)
                if e.target == ac.TARGET_GITHUB_DISMISSAL]

    def test_every_github_dismissal_entry_is_unambiguously_resolvable(self):
        problems = {e.id: am.scope_problem(e) for e in self.entries()}
        bad = {k: v for k, v in problems.items() if v}
        assert not bad, (
            "github-dismissal entries that cannot be resolved to alerts:\n"
            + "\n".join(f"  {k}: {v}" for k, v in bad.items())
            + "\n\nDeclare scope.tool plus either scope.paths or "
              "scope.match: rule-wide. Ambiguity is refused, never guessed."
        )

    def test_every_entry_produces_a_marked_dismissal_comment(self):
        for e in self.entries():
            assert am.marker_in(am.dismissal_comment(e)) == e.id

    def test_converge_is_not_wired_into_any_workflow(self):
        """No scheduled job may hold the authority to mass-dismiss security
        alerts — an automated reconciler is the shape that produced webui #285.
        This asserts the absence is real, not just intended."""
        workflows = REPO_ROOT / ".github" / "workflows"
        offenders = [
            wf.name for wf in [*workflows.glob("*.yml"), *workflows.glob("*.yaml")]
            if "converge" in wf.read_text(encoding="utf-8")
        ]
        assert not offenders, f"converge must stay operator-invoked: {offenders}"
