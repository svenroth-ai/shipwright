"""``loop_claim.py readiness`` (campaign-dag-scheduler, WebUI card 10): the
read-only twin of ``next-batch``. Real git repo for the ancestry rule — the
whole point is that the simple "deps merged" rule is NOT the launchable rule.
"""

from __future__ import annotations

import argparse
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import loop_claim, loop_ready_set
from lib.contract_skeleton import _merge, diff_skeletons, skeleton_of
from lib.loop_claim import cmd_next_batch, cmd_readiness
from lib.loop_ready_set import READINESS_SCHEMA_VERSION, REASONS, build_readiness

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "loop_claim.py"
_FIXTURE = Path(__file__).parent / "contracts" / "loop-readiness-1.0.json"


def _git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _git(r, "commit", "-q", "--allow-empty", "-m", "on-main")
    on_main = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-q", "-b", "side")
    _git(r, "commit", "-q", "--allow-empty", "-m", "off-main")
    off_main = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-q", "main")
    return r, on_main, off_main


def _state(units, **kw):
    s = {"loop_id": "L", "kind": "sub_iterate", "branch_strategy": "independent", "units": units}
    s.update(kw)
    return s


def _matrix(on_main, off_main):
    return [
        {"id": "A", "status": "merged", "merged_commit": on_main, "depends_on": []},
        {"id": "D", "status": "merged", "merged_commit": off_main, "depends_on": []},
        {"id": "N", "status": "merged", "depends_on": []},  # merged, no commit
        {"id": "P", "status": "pending", "depends_on": []},
        {"id": "READY", "status": "pending", "depends_on": ["A"]},
        {"id": "ROOT", "status": "pending", "depends_on": []},
        {"id": "OFFBASE", "status": "pending", "depends_on": ["D"]},
        {"id": "UNMERGED", "status": "pending", "depends_on": ["P"]},
        {"id": "GHOST", "status": "pending", "depends_on": ["nope"]},
        {"id": "NOCOMMIT", "status": "pending", "depends_on": ["N"]},
        {"id": "MIXED", "status": "pending", "depends_on": ["A", "D", "P"]},
        {"id": "RUN", "status": "running", "depends_on": ["P"]},
    ]


def _by_id(report):
    return {r["id"]: r for r in report["units"]}


class TestBuildReadiness:
    def test_reasons_and_flags(self, repo):
        r, on_main, off_main = repo
        rep = build_readiness(_state(_matrix(on_main, off_main)), cwd=str(r))
        rows = _by_id(rep)
        assert rep["schema_version"] == READINESS_SCHEMA_VERSION
        assert rep["supported"] is True and rep["base_branch"] == "main"
        for uid in ("READY", "ROOT", "P"):
            assert rows[uid]["ready"] is True and rows[uid]["blocked_by"] == []
        want = {"OFFBASE": ["commit_not_on_base"], "UNMERGED": ["not_merged"],
                "GHOST": ["dependency_missing"], "NOCOMMIT": ["commit_missing"],
                "MIXED": ["commit_not_on_base", "not_merged"]}
        for uid, reasons in want.items():
            assert rows[uid]["ready"] is False
            assert [b["reason"] for b in rows[uid]["blocked_by"]] == reasons
        assert [b["id"] for b in rows["MIXED"]["blocked_by"]] == ["D", "P"]
        # non-pending: state reported, never ready, nothing to unblock
        assert rows["RUN"] == {"id": "RUN", "state": "running", "ready": False, "blocked_by": []}
        assert rows["A"]["state"] == "merged" and rows["A"]["ready"] is False

    @pytest.mark.parametrize("strategy", ["stacked", "single-branch", "bogus"])
    def test_unsupported_strategy_blocks_every_pending_unit(self, repo, strategy):
        r, on_main, off_main = repo
        rep = build_readiness(_state(_matrix(on_main, off_main), branch_strategy=strategy), cwd=str(r))
        assert rep["supported"] is False and rep["base_branch"] is None and rep["ready_ids"] == []
        for row in rep["units"]:
            if row["state"] == "pending":  # even dependency-free ones: next-batch refuses all
                assert [b["reason"] for b in row["blocked_by"]] == ["unsupported_strategy"]

    def test_finalized_campaign_is_never_ready(self, repo):
        r, on_main, off_main = repo
        rep = build_readiness(_state(_matrix(on_main, off_main), finalized=True), cwd=str(r))
        assert rep["finalized"] is True and rep["ready_ids"] == []
        assert _by_id(rep)["ROOT"]["blocked_by"][0]["reason"] == "campaign_finalized"


