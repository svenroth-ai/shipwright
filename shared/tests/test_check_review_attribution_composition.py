"""Real-git composition test for ``check_review_attribution.py`` across two
sequential merges (campaign-dag-scheduler R5b, ``sub-iterates/R5b-merge-lane.md``).

Split out of ``test_check_review_attribution_invalidate.py`` when it crossed
the 300-line guideline (round 2) — the staleness-cascade pair (negative/
positive) stays there; this file covers only the spec's own required
integration test: "a real-git composition test across two sequential merges,
asserting shipped_head/PR-identity checks at merge time." (External review,
glm + openai: flagged as missing entirely from the original file's first
draft.)

No ``gh`` calls (this repo's test style avoids a live GitHub dependency for
pure-git composition — see ``test_campaign_serial_composition_integration.py``'s
own ``git push origin iterate/s1:main`` idiom, reused here): a "PR merge" is
simulated as pushing the unit's branch onto ``main`` directly, which is
exactly what ``gh pr merge --squash`` does from the git object model's own
point of view.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from lib.review_attribution import pin, ship, verify

# Mirrors test_check_review_attribution.py's own load-by-path convention:
# `shared/scripts/checks/` is not a package on sys.path, so the CLI module is
# loaded directly from its file rather than imported by dotted name.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_review_attribution.py"
_spec = importlib.util.spec_from_file_location("check_review_attribution_composition_for_test", _CLI)
assert _spec is not None and _spec.loader is not None
cra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cra)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _write_loop_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "r5b-test", "kind": "sub_iterate", "units": units}),
                     encoding="utf-8")


def _commit_file(repo: Path, name: str, content: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"write {name}")
    return _git(repo, "rev-parse", "HEAD")


class TestTwoSequentialMergesComposition:
    """The spec's own required integration test (R5b-merge-lane.md, Test
    strategy): "a real-git composition test across two sequential merges,
    asserting shipped_head/PR-identity checks at merge time." (External
    review, glm + openai: flagged as missing entirely from this file's first
    draft, which covered only the staleness-cascade pair.)
    """

    def test_shipped_head_and_pr_identity_survive_two_sequential_merges(self, git_origin_repo):
        work, origin = git_origin_repo

        # --- Unit A: pin, ship (simulating 3f-bis's reviews.json commit),
        # verify at merge time, then land on main (the "PR merge"). ---
        _git(work, "checkout", "-b", "iterate/unit-a", "main")
        _commit_file(work, "a.txt", "v1\n")
        state_path = work / ".shipwright" / "loop_state.json"
        _write_loop_state(state_path, [
            {"id": "A", "branch": "iterate/unit-a", "worktree": str(work), "attempt": 0},
            {"id": "B", "branch": "iterate/unit-b", "worktree": str(work), "attempt": 0},
        ])
        pinned_a = pin(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                       loop_id="r5b-test", default_branch="main",
                       pr_node_id="PR_NODE_A", pr_head_ref="iterate/unit-a", pr_base_ref="main")
        _commit_file(work, ".shipwright/planning/iterate/run-a/reviews.json", '{"self":"completed"}\n')
        shipped_a = _git(work, "rev-parse", "HEAD")
        ship(state_path, "A", project_root=str(work), campaign_worktree=str(work),
             loop_id="r5b-test", shipped_head=shipped_a)

        # Merge-time checks, mirroring 3g's own order: shipped_head first,
        # then the PR-identity fields the new pre-merge check (campaign-mode.md
        # 3g, R5b) compares against a fresh `gh pr view`.
        verified_a = verify(state_path, "A", project_root=str(work), campaign_worktree=str(work),
                            loop_id="r5b-test", against="shipped_head")
        assert verified_a["ok"] is True
        assert verified_a["pin"]["pr_node_id"] == "PR_NODE_A"
        assert verified_a["pin"]["pr_head_ref"] == "iterate/unit-a"
        assert verified_a["pin"]["pr_base_ref"] == "main"
        assert verified_a["pin"]["shipped_head"] == shipped_a

        # "PR merge" — push A's branch onto main directly (git-object-model
        # equivalent of `gh pr merge --squash`), without ever advancing the
        # local `main` ref this worktree happens to have checked out.
        _git(work, "push", "origin", "iterate/unit-a:main")

        # --- Unit B: branches off the FRESH remote main (containing A's
        # merge), goes through the identical pin/ship/verify cycle, and its
        # own merge-time checks must be unaffected by A's unrelated merge. ---
        _git(work, "fetch", "origin")
        _git(work, "checkout", "-b", "iterate/unit-b", "origin/main")
        composed = (work / "a.txt").read_text(encoding="utf-8")
        assert composed == "v1\n", "B must compose on top of A's merge"
        _commit_file(work, "b.txt", "v1\n")
        pinned_b = pin(state_path, "B", project_root=str(work), campaign_worktree=str(work),
                       loop_id="r5b-test", default_branch="main",
                       pr_node_id="PR_NODE_B", pr_head_ref="iterate/unit-b", pr_base_ref="main")
        _commit_file(work, ".shipwright/planning/iterate/run-b/reviews.json", '{"self":"completed"}\n')
        shipped_b = _git(work, "rev-parse", "HEAD")
        ship(state_path, "B", project_root=str(work), campaign_worktree=str(work),
             loop_id="r5b-test", shipped_head=shipped_b)

        verified_b = verify(state_path, "B", project_root=str(work), campaign_worktree=str(work),
                            loop_id="r5b-test", against="shipped_head")
        assert verified_b["ok"] is True, (
            "A's unrelated merge to main must not affect B's own shipped_head "
            "verification at B's own merge time"
        )
        assert verified_b["pin"]["pr_node_id"] == "PR_NODE_B"
        assert verified_b["pin"]["pr_head_ref"] == "iterate/unit-b"
        assert verified_b["pin"]["pr_base_ref"] == "main"
        assert pinned_a["pr_node_id"] != pinned_b["pr_node_id"], (
            "sanity: the two units' PR identities must never be conflated"
        )
