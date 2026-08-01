"""`iterate_checks.check_integration_coverage` — the non-dodgeable F11 gate for
the `cross_component` risk flag (iterate-2026-06-12-cross-component-gate).

An iterate that touches FRAMEWORK cross-component machinery (merge/churn
resolver, hooks + hook fan-out, pipeline validators, campaign drain) MUST carry an
INTEGRATION-coverage behavior (`category: "integration"`) in the Test Completeness
Ledger — a real-scenario test proving the components compose. The gate RECOMPUTES
`cross_component` from the actual diff (merge-base..HEAD), NOT from any
agent-reported flag.

**The diff decides, at every complexity**
(iterate-2026-08-01-coverage-gate-recompute-order). Until then the gate read the
run's *recorded* complexity first and green-SKIPped below `medium`, so the
recompute it advertised as non-dodgeable was reached only for runs that had
already self-reported into the enforcing band. The recorded complexity is now
message content, never control flow.

Real-git via the `git_origin_repo` / `make_worktree` fixtures + helpers from
`test_integrate_main`.
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
from tools.verifiers import integration_coverage as icov  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402

_RUN = "iterate-xc"

# Every complexity tier. The gate's whole point is that this axis does not decide
# anything, so the enforcement tests sweep it rather than sampling one value.
_ALL_COMPLEXITIES = ("trivial", "small", "medium", "large")


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


# --- the recompute decides, at every complexity -------------------------------


@pytest.mark.parametrize("complexity", _ALL_COMPLEXITIES)
def test_cross_component_without_integration_behavior_fails_at_every_complexity(
    complexity, git_origin_repo, make_worktree,
):
    """The reordering's core property. `small` and `trivial` used to green-SKIP
    here before reaching the diff at all."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, f"xc-fail-{complexity}")
    commit = _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    _seed_entry(wt, complexity)
    _seed_ledger(wt, [{"behavior": "some unit thing", "disposition": "tested",
                       "evidence": "test_x", "category": "unit"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False, res
    assert res.severity == "error" and not res.is_skipped, res
    assert "integration" in res.detail.lower()


@pytest.mark.parametrize("complexity", _ALL_COMPLEXITIES)
def test_integration_behavior_satisfies_the_gate_at_every_complexity(
    complexity, git_origin_repo, make_worktree,
):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, f"xc-ok-{complexity}")
    commit = _commit_change(wt, "plugins/x/hooks/hooks.json", "touch hook fan-out")
    _seed_entry(wt, complexity)
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


def test_non_cross_component_passes_with_no_iterate_entry_at_all(git_origin_repo, make_worktree):
    """Newly reachable after the reorder: the entry is read only once the diff has
    established applicability, so the common no-op path must not need one."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-noentry-pass")
    commit = _commit_change(wt, "src/app/page.tsx", "ordinary route")
    # deliberately no _seed_entry, no _seed_ledger
    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is True and not res.is_skipped, res


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


# --- the recorded complexity is message content, never control flow -----------


@pytest.mark.parametrize("complexity", ("trivial", "small"))
def test_below_medium_failure_names_the_classification_floor(
    complexity, git_origin_repo, make_worktree,
):
    """Two things went wrong, and the operator is told both: the change is
    untested for composition AND the run is under-classified against the
    `min_complexity: medium` the flag enforces."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, f"xc-floor-{complexity}")
    commit = _commit_change(wt, "shared/scripts/lib/churn_merge.py", "touch churn resolver")
    _seed_entry(wt, complexity)
    _seed_ledger(wt, [{"behavior": "x", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False, res
    assert complexity in res.detail
    assert "medium" in res.detail and "under-classified" in res.detail.lower(), res.detail


@pytest.mark.parametrize("complexity", ("medium", "large"))
def test_enforcing_complexity_makes_no_floor_claim(complexity, git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, f"xc-nofloor-{complexity}")
    commit = _commit_change(wt, "shared/scripts/lib/churn_merge.py", "touch churn resolver")
    _seed_entry(wt, complexity)
    _seed_ledger(wt, [{"behavior": "x", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False, res
    assert "under-classified" not in res.detail.lower(), res.detail


def test_absent_entry_still_fails_and_claims_no_floor(git_origin_repo, make_worktree):
    """Omitting the self-report must never be the cheap way out — and the message
    must not assert a floor violation the gate cannot substantiate."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-noentry")
    commit = _commit_change(wt, "shared/scripts/tools/ensure_current.py", "touch resolver")
    # no entry file at all
    _seed_ledger(wt, [{"behavior": "x", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False and not res.is_skipped, res
    assert "under-classified" not in res.detail.lower(), res.detail


def test_non_utf8_entry_file_fails_closed_instead_of_raising(git_origin_repo, make_worktree):
    """AC-11 says a malformed entry must be ABSENT, never fatal.

    `lib/iterate_entry.py` catches only (JSONDecodeError, OSError), and
    UnicodeDecodeError is a ValueError — so a non-UTF-8 entry file propagates out of
    `find_entry_by_run_id` and, since verify_iterate_finalization has no try/except
    around run_all_checks, takes down the report for EVERY check rather than just
    this one. The gate absorbs it at its own call site (`_read_entry`); fixing the
    shared store is tracked as trg-06216b9f.
    """
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-badbytes")
    commit = _commit_change(wt, "shared/scripts/tools/ensure_current.py", "touch resolver")
    entry_path = wt / ".shipwright" / "agent_docs" / "iterates" / f"{_RUN}.json"
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    # Valid JSON structure, invalid UTF-8 (a lone continuation byte).
    entry_path.write_bytes(b'{"run_id": "' + _RUN.encode() + b'", "complexity": "\xff\xfe"}')

    res = ic.check_integration_coverage(wt, _RUN, commit)  # must not raise
    assert res.ok is False and not res.is_skipped, res
    assert "under-classified" not in res.detail.lower(), res.detail


def test_a_non_dict_entry_is_treated_as_absent(git_origin_repo, make_worktree, monkeypatch):
    """The other half of AC-11's shape guard. `find_entry_by_run_id` returns
    dict|None today, so this pins the contract rather than a reachable state — if a
    future store shape returns a list or a string, the gate must degrade to "no
    self-report" rather than raising AttributeError on `.get`."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-nondict")
    commit = _commit_change(wt, "shared/scripts/tools/ensure_current.py", "touch resolver")
    monkeypatch.setattr(icov, "find_entry_by_run_id", lambda root, run_id: ["not", "a", "dict"])

    res = ic.check_integration_coverage(wt, _RUN, commit)  # must not raise
    assert res.ok is False and not res.is_skipped, res
    assert "under-classified" not in res.detail.lower(), res.detail


def test_malformed_entry_still_fails_and_claims_no_floor(git_origin_repo, make_worktree):
    """A corrupt entry file is SKIPPED by the store's reader, so the gate sees no
    self-report — distinct from the corrupt-results-artifact branch below."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-badentry")
    commit = _commit_change(wt, "shared/scripts/tools/ensure_current.py", "touch resolver")
    _write(wt, f".shipwright/agent_docs/iterates/{_RUN}.json", "{ not json at all")
    _seed_ledger(wt, [{"behavior": "x", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, commit)
    assert res.ok is False and not res.is_skipped, res
    assert "under-classified" not in res.detail.lower(), res.detail



# --- _floor_note normalization, pinned directly ------------------------------
#
# The gate-level tests all seed a clean lowercase literal, so deleting
# `.strip().lower()` (or the `str(...)`) left the whole suite green — the note
# would silently vanish for a legacy entry carrying " Small ". Unit-tested here
# because no realistic end-to-end fixture exercises it.


@pytest.mark.parametrize("recorded,expects_note", [
    ({"complexity": "small"}, True),
    ({"complexity": "trivial"}, True),
    ({"complexity": " SMALL "}, True),      # legacy, pre-normalize_legacy_entry
    ({"complexity": "TRIVIAL"}, True),
    ({"complexity": "medium"}, False),
    ({"complexity": "large"}, False),
    ({"complexity": ""}, False),            # unknown → no claim we cannot substantiate
    ({"complexity": None}, False),
    ({"complexity": 3}, False),             # non-string must degrade, not raise
    ({"complexity": ["small"]}, False),
    ({}, False),
    (None, False),
])
def test_floor_note_only_claims_a_floor_it_can_substantiate(recorded, expects_note):
    note = icov._floor_note(recorded)
    assert bool(note) is expects_note, note
    if expects_note:
        assert "under-classified" in note and "medium" in note


# The infra fail-closed paths (git tri-state, HEAD fallback, and the
# None / [] / paths contract of `_iterate_changed_paths`) live in
# `test_check_integration_coverage_infra.py` — split out to keep this module
# under the 300-line file limit.


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
