"""E2E: the real ``audit_phase_quality_on_stop.py`` subprocess, across Stops.

Split out of ``test_already_audited_unresolvable_staleness.py`` (300-LOC
guideline) — that file keeps the unit-level coverage for
``make_finding``/``unresolvable_run_id_skip`` tagging and ``already_audited``
staleness; this file drives the real Stop hook subprocess end to end (the
shape trg-b36fd844 actually manifested in) so the fix is proven at the seam
it broke, not just at the unit it broke in. The project-wide tail's own
split-anchoring (doubt-review D1) is proven separately in the sibling
``test_phase_quality_tail_routing_e2e.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lib import phase_quality as pq  # noqa: E402

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "hooks" / "audit_phase_quality_on_stop.py"
)


@pytest.fixture
def completed_project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    return tmp_path


def _run_hook(cwd: Path, *, session_id: str = "sess-E2E") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    for k in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID",
              "SHIPWRIGHT_PHASE_QUALITY", "SHIPWRIGHT_PROJECT_ROOT"):
        env.pop(k, None)
    env["CLAUDE_PLUGIN_ROOT"] = str(Path("/fake/plugins/shipwright-iterate"))
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)], input="{}", capture_output=True,
        text=True, cwd=str(cwd), env=env,
    )


def _iterate_finding(cwd: Path) -> dict:
    finding_dir = cwd / pq.FINDING_DIR
    for p in finding_dir.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        if data["phase"] == "iterate":
            return data
    raise AssertionError("no iterate finding written")


def _s2(data: dict) -> dict:
    return next(f for f in data["spec"] if f["id"] == "S2")


def test_second_stop_reaudits_s2_once_the_ledger_entry_appears(completed_project: Path):
    r1 = _run_hook(completed_project)
    assert r1.returncode == 0, r1.stderr
    first = _iterate_finding(completed_project)
    assert _s2(first)["status"] == pq.STATUS_SKIP
    assert _s2(first).get("reason_code") == "unresolvable_run_id"

    # Age the once-per-event claim so the 2nd Stop re-arms instead of losing
    # the fan-out claim outright — mirrors _age_claim in test_audit_phase_quality.py.
    claim = (
        completed_project / ".shipwright" / ".cache" / "stop-phasequality-sess-E2E.claim"
    )
    if claim.exists():
        old = time.time() - 120
        os.utime(claim, (old, old))

    # F5c writes the ledger entry mid-run — simulated directly here.
    (completed_project / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "run_id": "iterate-2026-08-01-demo",
            "iterate_history": [{"run_id": "iterate-2026-08-01-demo", "complexity": "medium"}],
        }),
        encoding="utf-8",
    )

    r2 = _run_hook(completed_project)
    assert r2.returncode == 0, r2.stderr
    second = _iterate_finding(completed_project)
    # No spec file on disk for this run at medium complexity → S2 now FAILs
    # for real, instead of staying frozen at the first Stop's SKIP.
    assert _s2(second)["status"] == pq.STATUS_FAIL
    assert "reason_code" not in _s2(second)


def test_second_stop_reaudits_s2_via_pointer_when_cwd_is_main(tmp_path: Path):
    """Same transition, but with the shape a real Stop subprocess actually
    sees: cwd is MAIN, not the worktree — only a run pointer names where the
    worktree is. The previous test drives the hook with cwd already AT the
    worktree, which external review (round 2) and the internal plan review
    both flagged as unproven: without the pointer-based redirect, resolving
    project_root from cwd roots this audit at main, where F5c's ledger entry
    never lands, and the re-audit this whole module exists for is
    unreachable. This proves the redirect closes that gap."""
    from lib.worktree_isolation import write_run_pointer

    main_root = tmp_path / "main"
    main_root.mkdir()
    # A completed project's config lives at the root of BOTH the main
    # checkout and the worktree in real usage — B1a branches the worktree
    # off `origin/default`, which already carries it (setup_iterate_
    # worktree.py's own precondition). plain_root's greenfield gate (D1 fix)
    # relies on that: it deliberately checks main, not the pointer redirect.
    (main_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(main_root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(main_root), check=True)

    worktree = main_root / ".worktrees" / "demo"
    # A REAL `git worktree add` (not a hand-rolled `.git` marker) so the
    # `.git` gitdir-FILE shape `pointer_worktree_root`'s identity check
    # (`is_worktree_of`) verifies is exactly what git itself produces.
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
        cwd=str(main_root), check=True,
    )
    (worktree / ".shipwright" / "agent_docs").mkdir(parents=True)
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    write_run_pointer(
        main_root, run_id="iterate-2026-08-01-demo", slug="demo",
        branch="iterate/demo", worktree_path=worktree, session_id="sess-E2E",
    )

    r1 = _run_hook(main_root)
    assert r1.returncode == 0, r1.stderr
    first = _iterate_finding(worktree)
    assert _s2(first)["status"] == pq.STATUS_SKIP
    assert _s2(first).get("reason_code") == "unresolvable_run_id"

    # Anchored at main_root (plain_root), not worktree: the once-per-Stop
    # claim deliberately stays off the pointer redirect (D4 fix) so a
    # transient pointer-resolution flake can't split the claim across roots.
    claim = main_root / ".shipwright" / ".cache" / "stop-phasequality-sess-E2E.claim"
    if claim.exists():
        old = time.time() - 120
        os.utime(claim, (old, old))

    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "run_id": "iterate-2026-08-01-demo",
            "iterate_history": [{"run_id": "iterate-2026-08-01-demo", "complexity": "medium"}],
        }),
        encoding="utf-8",
    )

    r2 = _run_hook(main_root)
    assert r2.returncode == 0, r2.stderr
    second = _iterate_finding(worktree)
    assert _s2(second)["status"] == pq.STATUS_FAIL
    assert "reason_code" not in _s2(second)

