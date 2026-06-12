"""`iterate_checks.check_integration_coverage` — the non-dodgeable F11 gate for
the `cross_component` risk flag (iterate-2026-06-12-cross-component-gate).

A medium+ iterate that touches FRAMEWORK cross-component machinery (merge/churn
resolver, hooks + hook fan-out, pipeline validators, campaign drain) MUST carry an
INTEGRATION-coverage behavior (`category: "integration"`) in the Test Completeness
Ledger — a real-scenario test proving the components compose. The gate RECOMPUTES
`cross_component` from the actual diff (merge-base..HEAD), NOT from any
agent-reported flag, so it cannot be dodged by omitting a self-report.

Real-git via the `git_origin_repo` / `make_worktree` fixtures + helpers from
`test_integrate_main`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402

_RUN = "iterate-xc"


def _seed_entry(wt: Path, complexity: str) -> None:
    _write(wt, f".shipwright/agent_docs/iterates/{_RUN}.json",
           json.dumps({"run_id": _RUN, "complexity": complexity, "type": "change"}))


def _seed_ledger(wt: Path, behaviors: list[dict]) -> None:
    _write(wt, "shipwright_test_results.json",
           json.dumps({"iterate_latest": {"run_id": _RUN,
                       "test_completeness": {"status": "complete", "behaviors": behaviors}}}))


def _commit_change(wt: Path, path: str, msg: str) -> str:
    _write(wt, path, "x\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", msg)
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


def test_fails_when_cross_component_touched_without_integration_behavior(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-fail")
    commit = _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    _seed_entry(wt, "medium")
    _seed_ledger(wt, [{"behavior": "some unit thing", "disposition": "tested",
                       "evidence": "test_x", "category": "unit"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False, res
    assert "integration" in res.detail.lower()


def test_ok_when_integration_behavior_present(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-ok")
    commit = _commit_change(wt, "plugins/x/hooks/hooks.json", "touch hook fan-out")
    _seed_entry(wt, "medium")
    _seed_ledger(wt, [
        {"behavior": "components compose end-to-end", "disposition": "tested",
         "evidence": "test_parallel_merge_cascade_integration.py", "category": "integration"},
    ])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is True, res


def test_ok_when_change_is_not_cross_component(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-noncomp")
    commit = _commit_change(wt, "src/app/routes/courses/page.tsx", "ordinary route")
    _seed_entry(wt, "medium")
    _seed_ledger(wt, [{"behavior": "route renders", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is True, res  # no cross-component machinery → no integration requirement


def test_skipped_at_small_complexity(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-small")
    commit = _commit_change(wt, "shared/scripts/lib/churn_merge.py", "touch churn resolver")
    _seed_entry(wt, "small")  # below the medium floor
    _seed_ledger(wt, [{"behavior": "x", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is True and res.severity == "skipped", res


def test_corrupt_results_json_is_distinct_failure(git_origin_repo, make_worktree):
    # A cross-component diff with an UNREADABLE results.json must fail with a
    # DISTINCT "corrupt" reason, not be misreported as "missing integration
    # coverage" (external-review fix).
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-corrupt")
    commit = _commit_change(wt, "shared/scripts/tools/ensure_current.py", "touch resolver")
    _seed_entry(wt, "medium")
    _write(wt, "shipwright_test_results.json", "{ this is not json")

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False
    assert "corrupt" in res.detail.lower() or "unreadable" in res.detail.lower()


def test_recomputes_from_diff_not_self_report(git_origin_repo, make_worktree):
    # The ledger carries NO risk_flags field at all — the gate must still fire from
    # the diff alone (the anti-dodge property).
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-recompute")
    commit = _commit_change(wt, "shared/scripts/tools/verify_phase.py", "touch pipeline validator")
    _seed_entry(wt, "large")
    _seed_ledger(wt, [{"behavior": "unit only", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False, res
