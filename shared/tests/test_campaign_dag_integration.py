"""Integration test (``category: "integration"``, ``cross_component``):
a 3-unit campaign (A, B depends on A, C independent) driven end to end
through ``campaign_status``/``campaign_graph``'s projection and
``autonomous_loop``'s ``cmd_init``/``cmd_next``/``cmd_record`` — proving B
waits for A's VERIFIED ``merged_commit`` ancestry to survive a simulated
campaign resume, and C is never blocked by it; a second scenario edits B's
``depends_on`` after B is claimed and asserts only B degrades.

Lives under ``shared/tests`` (this repo's one-test-root-per-process rule,
and this campaign's own test-strategy note): every module under test here —
``lib.autonomous_loop``, ``lib.loop_state``, ``lib.campaign_graph``,
``lib.campaign_status`` — is importable from this root already. The campaign
fixture is built directly (the ``campaign_init.py`` shape, hand-written)
rather than by importing that OTHER plugin's tool, keeping this test inside
one pytest root per this repo's hard rule.

Every subprocess-level assertion here is paired with the dedicated in-process
unit coverage in ``test_loop_state.py`` (``verify_merged_commit_ancestry``)
and ``test_autonomous_loop_depends_on.py`` (the guard clause itself) — this
test monkeypatches ancestry verification at the MODULE-OBJECT level
(``lib.loop_state.verify_merged_commit_ancestry``) so it stays a fast,
deterministic, in-process test of the ORDERING logic, not of git plumbing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from lib import loop_state
from lib.campaign_graph import safe_project_campaign_status

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from autonomous_loop import cmd_init, cmd_next, cmd_record  # noqa: E402


CAMPAIGN_MD = """---
campaign: dag-demo
status: active
branch_strategy: serial
created: 2026-09-21T00:00:00+00:00
---

## Sub-Iterates

