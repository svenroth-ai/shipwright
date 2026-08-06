"""S2/S3/S9/S10 run_id guard (Layer 2 of iterate-2026-05-31-phasequality-triage-bundle).

When the resolved run_id is a sentinel (``""`` / ``"unknown"``) or has no
exact ``iterate_history`` entry — AND no matching spec/mini-plan file is on
disk — S2/S3 must SKIP rather than tail-fall-back to the most-recent entry's
complexity and emit an unsatisfiable FAIL (AC-5). A matching file on disk
preserves the file-exists→PASS signal (AC-6).

S9/S10 carry the same guard on the same rationale, one axis over: they read the
tail-fallback's ``type``/``category`` rather than its ``complexity``, so an
unresolvable run_id inherited an *unrelated* run's category and decided S9/S10's
verdict from it (iterate-2026-08-06-s9-s10-sentinel-guard). Neither check has a
run-specific file on disk, so they pass ``candidates=[]`` — there is no
file-exists→PASS signal to preserve, unlike S2/S3/W2.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402
from tools.verifiers._iterate_run_id import has_exact_iterate_entry  # noqa: E402


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    return tmp_path


def _history(proj: Path, entries: list[dict]) -> None:
    (proj / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": entries}), encoding="utf-8")


def _spec_file(proj: Path, stem: str) -> None:
    d = proj / ".shipwright" / "planning" / "iterate"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text("body", encoding="utf-8")


# --- S2 -----------------------------------------------------------------

def test_s2_skip_on_unknown_run_id_ignores_tail_fallback(proj: Path) -> None:
    # The bug: run_id=unknown inherited the latest entry's medium complexity
    # and FAILed on an impossible spec-file match. Now it SKIPs.
    _history(proj, [{"run_id": "iterate-2026-05-30-real", "complexity": "medium"}])
    f = sc.check_s2_iterate_spec(proj, run_id="unknown")
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in f["evidence"]


def test_s2_skip_on_empty_run_id(proj: Path) -> None:
    _history(proj, [{"run_id": "iterate-2026-05-30-real", "complexity": "medium"}])
    assert sc.check_s2_iterate_spec(proj, run_id="")["status"] == pq.STATUS_SKIP


def test_s2_file_on_disk_overrides_guard(proj: Path) -> None:
    # AC-6: a matching spec file on disk → guard does NOT skip; normal logic
    # runs and the file satisfies S2 (PASS), even without an exact entry.
    _history(proj, [{"run_id": "other", "complexity": "medium"}])
    _spec_file(proj, "2026-05-31-myrun")
    f = sc.check_s2_iterate_spec(proj, run_id="myrun")
    assert f["status"] == pq.STATUS_PASS


def test_s2_exact_entry_still_fails_when_spec_missing(proj: Path) -> None:
    # Guard must NOT fire for a real run with an exact entry → genuine FAIL.
    _history(proj, [{"run_id": "real", "complexity": "medium"}])
    f = sc.check_s2_iterate_spec(proj, run_id="real")
    assert f["status"] == pq.STATUS_FAIL


def test_s2_skip_when_no_history_at_all(proj: Path) -> None:
    # No run_config / no entries → unresolvable → SKIP (not a crash).
    assert sc.check_s2_iterate_spec(proj, run_id="unknown")["status"] == pq.STATUS_SKIP


# --- S3 -----------------------------------------------------------------

def test_s3_skip_on_unknown_run_id(proj: Path) -> None:
    _history(proj, [{"run_id": "iterate-2026-05-30-real", "complexity": "medium"}])
    f = sc.check_s3_iterate_miniplan(proj, run_id="unknown")
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in f["evidence"]


def test_s3_exact_entry_still_warns_when_miniplan_missing(proj: Path) -> None:
    _history(proj, [{"run_id": "real", "complexity": "medium"}])
    f = sc.check_s3_iterate_miniplan(proj, run_id="real")
    assert f["status"] == pq.STATUS_WARN


# --- S9 / S10 -----------------------------------------------------------
#
# S9/S10 read the tail-fallback's category, not its complexity. Without the
# guard an unresolvable run_id inherited an unrelated run's `type` and let it
# decide the verdict. The git-backed halves of both checks are covered by
# test_spec_checks.py / test_spec_checks_tier2_git_context.py, so these pin the
# guard alone: git is stubbed to the state that WOULD warn, making a surviving
# WARN unambiguous evidence the guard did not fire.

_UNRELATED = "iterate-2026-08-01-someone-elses-run"


@pytest.fixture
def would_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub S9/S10's git reads to the exact state both checks WARN on."""
    monkeypatch.setattr(sc, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(sc, "_is_ui_facing_iterate", lambda root: True)
    monkeypatch.setattr(sc, "_readme_touched_recently", lambda root: False)
    monkeypatch.setattr(sc, "_new_top_level_dirs", lambda root: ["brandnewdir"])
    monkeypatch.setattr(sc, "_claude_md_touched_recently", lambda root: False)


_Check = Callable[[Path, str], dict[str, Any]]

_S9_S10 = [
    pytest.param(sc.check_s9_readme_freshness, "S9", id="S9"),
    pytest.param(sc.check_s10_claude_md_sync, "S10", id="S10"),
]


_SEAM_ENV = ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID", "SHIPWRIGHT_RUN_ID")


@pytest.mark.parametrize("session_id", ["unknown", "d269d6e9-14a6-4c50-b77c"])
def test_the_stop_audit_seam_hands_these_checks_an_unresolvable_run_id(
    proj: Path, would_warn: None, monkeypatch: pytest.MonkeyPatch,
    session_id: str,
) -> None:
    """Pin the CONSEQUENCE, so it is falsifiable rather than assumed.

    The only production caller is the phase-quality Stop audit, whose run_id
    comes from ``pq.resolve_run_id``. That chain (run_config ``run_id`` → a
    ``run_started`` event → SHIPWRIGHT_LOOP_ID → the session id) never yields
    the canonical ``iterate-YYYY-MM-DD-slug`` an iterate_history entry is keyed
    by, so post-guard S9/S10 SKIP on EVERY real invocation.

    The parameters are the two values the hook can actually pass: it coerces a
    blank env var to ``"unknown"`` before calling
    (``audit_phase_quality_on_stop.py``), so ``""`` is NOT a reachable input and
    testing it would pin a branch production never takes. The asserted invariant
    is therefore ``has_exact_iterate_entry`` — the thing the guard keys on —
    rather than ``is_sentinel_run``, which holds for only one of the two.
    """
    for var in _SEAM_ENV:
        monkeypatch.delenv(var, raising=False)
    _history(proj, [{"run_id": _UNRELATED, "type": "feature",
                     "complexity": "medium"}])

    resolved = pq.resolve_run_id(proj, session_id=session_id)

    assert resolved != _UNRELATED
    assert has_exact_iterate_entry(proj, resolved) is False
    for check in (sc.check_s9_readme_freshness, sc.check_s10_claude_md_sync):
        f = check(proj, resolved)
        assert f["status"] == pq.STATUS_SKIP
        assert "not a resolvable iterate run" in f["evidence"]


def test_the_loop_var_seam_is_the_branch_that_actually_reached_the_backlog(
    proj: Path, would_warn: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reachable NON-sentinel branch — campaign / autonomous-loop runs.

    ``resolve_run_id`` falls through to ``SHIPWRIGHT_LOOP_ID``(+``_UNIT_ID``),
    which campaign mode exports. That id is not an ``iterate_history`` key
    either, so pre-fix S9/S10 inherited an unrelated run's category here too —
    but unlike the sentinel branch the resulting finding is NOT dropped by the
    read-time rollup filter, so it reached the triage backlog and the dashboard.
    This is the branch where the old behaviour was actually actionable, which
    makes it the one that most needs the guard.
    """
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "campaign-alpha")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-3")
    _history(proj, [{"run_id": _UNRELATED, "type": "feature",
                     "complexity": "medium"}])

    resolved = pq.resolve_run_id(proj, session_id="unknown")

    assert resolved == "campaign-alpha-unit-3"
    assert pq.is_sentinel_run(resolved) is False  # survives the rollup filter
    assert has_exact_iterate_entry(proj, resolved) is False
    for check in (sc.check_s9_readme_freshness, sc.check_s10_claude_md_sync):
        assert check(proj, resolved)["status"] == pq.STATUS_SKIP


@pytest.mark.parametrize("check,check_id", _S9_S10)
@pytest.mark.parametrize("sentinel", ["unknown", "UNKNOWN", ""])
def test_s9_s10_skip_on_sentinel_run_id(
    proj: Path, would_warn: None, check: _Check, check_id: str, sentinel: str,
) -> None:
    # The bug: the sentinel tail-fell-back and inherited type=feature from an
    # unrelated run, then WARNed on it. Now it SKIPs.
    _history(proj, [{"run_id": _UNRELATED, "type": "feature",
                     "complexity": "medium"}])
    f = check(proj, sentinel)
    assert f["id"] == check_id
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in f["evidence"]


@pytest.mark.parametrize("check,check_id", _S9_S10)
def test_s9_s10_skip_on_unresolvable_non_sentinel_run_id(
    proj: Path, would_warn: None, check: _Check, check_id: str,
) -> None:
    # The case the read-time rollup filter canNOT catch: a REAL run_id whose
    # F5c entry is not written yet is not a sentinel, so `is_sentinel_run` is
    # False and the bogus WARN would reach the triage backlog.
    mine = "iterate-2026-08-06-entry-not-written-yet"
    assert pq.is_sentinel_run(mine) is False
    _history(proj, [{"run_id": _UNRELATED, "type": "feature",
                     "complexity": "medium"}])
    f = check(proj, mine)
    assert f["id"] == check_id
    assert f["status"] == pq.STATUS_SKIP


@pytest.mark.parametrize("check,check_id", _S9_S10)
def test_s9_s10_exact_entry_still_warns(
    proj: Path, would_warn: None, check: _Check, check_id: str,
) -> None:
    # The guard must not over-fire: a real run with its own entry keeps the
    # genuine WARN. This is what makes the SKIPs above meaningful.
    _history(proj, [{"run_id": "real", "type": "feature", "complexity": "medium"}])
    f = check(proj, "real")
    assert f["id"] == check_id
    assert f["status"] == pq.STATUS_WARN


@pytest.mark.parametrize("check", [c.values[0] for c in _S9_S10], ids=["S9", "S10"])
def test_s9_s10_verdict_no_longer_follows_an_unrelated_runs_category(
    proj: Path, would_warn: None, check: _Check,
) -> None:
    # The decisive property. Pre-fix, flipping ONLY the unrelated run's
    # category flipped this run's verdict (feature → WARN, chore → SKIP) on
    # otherwise identical state. The verdict must not depend on it at all.
    verdicts = []
    for category in ("feature", "chore"):
        _history(proj, [{"run_id": _UNRELATED, "type": category,
                         "complexity": "medium"}])
        verdicts.append(check(proj, "unknown")["status"])
    assert verdicts == [pq.STATUS_SKIP, pq.STATUS_SKIP]


@pytest.mark.parametrize("check", [c.values[0] for c in _S9_S10], ids=["S9", "S10"])
def test_work_tree_guard_still_precedes_the_run_id_guard(
    proj: Path, monkeypatch: pytest.MonkeyPatch, check: _Check,
) -> None:
    # Both guards SKIP, so only the evidence distinguishes them. A git fault
    # must keep reporting the git fault rather than being masked by the new
    # run_id guard, which would misdiagnose a wedged repo as an audit-context
    # mismatch.
    monkeypatch.setattr(sc, "git_context", lambda root: "git_error")
    _history(proj, [{"run_id": _UNRELATED, "type": "feature",
                     "complexity": "medium"}])
    f = check(proj, "unknown")
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" not in f["evidence"]
    assert "wedged" in f["evidence"] or "safe.directory" in f["evidence"]