class TestAgreesWithNextBatch:
    def test_next_batch_claims_exactly_the_readiness_ready_set(self, repo, tmp_path, capsys):
        r, on_main, off_main = repo
        sp = tmp_path / ".shipwright" / "loop_state.json"
        sp.parent.mkdir(parents=True)
        sp.write_text(json.dumps(_state(_matrix(on_main, off_main))), encoding="utf-8")
        before = sp.read_bytes()

        ns = argparse.Namespace(state=str(sp), campaign_worktree=str(r))
        assert cmd_readiness(ns) == 0
        ready_ids = json.loads(capsys.readouterr().out)["ready_ids"]
        assert sp.read_bytes() == before, "readiness must not write state"
        assert not (sp.parent / "loop.lock").exists(), "readiness must not take the lock"

        assert cmd_next_batch(argparse.Namespace(state=str(sp), campaign_worktree=str(r), max_parallel=8)) == 0
        claimed = [c["id"] for c in json.loads(capsys.readouterr().out)["claimed"]]
        assert claimed and sorted(claimed) == sorted(ready_ids)

    @pytest.mark.parametrize("variant", ["case_mismatch", "serial"])
    def test_agreement_edge_cases(self, repo, tmp_path, capsys, monkeypatch, variant):
        r, on_main, off_main = repo
        units = _matrix(on_main, off_main)
        strategy = "independent"
        if variant == "case_mismatch":
            units.append({"id": "LOWER", "status": "pending", "depends_on": ["a"]})
        else:
            strategy = "serial"
            monkeypatch.setattr(loop_ready_set, "fresh_remote_default_ref", lambda cwd=None: "main")
        sp = tmp_path / "s.json"
        sp.write_text(json.dumps(_state(units, branch_strategy=strategy)), encoding="utf-8")
        ns = argparse.Namespace(state=str(sp), campaign_worktree=str(r))
        assert cmd_readiness(ns) == 0
        rep = json.loads(capsys.readouterr().out)
        assert variant != "case_mismatch" or "LOWER" in rep["ready_ids"]
        for row in rep["units"]:  # a pending row that is not ready always says why
            assert row["state"] != "pending" or row["ready"] or row["blocked_by"]
        assert cmd_next_batch(argparse.Namespace(state=str(sp), campaign_worktree=str(r), max_parallel=8)) == 0
        claimed = [c["id"] for c in json.loads(capsys.readouterr().out)["claimed"]]
        assert sorted(claimed) == sorted(rep["ready_ids"])

    def test_at_most_one_fetch_and_verdict_survives_a_moving_ref(self, repo):
        """Many dependents of one off-base dep => ONE fetch, and ready/blocked_by
        stay consistent even if the ref advances between the two asks."""
        from unittest.mock import patch
        r, on_main, off_main = repo
        units = [{"id": "D", "status": "merged", "merged_commit": off_main, "depends_on": []}]
        units += [{"id": f"U{i}", "status": "pending", "depends_on": ["D"]} for i in range(5)]
        with patch.object(loop_ready_set, "_is_ancestor", side_effect=[False, False, True, True, True]), \
                patch.object(loop_ready_set.subprocess, "run") as fetch:
            rep = build_readiness(_state(units), cwd=str(r))
        assert fetch.call_count == 1
        for row in rep["units"][1:]:
            assert row["ready"] != bool(row["blocked_by"])

    def test_finalized_does_not_resolve_a_base(self, repo, monkeypatch):
        r, on_main, off_main = repo
        def boom(cwd=None):
            raise AssertionError("must not fetch for a finalized campaign")
        monkeypatch.setattr(loop_ready_set, "fresh_remote_default_ref", boom)
        rep = build_readiness(_state(_matrix(on_main, off_main), branch_strategy="serial", finalized=True), cwd=str(r))
        assert rep["ready_ids"] == [] and rep["base_branch"] is None

    def test_unsupported_strategy_agrees_next_batch_refuses(self, repo, tmp_path):
        r, on_main, off_main = repo
        sp = tmp_path / "s.json"
        sp.write_text(json.dumps(_state(_matrix(on_main, off_main), branch_strategy="stacked")), encoding="utf-8")
        assert cmd_next_batch(argparse.Namespace(state=str(sp), campaign_worktree=str(r), max_parallel=8)) == 1

    def test_both_paths_use_one_function(self):
        """Structural pin: next-batch must not carry its own copy of the rule."""
        assert loop_claim.ready_unit_ids is loop_ready_set.ready_unit_ids
        assert "ready_unit_ids(" in inspect.getsource(loop_claim.cmd_next_batch)
        assert "_pending_blockers(" in inspect.getsource(loop_ready_set.build_readiness)
        assert "_pending_blockers(" in inspect.getsource(loop_ready_set.ready_unit_ids)


