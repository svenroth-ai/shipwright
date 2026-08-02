"""`check_integration_coverage` — WHERE the ledger comes from, and whose it is.

Split from ``test_check_integration_coverage.py`` (300-line file limit); that
module owns "the diff decides, at every complexity", this one owns the ledger
lookup order and its attribution.

The gate prefers the PER-RUN F5c entry and falls back to the shared
``shipwright_test_results.json``. Both halves matter:

* the per-run preference exists because F11 restores the shared file to HEAD on a
  branch behind main, so a run WITH integration coverage would be failed for
  lacking it (iterate-2026-07-27-derived-snapshots-off-branch);
* the fallback must be ATTRIBUTED, because that same restore means an
  unattributed read sees the PREVIOUS run's block — and a cross-component change
  would pass green on someone else's integration test
  (iterate-2026-08-01-coverage-gate-recompute-order, Stage-3 doubt review).

Three siblings guard the same file with ``read_iterate_latest(...).is_current``:
``check_test_completeness_ledger``, ``check_surface_verification`` and the
silent-revert declarations. This gate now does too.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("complexity", ("trivial", "small"))
def test_the_cheap_remedy_actually_works_below_medium(complexity, git_origin_repo, make_worktree):
    """The remedy text promises that recording the behavior in THIS run's F5c entry
    clears the gate at any tier — including `trivial`, where the Test Completeness
    Ledger is otherwise auto-`n/a`. Pinned because an earlier draft of that text
    claimed escalation to `medium` was the ONLY route, which would have sent a
    trivial run to buy a spec, mini-plan, approval gate and external plan review it
    did not need. If this ever stops holding, the shipped remedy becomes a lie and
    this test is what says so."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, f"xc-cheap-{complexity}")
    commit = _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    # The entry carries the behavior directly — no shared results file at all.
    _write(wt, f".shipwright/agent_docs/iterates/{_RUN}.json", json.dumps({
        "run_id": _RUN, "complexity": complexity, "type": "change",
        "test_completeness": {"status": "n/a", "behaviors": [
            {"behavior": "the pieces compose", "disposition": "tested",
             "evidence": "test_x", "category": "integration"},
        ]},
    }))
    assert not (wt / "shipwright_test_results.json").exists()

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is True and not res.is_skipped, res


def test_a_foreign_runs_ledger_does_not_satisfy_the_gate(git_origin_repo, make_worktree):
    """The shared results file must be ATTRIBUTED before it can credit anyone.

    On a branch behind main, F11 restores `shipwright_test_results.json` to HEAD —
    so an unattributed read sees the PREVIOUS run's `iterate_latest`. If that run had
    an integration behavior, this run's cross-component change would pass green on
    someone else's test. `check_test_completeness_ledger`, `check_surface_verification`
    and the silent-revert declarations all guard this file with `is_current`; this
    gate did not, and the reorder widened the hole from medium+ to every complexity
    (Stage-3 doubt review).
    """
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-foreign-ledger")
    commit = _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    _seed_entry(wt, "medium")  # entry carries NO test_completeness → shared-file fallback
    _write(wt, "shipwright_test_results.json", json.dumps({
        "iterate_latest": {
            "run_id": "iterate-SOMEONE-ELSE",
            "test_completeness": {"status": "complete", "behaviors": [
                {"behavior": "their pieces compose", "disposition": "tested",
                 "evidence": "their_test", "category": "integration"},
            ]},
        },
    }))

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False and not res.is_skipped, res
    assert "iterate-SOMEONE-ELSE" in res.detail, res.detail


def test_this_runs_ledger_in_the_shared_file_still_satisfies_the_gate(git_origin_repo, make_worktree):
    """The other direction — the attribution guard must not break the legitimate
    fallback for a run that genuinely wrote the shared file."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-own-ledger")
    commit = _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    _seed_entry(wt, "medium")
    _seed_ledger(wt, [
        {"behavior": "the pieces compose", "disposition": "tested",
         "evidence": "test_x", "category": "integration"},
    ])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is True and not res.is_skipped, res


def test_corrupt_results_json_is_distinct_failure(git_origin_repo, make_worktree):
    # A cross-component diff with an UNREADABLE results.json must fail with a
    # DISTINCT "corrupt" reason, not be misreported as "missing integration
    # coverage" (external-review fix). Distinct from a corrupt ENTRY file, which
    # the store simply skips.
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-corrupt")
    commit = _commit_change(wt, "shared/scripts/tools/ensure_current.py", "touch resolver")
    _seed_entry(wt, "medium")
    _write(wt, "shipwright_test_results.json", "{ this is not json")

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False and not res.is_skipped
    assert "corrupt" in res.detail.lower() or "unreadable" in res.detail.lower()



if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
