"""Tests for autonomous_loop.py CLI state-machine.

Tests all 4 commands (init, next, record, finalize) including
negative-path tests from external review Finding 10.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_init, cmd_next, cmd_record, cmd_finalize


class FakeArgs:
    """Minimal argparse.Namespace substitute."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def state_dir(tmp_path):
    ship = tmp_path / ".shipwright"
    ship.mkdir()
    return ship


@pytest.fixture
def units_file(tmp_path):
    """Create a build config with 3 sections."""
    config = {
        "sections": [
            {"name": "01-auth", "status": "not_started", "spec_path": "sections/01-auth.md"},
            {"name": "02-api", "status": "not_started", "spec_path": "sections/02-api.md"},
            {"name": "03-ui", "status": "not_started", "spec_path": "sections/03-ui.md"},
        ]
    }
    f = tmp_path / "shipwright_build_config.json"
    f.write_text(json.dumps(config), encoding="utf-8")
    return f


@pytest.fixture
def units_with_complete(tmp_path):
    """Config where one section is already complete."""
    config = {
        "sections": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-api", "status": "not_started"},
        ]
    }
    f = tmp_path / "shipwright_build_config.json"
    f.write_text(json.dumps(config), encoding="utf-8")
    return f


@pytest.fixture
def iterate_units_file(tmp_path):
    """Create a campaign status.json with sub-iterates."""
    config = {
        "sub_iterates": [
            {"id": "14.0", "slug": "phase-dropdown", "spec_path": "sub-iterates/14.0.md"},
            {"id": "14.1", "slug": "preview-button", "spec_path": "sub-iterates/14.1.md"},
        ]
    }
    f = tmp_path / "status.json"
    f.write_text(json.dumps(config), encoding="utf-8")
    return f