class TestCli:
    def _run(self, *args):
        return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True)

    def test_json_output_and_exit_zero(self, repo, tmp_path):
        r, on_main, off_main = repo
        sp = tmp_path / "s.json"
        sp.write_text(json.dumps(_state(_matrix(on_main, off_main))), encoding="utf-8")
        p = self._run("readiness", "--state", str(sp), "--campaign-worktree", str(r), "--json")
        assert p.returncode == 0, p.stderr
        assert "READY" in json.loads(p.stdout)["ready_ids"]

    def test_rejects_section_state_and_missing_file(self, repo, tmp_path):
        r, *_ = repo
        sp = tmp_path / "s.json"
        sp.write_text(json.dumps({"kind": "section", "units": []}), encoding="utf-8")
        assert self._run("readiness", "--state", str(sp), "--campaign-worktree", str(r)).returncode == 1
        gone = tmp_path / "missing.json"
        assert self._run("readiness", "--state", str(gone), "--campaign-worktree", str(r)).returncode == 1

    def test_malformed_state_is_a_structured_error(self, repo, tmp_path):
        r, *_ = repo
        sp = tmp_path / "s.json"
        sp.write_text(json.dumps({"kind": "sub_iterate", "branch_strategy": "independent"}), encoding="utf-8")
        p = self._run("readiness", "--state", str(sp), "--campaign-worktree", str(r))
        assert p.returncode == 1 and json.loads(p.stderr)["error"] == "malformed_state"


class TestWireContract:
    def test_shape_matches_frozen_v1_fixture(self, repo):
        """The WebUI renders this JSON. A shape change needs a version bump
        and a NEW `loop-readiness-<ver>.json` — never edit the published one."""
        r, on_main, off_main = repo
        supported = build_readiness(_state(_matrix(on_main, off_main)), cwd=str(r))
        refused = build_readiness(_state(_matrix(on_main, off_main), branch_strategy="stacked"), cwd=str(r))
        # both arms: base_branch / blocked_by[].id are nullable on the wire
        live = _merge(skeleton_of(supported), skeleton_of(refused))
        fixture = _FIXTURE.with_name(f"loop-readiness-{READINESS_SCHEMA_VERSION}.json")
        assert fixture.exists(), "bump => add a NEW loop-readiness-<version>.json, never edit the old one"
        pinned = json.loads(fixture.read_text(encoding="utf-8"))
        assert pinned["version"] == READINESS_SCHEMA_VERSION
        # the closed reason vocabulary consumers switch on is part of the contract
        assert set(pinned["contract"]["enums"]["blocked_by.reason"]) == set(REASONS)
        d = diff_skeletons(pinned["contract"]["skeleton"], live)
        assert not (d.added or d.removed or d.retyped), d
