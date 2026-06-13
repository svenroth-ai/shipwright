"""Tests for branch_base — per-strategy base-ref resolution
(extracted from autonomous_loop; iterate-2026-06-13-campaign-serial-default).

The serial strategy branches each sub-iterate off the FRESHLY-FETCHED remote
default ref (origin/<default>), NEVER the possibly-stale local main, so a
sub-iterate can't regress the prior sub-iterate's merged changes (external-review
HIGH: code-enforce freshness, don't trust orchestration prose).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from branch_base import resolve_base_branch, resolve_default_branch


def _git_fake(symbolic_ref_stdout="refs/remotes/origin/main\n", fetch_raises=None):
    def fake(cmd, *a, **k):
        sub = cmd[:2] if isinstance(cmd, list) else []
        if sub == ["git", "fetch"]:
            if fetch_raises:
                raise fetch_raises
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if sub == ["git", "symbolic-ref"]:
            return type("R", (), {"returncode": 0, "stdout": symbolic_ref_stdout, "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "abc\n", "stderr": ""})()
    return fake


# --- serial: fresh remote default ref ---------------------------------------

@patch("branch_base.subprocess.run")
def test_serial_returns_fresh_remote_default(mock_run):
    mock_run.side_effect = _git_fake()
    units = [{"id": "S1", "branch": "iterate/s1"},
             {"id": "S2", "branch": None}]
    # The fresh REMOTE ref, not the local "main".
    assert resolve_base_branch("serial", units, units[1]) == "origin/main"


@patch("branch_base.subprocess.run")
def test_serial_first_unit_also_off_fresh_remote(mock_run):
    """Unlike stacked (first unit has no base), serial branches EVERY unit."""
    mock_run.side_effect = _git_fake()
    units = [{"id": "S1", "branch": None}]
    assert resolve_base_branch("serial", units, units[0]) == "origin/main"


@patch("branch_base.subprocess.run")
def test_serial_respects_non_main_default_branch(mock_run):
    """Resolve the default from origin/HEAD — not a hardcoded 'main'."""
    mock_run.side_effect = _git_fake(symbolic_ref_stdout="refs/remotes/origin/develop\n")
    units = [{"id": "S1", "branch": None}]
    assert resolve_base_branch("serial", units, units[0]) == "origin/develop"


@patch("branch_base.subprocess.run")
def test_serial_fetch_failure_is_failsoft(mock_run):
    """A failed `git fetch` must NOT crash — resolve against the last-known ref."""
    mock_run.side_effect = _git_fake(fetch_raises=FileNotFoundError("git missing"))
    units = [{"id": "S1", "branch": None}]
    assert resolve_base_branch("serial", units, units[0]) == "origin/main"


@patch("branch_base.subprocess.run")
def test_resolve_default_branch_falls_back_to_main_on_error(mock_run):
    mock_run.side_effect = FileNotFoundError("git missing")
    assert resolve_default_branch() == "main"


# --- legacy strategies (unchanged) ------------------------------------------

def test_stacked_returns_prev_branch():
    units = [{"id": "S1", "branch": "iterate/s1"},
             {"id": "S2", "branch": None}]
    assert resolve_base_branch("stacked", units, units[1]) == "iterate/s1"


def test_stacked_first_unit_has_no_base():
    units = [{"id": "S1", "branch": None}]
    assert resolve_base_branch("stacked", units, units[0]) is None


def test_independent_returns_local_main():
    units = [{"id": "S1", "branch": None}]
    assert resolve_base_branch("independent", units, units[0]) == "main"


def test_single_branch_returns_none():
    units = [{"id": "S1", "branch": None}]
    assert resolve_base_branch("single-branch", units, units[0]) is None


# --- strategy vocabulary (gates `autonomous_loop init --branch-strategy serial`)

def test_serial_is_a_valid_strategy():
    from autonomous_loop import VALID_STRATEGIES
    assert "serial" in VALID_STRATEGIES


def test_legacy_strategies_retained():
    """serial is additive — stacked/single-branch/independent stay (build + legacy)."""
    from autonomous_loop import VALID_STRATEGIES
    assert {"single-branch", "stacked", "independent"} <= VALID_STRATEGIES