class TestInit:
    def test_creates_state_file(self, state_dir, units_file, capsys):
        state_path = state_dir / "loop_state.json"
        args = FakeArgs(
            state=str(state_path),
            units_from=str(units_file),
            kind="section",
            branch_strategy="single-branch",
            root_session_id="test-session-123",
        )
        ret = cmd_init(args)
        assert ret == 0
        assert state_path.exists()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["kind"] == "section"
        assert state["branch_strategy"] == "single-branch"
        assert state["root_session_id"] == "test-session-123"
        assert len(state["units"]) == 3
        assert all(u["status"] == "pending" for u in state["units"])

    def test_skips_already_complete(self, state_dir, units_with_complete, capsys):
        state_path = state_dir / "loop_state.json"
        args = FakeArgs(
            state=str(state_path),
            units_from=str(units_with_complete),
            kind="section",
            branch_strategy="single-branch",
            root_session_id="",
        )
        ret = cmd_init(args)
        assert ret == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert len(state["units"]) == 1
        assert state["units"][0]["id"] == "02-api"

    def test_resumes_existing_state(self, state_dir, units_file, capsys):
        state_path = state_dir / "loop_state.json"
        existing = {
            "loop_id": "section-20260415",
            "kind": "section",
            "root_session_id": "",
            "branch_strategy": "single-branch",
            "units": [
                {"id": "01-auth", "status": "complete"},
                {"id": "02-api", "status": "pending"},
            ],
        }
        state_path.write_text(json.dumps(existing), encoding="utf-8")
        args = FakeArgs(
            state=str(state_path),
            units_from=str(units_file),
            kind="section",
            branch_strategy="single-branch",
            root_session_id="",
        )
        ret = cmd_init(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "resumed"
        assert out["pending"] == 1

    def test_empty_units_returns_2(self, state_dir, tmp_path, capsys):
        config = {"sections": [{"name": "01-auth", "status": "complete"}]}
        f = tmp_path / "config.json"
        f.write_text(json.dumps(config), encoding="utf-8")
        state_path = state_dir / "loop_state.json"
        args = FakeArgs(
            state=str(state_path),
            units_from=str(f),
            kind="section",
            branch_strategy="single-branch",
            root_session_id="",
        )
        ret = cmd_init(args)
        assert ret == 2

    def test_missing_units_file(self, state_dir):
        args = FakeArgs(
            state=str(state_dir / "loop_state.json"),
            units_from="/nonexistent/file.json",
            kind="section",
            branch_strategy="single-branch",
            root_session_id="",
        )
        ret = cmd_init(args)
        assert ret == 1

    def test_iterate_kind(self, state_dir, iterate_units_file, capsys):
        state_path = state_dir / "loop_state.json"
        args = FakeArgs(
            state=str(state_path),
            units_from=str(iterate_units_file),
            kind="sub_iterate",
            branch_strategy="stacked",
            root_session_id="root-456",
        )
        ret = cmd_init(args)
        assert ret == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["kind"] == "sub_iterate"
        assert state["branch_strategy"] == "stacked"
        assert len(state["units"]) == 2


class TestNext:
    def _make_state(self, state_dir, units, strategy="single-branch"):
        state_path = state_dir / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "root_session_id": "root-123",
            "branch_strategy": strategy,
            "units": units,
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state_path

    @patch("autonomous_loop.subprocess.run")
    def test_picks_first_pending(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "complete"},
            {"id": "02-api", "status": "pending", "spec_path": "spec/02.md",
             "attempt": 0, "started_at": None, "finished_at": None,
             "commit": None, "head_sha": None, "branch": None,
             "result_path": None, "handoff_path": None, "failure_reason": None},
        ])
        args = FakeArgs(state=str(state_path))
        ret = cmd_next(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "02-api"
        assert out["loop_id"] == "test-loop"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][1]["status"] == "in_progress"

    def test_returns_2_when_all_done(self, state_dir, capsys):
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "complete"},
            {"id": "02-api", "status": "complete"},
        ])
        args = FakeArgs(state=str(state_path))
        ret = cmd_next(args)
        assert ret == 2
        out = json.loads(capsys.readouterr().out)
        assert out["done"] is True

    @patch("autonomous_loop.subprocess.run")
    def test_stacked_provides_base_branch(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc\n"})()
        state_path = self._make_state(state_dir, [
            {"id": "14.0", "status": "complete", "branch": "iterate/camp.0-dropdown"},
            {"id": "14.1", "status": "pending", "spec_path": "spec/14.1.md",
             "attempt": 0, "started_at": None, "finished_at": None,
             "commit": None, "head_sha": None, "branch": None,
             "result_path": None, "handoff_path": None, "failure_reason": None},
        ], strategy="stacked")
        args = FakeArgs(state=str(state_path))
        ret = cmd_next(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["base_branch"] == "iterate/camp.0-dropdown"


class TestRecord:
    def _make_state(self, state_dir, units):
        state_path = state_dir / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "root_session_id": "",
            "branch_strategy": "single-branch",
            "units": units,
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state_path

    def test_records_success(self, state_dir, tmp_path, capsys):
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "in_progress", "attempt": 0,
             "started_at": "2026-04-15T10:00:00Z", "finished_at": None,
             "commit": None, "head_sha": None, "branch": "build/x",
             "result_path": None, "handoff_path": None, "failure_reason": None},
        ])
        result = {"status": "complete", "commit": "abc123", "tests_passed": 5, "tests_total": 5,
                  "section": "01-auth", "branch": "build/x"}
        args = FakeArgs(state=str(state_path), unit="01-auth", result=json.dumps(result))
        ret = cmd_record(args)
        assert ret == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "complete"
        assert state["units"][0]["commit"] == "abc123"

    def test_records_failure_returns_3(self, state_dir, tmp_path, capsys):
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "in_progress", "attempt": 0,
             "started_at": "2026-04-15T10:00:00Z", "finished_at": None,
             "commit": None, "head_sha": None, "branch": None,
             "result_path": None, "handoff_path": None, "failure_reason": None},
        ])
        result = {"status": "failed", "error": "Tests broken", "section": "01-auth"}
        args = FakeArgs(state=str(state_path), unit="01-auth", result=json.dumps(result))
        ret = cmd_record(args)
        assert ret == 3
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "failed"

    def test_malformed_json_returns_3(self, state_dir, tmp_path, capsys):
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "in_progress", "attempt": 0,
             "started_at": None, "finished_at": None, "commit": None,
             "head_sha": None, "branch": None, "result_path": None,
             "handoff_path": None, "failure_reason": None},
        ])
        args = FakeArgs(state=str(state_path), unit="01-auth", result="not valid json {{{")
        ret = cmd_record(args)
        assert ret == 3
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "failed"
        assert "Non-JSON" in state["units"][0]["failure_reason"]

    def test_contract_violation_returns_3(self, state_dir, tmp_path, capsys):
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "in_progress", "attempt": 0,
             "started_at": None, "finished_at": None, "commit": None,
             "head_sha": None, "branch": None, "result_path": None,
             "handoff_path": None, "failure_reason": None},
        ])
        result = {"status": "complete"}
        args = FakeArgs(state=str(state_path), unit="01-auth", result=json.dumps(result))
        ret = cmd_record(args)
        assert ret == 3


