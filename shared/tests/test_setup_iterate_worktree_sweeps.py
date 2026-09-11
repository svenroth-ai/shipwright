"""Tests for the step 4.5/4.6/5 sweep trio inside
``shared/scripts/tools/setup_iterate_worktree.py`` (canon self-heal, outbox
sweep, opportunistic FR Layers promotion) and their ORDERING — split out of
``test_setup_iterate_worktree.py`` purely to keep that file under the
file-size guideline; same fixtures, same real-git invocation style."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helpers)
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "tools"))

import _sweep_helpers as sh  # noqa: E402  (real-git seed/outbox plumbing)
import setup_iterate_worktree as siw  # noqa: E402  (the real in-process setup)
from lib.gitignore_canon import read_canonical_rules  # noqa: E402

_GI_CHORE = (
    "chore: scaffold canonical .shipwright/ artifact-ignore block into .gitignore"
)


def _branch_commit_subjects(wt: Path) -> str:
    return sh.git(wt, "log", "--format=%s").stdout


# --------------------------------------------------------------------------- #
# MED-1 (D3 review cascade): the self-heal ↔ sweep STAGED-STATE SEAM.
# Step 4.6 commits .gitignore; step 5 must then still find a CLEAN index and fold
# a NON-EMPTY outbox. If the self-heal left .gitignore staged, the sweep would
# false-skip (staged_changes) and SILENTLY drop delivery. This locks both commits.
# --------------------------------------------------------------------------- #


def test_gitignore_selfheal_then_outbox_sweep_both_commit(git_origin_repo):
    work, _ = git_origin_repo
    sh.set_identity(work)
    # 1. Tracked triage.jsonl (schema header) + union .gitattributes on main, pushed
    #    to origin so the sweep's origin-delivered GC has a base.
    sh.seed_tracked(work, sh.item("trg-seed"))
    # 2. .gitignore present but MISSING the canon .shipwright/ managed block, so the
    #    step-4.6 gitignore self-heal genuinely fires (commits a chore).
    (work / ".gitignore").write_text("node_modules/\n", encoding="utf-8", newline="\n")
    sh.git(work, "add", "--", ".gitignore")
    sh.git(work, "commit", "-m", "user gitignore without canon block")
    sh.git(work, "push", "origin", "main")
    assert not any(r in (work / ".gitignore").read_text(encoding="utf-8")
                   for r in read_canonical_rules()), "canon block must be ABSENT pre-setup"
    # 3. NON-EMPTY main-tree outbox: one valid append line not yet in tracked log.
    sh.write_outbox(work, sh.item("trg-outbox-1", title="from-outbox"))

    # 4. Run the REAL in-process setup (no mocks, real git).
    env_ci = os.environ.get("CI")
    os.environ["CI"] = ""  # interactive session, not CI
    try:
        code, payload = siw.setup(str(work), "seam", "iterate-20260608-seam")
    finally:
        if env_ci is None:
            os.environ.pop("CI", None)
        else:
            os.environ["CI"] = env_ci
    assert code == 0, payload
    wt = Path(payload["project_root"])

    subjects = _branch_commit_subjects(wt)
    # (a) BOTH the gitignore self-heal chore AND the outbox sweep chore landed — the
    #     self-heal did NOT leave .gitignore staged and false-skip the sweep.
    assert _GI_CHORE in subjects, ("gitignore self-heal commit missing\n" + subjects)
    assert "chore(triage): sweep 1 outbox append(s) into branch" in subjects, (
        "outbox sweep commit missing (self-heal may have left .gitignore staged)\n"
        + subjects
    )
    # (b) The worktree is CLEAN afterwards (no staged residue from either step).
    assert sh.git(wt, "status", "--porcelain").stdout.strip() == "", "worktree not clean"
    # (c) The swept outbox line is present in the branch's tracked triage.jsonl.
    branch_lines = sh.branch_triage_lines(wt)
    assert any('"trg-outbox-1"' in ln for ln in branch_lines), (
        "swept outbox line not in branch tracked triage.jsonl: " + repr(branch_lines)
    )


def test_layer_promotion_sweep_is_invoked_and_surfaces_warnings(monkeypatch, git_origin_repo):
    """Wiring seam only (sweep behavior itself is pinned by
    ``test_layer_promotion_sweep.py``/``test_layer_promotion_delivery.py``):
    confirms setup() calls it with THIS worktree + run_id + default branch,
    and that its notes reach the payload the skill reads."""
    work, _ = git_origin_repo
    sh.set_identity(work)
    calls = []

    def _stub(worktree_path, run_id, default_branch):
        calls.append((worktree_path, run_id, default_branch))
        from lib.layer_promotion_sweep import LayerPromotionSweepResult
        return LayerPromotionSweepResult(
            status="delivered", promoted=["FR-01.01"],
            pr_url="https://example.com/pull/1", branch="chore/layer-promotion-abc123def456",
        )

    monkeypatch.setattr(siw, "run_layer_promotion_sweep", _stub)
    code, payload = siw.setup(str(work), "layer-sweep-seam", "iterate-20260911-layer-sweep-seam")
    assert code == 0, payload
    wt = Path(payload["project_root"])
    assert len(calls) == 1
    assert calls[0][:2] == (wt, "iterate-20260911-layer-sweep-seam")
    assert any("opened its own PR promoting" in w and "FR-01.01" in w for w in payload["warnings"])


def test_layer_promotion_sweep_runs_before_selfheal_and_outbox_sweep(monkeypatch, git_origin_repo):
    """Doubt-review finding: ``git push HEAD:refs/heads/<new>`` (inside the
    real sweep's own ``deliver_as_own_pr``) ships full ancestry, not just the
    tip commit — so if a canon self-heal or outbox-sweep commit had already
    landed on this branch by the time the promotion sweep ran, THAT unrelated
    commit would ride along into the promotion's own small PR. Seeds a
    scenario where both the self-heal AND the outbox sweep genuinely fire
    (mirrors ``test_gitignore_selfheal_then_outbox_sweep_both_commit``), then
    asserts the worktree's HEAD has NEITHER commit yet at the moment the
    (stubbed) promotion sweep is invoked."""
    work, _ = git_origin_repo
    sh.set_identity(work)
    sh.seed_tracked(work, sh.item("trg-seed"))
    (work / ".gitignore").write_text("node_modules/\n", encoding="utf-8", newline="\n")
    sh.git(work, "add", "--", ".gitignore")
    sh.git(work, "commit", "-m", "user gitignore without canon block")
    sh.git(work, "push", "origin", "main")
    sh.write_outbox(work, sh.item("trg-outbox-2", title="from-outbox"))

    seen_subjects_at_call_time: list[str] = []

    def _stub(worktree_path, run_id, default_branch):
        seen_subjects_at_call_time.append(_branch_commit_subjects(worktree_path))
        from lib.layer_promotion_sweep import LayerPromotionSweepResult
        return LayerPromotionSweepResult(status="no_change")

    monkeypatch.setattr(siw, "run_layer_promotion_sweep", _stub)
    code, payload = siw.setup(str(work), "layer-sweep-order", "iterate-20260911-layer-sweep-order")
    assert code == 0, payload

    assert len(seen_subjects_at_call_time) == 1
    subjects_at_sweep_time = seen_subjects_at_call_time[0]
    assert _GI_CHORE not in subjects_at_sweep_time, (
        "gitignore self-heal already landed BEFORE the layer-promotion sweep ran — "
        "a real promotion would have pushed that unrelated commit into its own PR\n"
        + subjects_at_sweep_time
    )
    assert "chore(triage): sweep" not in subjects_at_sweep_time, (
        "outbox sweep already landed BEFORE the layer-promotion sweep ran — "
        "a real promotion would have pushed that unrelated commit into its own PR\n"
        + subjects_at_sweep_time
    )

    # ...but both DO land, afterward, exactly as the pre-existing behavior test pins.
    wt = Path(payload["project_root"])
    final_subjects = _branch_commit_subjects(wt)
    assert _GI_CHORE in final_subjects
    assert "chore(triage): sweep 1 outbox append(s) into branch" in final_subjects
