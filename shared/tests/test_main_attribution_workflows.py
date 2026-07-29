"""The workflow-side invariants of the `main` self-heal.

@FR-01.19

Parsed YAML, never string matching — a comment mentioning `cancel-in-progress`
must not be able to satisfy a test about the setting.

Three things are pinned here, and each of them silently un-does the whole
feature if it drifts back:

* **AC-1** — on `main` every commit gets its own concurrency group and nothing
  is cancelled. Per-commit is not a nicety: a shared group with cancelling off
  QUEUES the merges instead of cancelling them, which trades a correctness bug
  for a throughput one.
* **AC-2** — the bloat check runs on merges at all, and its base ref is guarded
  against the shapes `github.event.before` really takes.
* **AC-6** — the repair-safety gate exists, is conditional on the same grammar
  the claim matcher uses, blocks rather than warns, and — the part that makes it
  an enforcement boundary — runs the checker from the pull request's BASE
  revision instead of from the branch under judgement.

Plus the registry-driven SSoT rule from the iterate skill's Step 6: the
monitored-workflow policy in code and the workflow files on disk are checked in
**both** directions, because a policy naming a workflow that no longer runs on
`main` would make ordinary commits look permanently unverified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

yaml = pytest.importorskip("yaml")

from lib import main_health as mh  # noqa: E402
from lib import main_health_diagnosis as dx  # noqa: E402

WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    # PyYAML resolves a bare `on:` key to the boolean True (the "Norway
    # problem"), so accept both spellings rather than silently finding nothing.
    return doc.get("on") or doc.get(True) or {}


# --------------------------------------------------------------------------
# AC-1 — every commit on main is verified, and verified in parallel
# --------------------------------------------------------------------------

@pytest.mark.parametrize("workflow", ["ci.yml", "security.yml"])
def test_main_runs_are_never_cancelled(workflow):
    concurrency = _load(workflow)["concurrency"]
    assert "refs/heads/main" in str(concurrency["cancel-in-progress"]), (
        "cancel-in-progress must be conditional on the ref: cancelling on `main` "
        "leaves intermediate commits unverified and makes attribution guesswork"
    )
    assert "!=" in str(concurrency["cancel-in-progress"]), (
        "the condition must DISABLE cancelling on main, not enable it"
    )


@pytest.mark.parametrize("workflow", ["ci.yml", "security.yml"])
def test_main_runs_get_their_own_group_so_they_do_not_queue(workflow):
    group = str(_load(workflow)["concurrency"]["group"])
    assert "github.sha" in group, (
        "on `main` the concurrency group must be per-commit; a shared group with "
        "cancelling off serialises every merge behind the previous one"
    )
    assert "github.ref" in group, "pull requests must still group per ref"


# --------------------------------------------------------------------------
# AC-2 — the coverage gap
# --------------------------------------------------------------------------

def test_bloat_check_runs_on_merges_to_main():
    triggers = _triggers(_load("bloat-check.yml"))
    assert "push" in triggers, (
        "a file that crosses its baseline only when two PRs combine is invisible "
        "without a push trigger"
    )
    assert triggers["push"]["branches"] == ["main"]


def test_bloat_check_still_only_comments_on_pull_requests():
    steps = _load("bloat-check.yml")["jobs"]["bloat-check"]["steps"]
    comment = next(s for s in steps if "comment" in (s.get("name") or "").lower())
    assert "pull_request" in str(comment["if"])


def test_bloat_check_guards_every_shape_its_base_ref_can_take():
    steps = _load("bloat-check.yml")["jobs"]["bloat-check"]["steps"]
    resolve = next(s for s in steps if s.get("id") == "base")
    body = resolve["run"]
    assert "github.event.before" in body, "a push has no pull_request base"
    assert "0000000000000000000000000000000000000000" in body, (
        "the all-zero SHA is a real value here and is not a commit"
    )
    assert "cat-file -e" in body, "an unresolvable base must be detected, not diffed"


# --------------------------------------------------------------------------
# AC-6 — the safety gate is a gate
# --------------------------------------------------------------------------

def _repair_gate_step() -> dict:
    steps = _load("ci.yml")["jobs"]["python-checks"]["steps"]
    return next(s for s in steps if "Repair-PR safety" in (s.get("name") or ""))


def test_the_repair_gate_exists_and_blocks():
    step = _repair_gate_step()
    assert "continue-on-error" not in step, "a gate that cannot fail is not a gate"
    assert "check_repair_safety.py" in step["run"]


def test_the_repair_gate_fires_on_the_same_grammar_the_claim_matcher_uses():
    """One declaration, two consumers. If they drift, a PR can claim a repair
    and never be gated for it."""
    condition = str(_repair_gate_step()["if"])
    assert "fix-main-" in condition
    assert dx.REPAIR_BRANCH_RE.search("iterate/fix-main-3ed41047c2f4")
    assert dx.REPAIR_BRANCH_RE.search("fix-main-3ed41047c2f4")
    assert not dx.REPAIR_BRANCH_RE.search("iterate/some-other-work")


def test_the_repair_gate_runs_the_checker_from_the_base_not_from_the_branch():
    """The enforcement boundary. Judging a repair with the checker that same
    repair just edited is not enforcement — and it fails exactly when it
    matters."""
    body = _repair_gate_step()["run"]
    assert "git show \"$base:shared/scripts/tools/check_repair_safety.py\"" in body
    assert "git show \"$base:shared/scripts/lib/assertion_weakening.py\"" in body
    assert "pull_request.base.sha" in body
    assert "shared/scripts/tools/check_repair_safety.py --project-root" not in body, (
        "the checked-out copy must never be the one that runs"
    )


def test_the_repair_gate_fails_closed_on_a_shell_error():
    assert "set -euo pipefail" in _repair_gate_step()["run"]


# --------------------------------------------------------------------------
# the monitored-workflow policy, checked in both directions
# --------------------------------------------------------------------------

def test_every_monitored_workflow_resolves_to_a_real_file_with_that_name():
    for wf in mh.MONITORED_WORKFLOWS:
        path = WORKFLOWS / wf.file
        assert path.is_file(), f"{wf.file} is in the policy but not on disk"
        assert _load(wf.file)["name"] == wf.name, (
            f"{wf.file} is named {_load(wf.file)['name']!r}, policy says "
            f"{wf.name!r} — `gh run list` reports the display name, so a rename "
            "makes every run invisible to the health check"
        )


def test_every_monitored_workflow_actually_runs_on_pushes_to_main():
    for wf in mh.MONITORED_WORKFLOWS:
        triggers = _triggers(_load(wf.file))
        assert "push" in triggers, (
            f"{wf.file} is monitored but never runs on a merge — every commit "
            "would look permanently unverified"
        )
        assert "main" in (triggers["push"] or {}).get("branches", [])
        assert "paths" not in (triggers["push"] or {}), (
            f"{wf.file} is path-filtered, so 'no run' would not mean 'not yet'"
        )


#: Workflows that run on push-to-main and are deliberately NOT health signals.
#: Named here rather than omitted, so adding a workflow forces a decision.
DELIBERATELY_UNMONITORED: frozenset[str] = frozenset()


def test_no_push_to_main_workflow_is_silently_left_out_of_the_policy():
    monitored = {w.file for w in mh.MONITORED_WORKFLOWS}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        triggers = _triggers(_load(path.name))
        push = triggers.get("push") or {}
        if "main" not in (push.get("branches") or []):
            continue
        assert path.name in monitored | DELIBERATELY_UNMONITORED, (
            f"{path.name} runs on every merge to main but is neither monitored "
            "nor listed as deliberately unmonitored — decide which, so a new "
            "gate cannot go red on `main` with nobody watching"
        )