class TestFinalize:
    def test_summary_all_complete(self, state_dir, capsys):
        state_path = state_dir / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "units": [
                {"id": "01-auth", "status": "complete", "commit": "abc"},
                {"id": "02-api", "status": "complete", "commit": "def"},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        args = FakeArgs(state=str(state_path))
        ret = cmd_finalize(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["completed"] == 2
        assert out["failed"] == 0
        assert out["terminal_reason"] == "all_complete"

    def test_summary_with_failure(self, state_dir, capsys):
        state_path = state_dir / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "units": [
                {"id": "01-auth", "status": "complete", "commit": "abc"},
                {"id": "02-api", "status": "failed", "commit": None},
                {"id": "03-ui", "status": "pending", "commit": None},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        args = FakeArgs(state=str(state_path))
        ret = cmd_finalize(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["completed"] == 1
        assert out["failed"] == 1
        assert out["pending"] == 1
        assert "02-api" in out["terminal_reason"]

    def test_aggregates_handoffs(self, state_dir, tmp_path, capsys):
        os.chdir(tmp_path)
        handoff_dir = tmp_path / "planning" / "handoffs" / "test-loop"
        handoff_dir.mkdir(parents=True)
        (handoff_dir / "01-auth.md").write_text("Auth handoff content")
        (handoff_dir / "02-api.md").write_text("API handoff content")
        state_path = state_dir / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "units": [
                {"id": "01-auth", "status": "complete", "commit": "abc"},
                {"id": "02-api", "status": "complete", "commit": "def"},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        args = FakeArgs(state=str(state_path))
        cmd_finalize(args)
        campaign_handoff = handoff_dir / "campaign.md"
        assert campaign_handoff.exists()
        content = campaign_handoff.read_text(encoding="utf-8")
        assert "Auth handoff content" in content
        assert "API handoff content" in content


class TestReconciliation:
    def test_reconcile_from_result_json(self, state_dir, tmp_path):
        os.chdir(tmp_path)
        state_path = state_dir / "loop_state.json"
        runs_dir = tmp_path / ".shipwright" / "runs" / "test-loop" / "01-auth"
        runs_dir.mkdir(parents=True)
        (runs_dir / "result.json").write_text(
            json.dumps({"status": "complete", "commit": "abc123"}),
            encoding="utf-8",
        )
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "root_session_id": "",
            "branch_strategy": "single-branch",
            "units": [
                {"id": "01-auth", "status": "in_progress", "attempt": 0,
                 "started_at": "2026-04-15T10:00:00Z", "finished_at": None,
                 "commit": None, "head_sha": None, "branch": None,
                 "result_path": None, "handoff_path": None, "failure_reason": None},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        args = FakeArgs(
            state=str(state_path),
            units_from=str(tmp_path / "dummy.json"),
            kind="section",
            branch_strategy="single-branch",
            root_session_id="",
        )
        (tmp_path / "dummy.json").write_text('{"sections":[]}')
        cmd_init(args)
        reloaded = json.loads(state_path.read_text(encoding="utf-8"))
        assert reloaded["units"][0]["status"] == "complete"


class TestConcurrency:
    def test_next_acquires_lock(self, state_dir, capsys):
        """Verify lock file is created during next command."""
        state_path = state_dir / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "section",
            "root_session_id": "",
            "branch_strategy": "single-branch",
            "units": [
                {"id": "01-auth", "status": "pending", "spec_path": "",
                 "attempt": 0, "started_at": None, "finished_at": None,
                 "commit": None, "head_sha": None, "branch": None,
                 "result_path": None, "handoff_path": None, "failure_reason": None},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with patch("autonomous_loop.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc\n"})()
            args = FakeArgs(state=str(state_path))
            cmd_next(args)
        lock_path = state_dir / "loop.lock"
        assert lock_path.exists()
