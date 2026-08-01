"""Where the spec-impact gate's range view stops being able to answer.

Sibling of `test_spec_impact_branch_range.py`, which proves the conversion works.
This one pins what it does at the edges: the two conditions under which it must
SKIP rather than accuse, the one empty answer it must still treat as a FAIL, and
the one case where the widening is genuinely fail-OPEN and we accept it.

That last one matters, and it is why this module exists rather than more rows in
the sibling. The four gates #503 converted use the changed set as a violation
TRIGGER — widening can only find MORE, so it is fail-safe. This gate uses it as
evidence of COMPLIANCE — widening can only fail LESS. "Same class as the siblings"
is true about the blindness and false about the risk, so the fail-open direction
gets its own pinned test instead of an assumption.

Helpers are imported from the sibling module (the convention `test_integrate_main`
already sets for `_git` / `_write` / `_set_repo_identity`).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from test_spec_impact_branch_range import (  # noqa: E402
    _RUN_ID,
    _SPEC,
    _build_merge_head,
    _seed_event,
    _seed_run,
)

from tools.verifiers.common import Severity  # noqa: E402
from tools.verifiers.iterate_checks import check_spec_impact_recorded  # noqa: E402


# --- what it does when it cannot see ----------------------------------------

def test_a_diff_the_gate_cannot_obtain_is_SKIPPED_not_failed(
    git_origin_repo, make_worktree,
) -> None:
    """`None` is "I could not see" and must never be reported as a violation.

    A real unresolvable anchor, not a mocked helper: the merge-base fails for every
    trunk candidate AND `git show` fails on the bad ref, which is the genuine
    both-paths-blind condition the resolver folds into `None`.
    """
    wt, _head = _build_merge_head(
        git_origin_repo[0], make_worktree,
        branch_files={_SPEC: "spec\n"},
        main_files={"other.py": "main moved on\n"},
    )
    _seed_run(wt)
    _seed_event(wt, intent="feature", spec_impact="modify")

    result = check_spec_impact_recorded(wt, _RUN_ID, "no-such-ref")

    assert result.is_skipped, f"invented a verdict from an unreadable ref: {result.detail}"
    assert result.ok is True
    # The skip must announce itself as BLIND. A silent skip on an ERROR-severity
    # gate is indistinguishable from a pass, which is how a gate quietly stops
    # gating — see the non-`main` trunk note in the iterate spec.
    assert "BLIND" in result.detail, result.detail


def test_a_merge_head_with_no_corroborated_base_is_SKIPPED_not_failed(tmp_path) -> None:
    """The second correction, and the one that used to be an outright false FAIL.

    No remote here, so only ONE trunk name resolves and `_branch_base_commit` refuses
    an uncorroborated base. The fallback then runs on a merge commit, where
    `git show --name-only` prints NOTHING — the old code got `[]`, read it as
    "touched no spec.md" and FAILED. The resolver folds that blind `[]` into `None`.
    """
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")

    _git(work, "checkout", "-b", "iterate/x")
    _write(work, _SPEC, "spec\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "feat: spec change")

    _git(work, "checkout", "main")
    _write(work, "other.py", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves")

    _git(work, "checkout", "iterate/x")
    _git(work, "merge", "--no-ff", "--no-edit", "main")
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    parents = _git(work, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3, "the fixture must really put a MERGE commit on top"

    _seed_run(work)
    _seed_event(work, intent="feature", spec_impact="modify")

    result = check_spec_impact_recorded(work, _RUN_ID, head)

    assert result.is_skipped, (
        "a merge commit the gate could not resolve a base for was reported as a "
        f"violation rather than skipped: {result.detail}"
    )
    assert result.ok is True


# --- but an empty answer it CAN trust is still a failure ---------------------

def test_an_empty_but_trustworthy_range_still_FAILS(
    git_origin_repo, make_worktree,
) -> None:
    """`None` and `[]` must not collapse into one branch.

    Kills the mutation `if changed is None:` → `if not changed:`, which every other
    test here leaves green — an ERROR gate would silently become a skip. Here the
    range RESOLVES and is genuinely empty, so `[]` is a fact: nothing changed, so no
    spec.md was touched, so FAIL. Only the unresolvable cases above may skip.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "empty-range")
    _git(wt, "commit", "--allow-empty", "-m", "chore: nothing at all")
    head = _git(wt, "rev-parse", "HEAD").stdout.strip()

    _seed_run(wt)
    _seed_event(wt, intent="feature", spec_impact="modify")

    result = check_spec_impact_recorded(wt, _RUN_ID, head)

    assert result.ok is False, (
        f"an empty-but-readable range was treated as unreadable: {result.detail}"
    )
    assert result.severity == Severity.ERROR.value
    assert "0 path(s)" in result.detail, result.detail


# --- the accepted fail-open, pinned so it cannot drift unnoticed -------------

def test_a_spec_md_from_a_FOREIGN_commit_in_the_range_satisfies_the_gate(
    git_origin_repo, make_worktree,
) -> None:
    """ACCEPTED LIMITATION, deliberately pinned — this asserts a WEAKNESS.

    The range is `merge-base(trunk, anchor)..anchor`, so any commit between the
    trunk and the anchor counts, whoever wrote it. Under the supported `stacked`
    campaign strategy (`autonomous_loop.VALID_STRATEGIES`, `branch_base.py:61`) unit
    N branches off unit N-1's UNMERGED branch, so N-1's commits sit inside N's
    range: if N-1 wrote a planning spec.md and N wrote none, N's gate PASSES on
    N-1's file. The single-commit view did not have this hole.

    It is accepted rather than fixed because the alternative — intersecting the
    range with commits carrying this run's `Run-ID:` trailer — would make this gate
    the only one of the five that does so, and every sibling shares the same
    trunk-anchored base. Under `serial` (the default; a worktree forked from freshly
    fetched `origin/main`) the range holds only this unit's work and the hole is
    closed by construction.

    If this test ever FAILS, the behaviour changed: re-read the iterate spec's
    "Accepted limitation" section before making it pass again.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    # Unit N-1: a feature that DID write a planning spec.md, still unmerged.
    prev = make_worktree(work, "unit-n-minus-1")
    _write(prev, _SPEC, "| FR-01.01 | written by the PREVIOUS unit | Must |\n")
    _git(prev, "add", "-A")
    _git(prev, "commit", "-m", "feat: previous unit writes the spec")
    prev_branch = _git(prev, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    # Unit N: stacked on N-1, and it touches no spec.md of its own.
    stacked = work / ".worktrees" / "unit-n"
    _git(work, "worktree", "add", str(stacked), "-b", "iterate/unit-n", prev_branch)
    _write(stacked, "app.py", "unit N changes code only\n")
    _git(stacked, "add", "-A")
    _git(stacked, "commit", "-m", "feat: unit N, no spec change")
    head = _git(stacked, "rev-parse", "HEAD").stdout.strip()

    _seed_run(stacked)
    _seed_event(stacked, intent="feature", spec_impact="modify")

    result = check_spec_impact_recorded(stacked, _RUN_ID, head)

    assert result.ok is True, (
        "behaviour changed — the gate no longer accepts a stacked predecessor's "
        f"spec.md. That is an improvement; update the spec and this test: {result.detail}"
    )
    assert "1 planning spec.md" in result.detail
