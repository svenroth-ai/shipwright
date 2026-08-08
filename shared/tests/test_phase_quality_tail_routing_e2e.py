"""E2E: the project-wide tail (aggregates + triage backlog) after D1.

Split out of ``test_phase_quality_stop_hook_reachability_e2e.py`` (300-LOC
guideline) — that file proves the per-phase redirect itself (trg-b36fd844);
this file proves the project-wide tail's split anchoring (doubt-review D1
and its code-review follow-up): ``regenerate_all_aggregates`` must follow
``audit_root`` (a pure per-tree render, no cross-tree hazard) while
``emit_phase_quality_backlog`` must stay at ``plain_root`` (the one call with
real triage-routing/dismiss hazard). Both need a real ``origin`` remote and a
literal ``main`` branch to exercise ``triage.should_route_to_outbox``
faithfully — a synthetic no-origin repo makes it return ``False`` for every
tree, which would hide exactly the routing distinction this file is about.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from lib import phase_quality as pq  # noqa: E402

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "hooks" / "audit_phase_quality_on_stop.py"
)


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


def _init_main_with_origin(main_root: Path) -> None:
    """A real ``origin`` remote + a literal ``main`` branch, so ``triage.
    should_route_to_outbox`` behaves exactly as it does in production (it
    requires BOTH: an ``origin`` remote configured — ``get-url`` only checks
    config, never reachability — and ``current_branch == default_branch``,
    which falls back to the literal string ``"main"`` with no ``origin/HEAD``
    symref). Without this, a synthetic no-origin test repo makes
    ``should_route_to_outbox`` return ``False`` for EVERY tree, and the
    outbox/tracked routing distinction D1 is actually about cannot be
    observed at all."""
    main_root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(main_root), check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://example.invalid/fake.git"],
                    cwd=str(main_root), check=True)


def test_aggregate_report_regenerates_at_the_audited_worktree(tmp_path: Path):
    """Code-review follow-up to D1: `regenerate_all_aggregates` is a PURE
    render of one tree's own findings — no cross-tree/triage hazard — so it
    must follow `audit_root`, not `plain_root`-only. The over-broad first
    version of the D1 fix anchored ALL three tail calls at `plain_root`,
    which meant findings written to the worktree (the whole point of
    trg-b36fd844's fix) were never rendered into ANY dashboard/report and
    vanished, unread, when the worktree was pruned — an observability
    regression code-review caught. Proven by checking the report exists
    WHERE the findings do. It ALSO renders at `plain_root` (code review,
    delta pass) so main's own dashboard keeps refreshing during a
    redirected run instead of going dark for its duration — proven by
    checking main gets a render too, not by its absence."""
    from lib.worktree_isolation import write_run_pointer

    main_root = tmp_path / "main"
    _init_main_with_origin(main_root)
    (main_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(main_root), check=True)

    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "iterate/demo", str(worktree)],
        cwd=str(main_root), check=True,
    )
    (worktree / ".shipwright" / "agent_docs").mkdir(parents=True)
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    write_run_pointer(
        main_root, run_id="iterate-2026-08-01-demo", slug="demo",
        branch="iterate/demo", worktree_path=worktree, session_id="sess-tail",
    )

    r1 = _run_hook(main_root, session_id="sess-tail")
    assert r1.returncode == 0, r1.stderr

    # Per-phase findings land in the AUDITED tree (the worktree)...
    assert any((worktree / pq.FINDING_DIR).glob("*.json"))
    # ...and so does their render — the tail follows them, not plain_root-only.
    assert (worktree / pq.REPORT_PATH).exists()
    # ...and main's OWN dashboard also refreshes (its own, separate render —
    # main has no findings of its own here, so this proves the call ran, not
    # that it copied the worktree's report).
    assert (main_root / pq.REPORT_PATH).exists()


def test_triage_backlog_write_stays_at_main_never_the_pointer_worktree(tmp_path: Path):
    """Doubt-review D1, the actual hazard: `emit_phase_quality_backlog`'s
    `collect_in_scope_fails(project_root)` reads ONLY that root's own
    findings tree — so calling it at `plain_root` (main, which never
    receives this run's writes) means a redirected run's own FAILs can
    NEVER influence main's backlog, correct either way (no new item, no
    wrong dismissal). The actual corruption vector this guards against is
    calling it at `audit_root` instead: `should_route_to_outbox` would then
    see the WORKTREE's `iterate/*` branch (not idle main) and route straight
    into the TRACKED `.shipwright/triage.jsonl`, shipping a write into this
    run's own PR. Proven two ways: (1) `collect_in_scope_fails` genuinely
    sees the FAIL at `audit_root` but NOT at `plain_root` — confirming the
    two roots are not equivalent, so which one is used is load-bearing; (2)
    no triage file of either kind appears under the WORKTREE after a real
    run — the corruption vector never fires."""
    from lib.worktree_isolation import write_run_pointer

    main_root = tmp_path / "main"
    _init_main_with_origin(main_root)
    (main_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(main_root), check=True)

    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "iterate/demo", str(worktree)],
        cwd=str(main_root), check=True,
    )
    (worktree / ".shipwright" / "agent_docs").mkdir(parents=True)
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-2026-08-01-demo"}),
        encoding="utf-8",
    )
    write_run_pointer(
        main_root, run_id="iterate-2026-08-01-demo", slug="demo",
        branch="iterate/demo", worktree_path=worktree, session_id="sess-route",
    )

    # First Stop: S2 provisional SKIP (no ledger entry yet) — no FAIL, nothing
    # for the backlog to emit yet.
    r1 = _run_hook(main_root, session_id="sess-route")
    assert r1.returncode == 0, r1.stderr
    first = _iterate_finding(worktree)
    assert _s2(first)["status"] == pq.STATUS_SKIP

    claim = main_root / ".shipwright" / ".cache" / "stop-phasequality-sess-route.claim"
    if claim.exists():
        old = time.time() - 120
        os.utime(claim, (old, old))

    # F5c writes the ledger entry mid-run — simulated directly, same as the
    # sibling reachability test.
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "run_id": "iterate-2026-08-01-demo",
            "iterate_history": [{"run_id": "iterate-2026-08-01-demo", "complexity": "medium"}],
        }),
        encoding="utf-8",
    )

    # Second Stop: S2 now FAILs for real (no spec file on disk at medium
    # complexity) — a genuine Tier-1 FAIL for the backlog tail to act on.
    r2 = _run_hook(main_root, session_id="sess-route")
    assert r2.returncode == 0, r2.stderr
    second = _iterate_finding(worktree)
    assert _s2(second)["status"] == pq.STATUS_FAIL

    # (1) The two roots are NOT equivalent — audit_root sees the FAIL,
    # plain_root does not — so which one the tail actually uses is
    # load-bearing, not incidental.
    assert any(f["phase"] == "iterate" for f in pq.collect_in_scope_fails(worktree))
    assert not any(f["phase"] == "iterate" for f in pq.collect_in_scope_fails(main_root))

    # (2) The corruption vector — a write landing in the WORKTREE's own
    # tracked triage.jsonl, which would ship in this run's PR — never fires.
    assert not (worktree / ".shipwright" / "triage.jsonl").exists()
    assert not (worktree / ".shipwright" / "triage.outbox.jsonl").exists()