| ID | Slug | Title | Status | Depends On |
|---|---|---|---|---|
| A | alpha | First | pending |  |
| B | bravo | Second | pending | A |
| C | charlie | Third | pending |  |
"""


class FakeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _write_campaign(tmp_path, *, sub_iterates):
    campaign_dir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "dag-demo"
    campaign_dir.mkdir(parents=True)
    (campaign_dir / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
    status = {"campaign": "dag-demo", "status": "active", "branch_strategy": "serial",
              "sub_iterates": sub_iterates}
    (campaign_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    events_log = tmp_path / "shipwright_events.jsonl"
    events_log.write_text("", encoding="utf-8")
    return campaign_dir, events_log


def _base_subs(**overrides):
    subs = [
        {"id": "A", "slug": "alpha", "spec_path": "x/A.md", "status": "pending",
         "commit": None, "branch": None, "tests_passed": None, "tests_total": None,
         "depends_on": [], "merged_commit": None},
        {"id": "B", "slug": "bravo", "spec_path": "x/B.md", "status": "pending",
         "commit": None, "branch": None, "tests_passed": None, "tests_total": None,
         "depends_on": ["A"], "merged_commit": None},
        {"id": "C", "slug": "charlie", "spec_path": "x/C.md", "status": "pending",
         "commit": None, "branch": None, "tests_passed": None, "tests_total": None,
         "depends_on": [], "merged_commit": None},
    ]
    for s in subs:
        s.update(overrides.get(s["id"], {}))
    return subs


class TestResumeAcrossDependency:
    @patch("autonomous_loop.subprocess.run")
    def test_b_waits_for_a_then_unblocks_across_resume_c_never_blocked(self, mock_run, tmp_path):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()

        # --- Pass 1: fresh campaign, nothing built yet ---
        campaign_dir, events_log = _write_campaign(tmp_path, sub_iterates=_base_subs())
        units_file = campaign_dir / "status.json"
        state_path = tmp_path / ".shipwright" / "loop_state.json"

        assert cmd_init(FakeArgs(
            state=str(state_path), units_from=str(units_file), kind="sub_iterate",
            branch_strategy="serial", root_session_id="",
        )) == 0

        out1 = cmd_next(FakeArgs(state=str(state_path)))
        assert out1 == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        claimed = [u for u in state["units"] if u["status"] == "in_progress"]
        assert [u["id"] for u in claimed] == ["A"]  # B blocked, skipped; A claimed FIFO

        # Simulate A's build + PR + real GH merge: record it complete, then
        # reflect that in the campaign's committed status.json (what a real
        # merge's F5b/3h steps would have written).
        assert cmd_record(FakeArgs(
            state=str(state_path), unit="A",
            result=json.dumps({"status": "complete", "commit": "sha-a-merged",
                               "tests_passed": 1, "tests_total": 1}),
        )) == 0
        merged_subs = _base_subs(A={"status": "complete", "commit": "sha-a-merged"})
        (campaign_dir / "status.json").write_text(json.dumps({
            "campaign": "dag-demo", "sub_iterates": merged_subs}), encoding="utf-8")

        # --- Simulated RESUME: loop_state.json is rebuilt fresh from the
        # (now updated) campaign status.json — this is where the
        # complete -> merged mapping + ancestry verification actually fire. ---
        state_path.unlink()
        with patch.object(loop_state, "verify_merged_commit_ancestry", lambda c: c):  # verified
            assert cmd_init(FakeArgs(
                state=str(state_path), units_from=str(campaign_dir / "status.json"),
                kind="sub_iterate", branch_strategy="serial", root_session_id="",
            )) == 0

            resumed = json.loads(state_path.read_text(encoding="utf-8"))
            a_unit = next(u for u in resumed["units"] if u["id"] == "A")
            assert a_unit["status"] == "merged"
            assert a_unit["merged_commit"] == "sha-a-merged"

            out2 = cmd_next(FakeArgs(state=str(state_path)))
            assert out2 == 0
            state2 = json.loads(state_path.read_text(encoding="utf-8"))
            claimed2 = [u for u in state2["units"] if u["status"] == "in_progress"]
            assert claimed2[0]["id"] == "B"  # unblocked now that A verified-merged

            # C must never have been blocked by B's edge: claim it next.
            out3 = cmd_next(FakeArgs(state=str(state_path)))
            assert out3 == 0
            state3 = json.loads(state_path.read_text(encoding="utf-8"))
            in_progress_ids = {u["id"] for u in state3["units"] if u["status"] == "in_progress"}
            assert in_progress_ids == {"B", "C"}

    def test_ancestry_unverified_keeps_b_blocked_across_resume(self, tmp_path):
        # Same resume, but the fresh ancestry check FAILS (e.g. rewritten
        # history) — B must stay blocked even though status.json says complete.
        merged_subs = _base_subs(A={"status": "complete", "commit": "sha-a-rewritten"})
        campaign_dir, events_log = _write_campaign(tmp_path, sub_iterates=merged_subs)
        state_path = tmp_path / ".shipwright" / "loop_state.json"

        with patch.object(loop_state, "verify_merged_commit_ancestry", lambda c: None):  # NEVER verifies
            assert cmd_init(FakeArgs(
                state=str(state_path), units_from=str(campaign_dir / "status.json"),
                kind="sub_iterate", branch_strategy="serial", root_session_id="",
            )) == 0
            with patch("autonomous_loop.subprocess.run") as mock_run:
                mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc\n"})()
                out = cmd_next(FakeArgs(state=str(state_path)))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            claimed = [u["id"] for u in state["units"] if u["status"] == "in_progress"]
            assert claimed == ["C"]  # only the independent unit is claimable; B stays blocked
            assert out == 0


class TestFrozenContractDegradesOnlyThatUnit:
    def test_editing_claimed_units_depends_on_reverts_only_that_unit(self, tmp_path):
        campaign_dir, events_log = _write_campaign(tmp_path, sub_iterates=_base_subs())

        # B is claimed (in_progress) — frozen from this point forward.
        loop_state_path = tmp_path / ".shipwright" / "loop_state.json"
        loop_state_path.write_text(json.dumps({"units": [
            {"id": "B", "status": "in_progress", "depends_on": ["A"]},
        ]}), encoding="utf-8")

        # An operator (or a stray edit) removes B's dependency on A in campaign.md.
        edited_md = CAMPAIGN_MD.replace(
            "| B | bravo | Second | pending | A |",
            "| B | bravo | Second | pending |  |",
        )
        (campaign_dir / "campaign.md").write_text(edited_md, encoding="utf-8")

        status, summary = safe_project_campaign_status(campaign_dir, events_log)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["depends_on"] == ["A"]  # reverted to frozen — the edit did NOT take
        assert by_id["A"]["depends_on"] == []  # untouched
        assert by_id["C"]["depends_on"] == []  # untouched
        assert "degraded_reason" in summary and "frozen" in summary["degraded_reason"]
