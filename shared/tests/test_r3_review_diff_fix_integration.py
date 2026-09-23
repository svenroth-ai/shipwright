"""Integration test (``category: "integration"``): R3's review-attribution
guard driven through the actual pin -> commit -> verify sequence 3f-bis/3g
use, and the shared-worktree fallback under alternating units — the
``cross_component`` risk flag `diff_risk_recheck.py` raises for this diff
(``campaign-mode.md`` is a "campaign drain" file) requires this composition
be proven, not just each function in isolation
(``shared/tests/test_review_attribution.py`` already covers those).

Lives under ``shared/tests`` (one-test-root-per-process rule), mirroring
``test_r2_worktree_capability_integration.py``'s own placement rationale.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_review_attribution.py"

_spec = importlib.util.spec_from_file_location("check_review_attribution_for_r3_it", _CLI)
assert _spec is not None and _spec.loader is not None
check_review_attribution = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_review_attribution)


def _write_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "r3-it", "units": units}), encoding="utf-8")


def _commit(repo: Path, name: str, msg: str) -> str:
    import subprocess
    (repo / name).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", msg], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()


def _checkout(repo: Path, branch: str, create: bool = False) -> None:
    import subprocess
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(branch)
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_pin_then_shipped_head_verify_across_the_real_3fbis_3g_sequence(git_origin_repo, capsys):
    """Mirrors 3f-bis (pin, then the reviews.json commit) followed by 3g's
    merge-time check (verify --against shipped_head) — the exact ordering
    the external plan review (openai, high) asked to see proven end to end,
    not just asserted in prose."""
    work, _ = git_origin_repo
    _checkout(work, "iterate/campaign-r3--U1", create=True)
    _commit(work, "feature.txt", "feat: unit work")
    state = work / ".shipwright" / "loop_state.json"
    _write_state(state, [{"id": "U1", "branch": "iterate/campaign-r3--U1", "attempt": 0}])

    rc = check_review_attribution.main([
        "--mode", "pin", "--state", str(state), "--unit-id", "U1",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "r3-it", "--pr-node-id", "PR_1", "--pr-head-ref", "iterate/campaign-r3--U1",
        "--pr-base-ref", "main",
    ])
    assert rc == 0
    capsys.readouterr()

    # 3f-bis's own reviews.json commit/push, which moves HEAD past the pin,
    # followed by the --mode ship call that records the pushed SHA (R3
    # doubt-round, high — without this call, shipped_head stays null and
    # verify --against shipped_head refuses to ALLOW).
    shipped_head = _commit(work, "reviews.json", "chore: record review pass for U1")

    rc = check_review_attribution.main([
        "--mode", "ship", "--state", str(state), "--unit-id", "U1",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "r3-it", "--shipped-head", shipped_head,
    ])
    assert rc == 0
    capsys.readouterr()

    rc = check_review_attribution.main([
        "--mode", "verify", "--state", str(state), "--unit-id", "U1",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "r3-it", "--against", "shipped_head", "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "allow"


def test_alternating_units_on_the_shared_worktree_never_cross_attribute(git_origin_repo):
    """Pre-R5a fallback: neither unit's row carries a `worktree` field, so
    both resolve to the SAME shared campaign worktree. Attempting to pin one
    unit while the OTHER's branch is checked out must fail closed — this is
    the exact "unit A captures unit B's checkout state" scenario the
    external plan review (glm, high; openai, medium) asked to see actually
    exercised, not just argued from the code."""
    work, _ = git_origin_repo
    _checkout(work, "iterate/campaign-r3--P", create=True)
    _commit(work, "p.txt", "feat: unit P work")
    _checkout(work, "iterate/campaign-r3--Q", create=True)
    _commit(work, "q.txt", "feat: unit Q work")

    state = work / ".shipwright" / "loop_state.json"
    _write_state(state, [
        {"id": "P", "branch": "iterate/campaign-r3--P", "attempt": 0},
        {"id": "Q", "branch": "iterate/campaign-r3--Q", "attempt": 0},
    ])

    # Q is currently checked out (from the branch creation above). Pinning P
    # against the shared worktree while Q's branch is live must be refused.
    rc = check_review_attribution.main([
        "--mode", "pin", "--state", str(state), "--unit-id", "P",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "r3-it",
    ])
    assert rc == 1

    # Switching to P's own branch first (the real orchestrator's serial
    # execution model) lets P pin cleanly, and Q's pin from a moment ago
    # never happened -- there is no stale/cross-attributed pin for Q either.
    _checkout(work, "iterate/campaign-r3--P")
    rc = check_review_attribution.main([
        "--mode", "pin", "--state", str(state), "--unit-id", "P",
        "--project-root", str(work), "--campaign-worktree", str(work),
        "--loop-id", "r3-it",
    ])
    assert rc == 0
    assert not (work / ".shipwright" / "runs" / "r3-it" / "Q").exists()
