"""The derived snapshots stay OUT of an iterate branch
(iterate-2026-07-27-derived-snapshots-off-branch).

Measured cause: with five PRs open on 2026-07-27, three sat DIRTY and
``git merge-tree`` showed ZERO conflicting source files — 100% of the conflicts
were the eleven regenerated snapshots, which every iterate rewrites regardless of
what it changed. Worse, a branch-local derivation is WRONG for main: it reads the
branch's git history (pre-squash SHAs) and an event log missing every
concurrently-merging branch.

Two properties are pinned here:

1. ``restore_derived_to_head`` puts a derived snapshot back even when a producer
   already STAGED it — so a stray ``git add -A``, hook, or future implementation
   cannot silently reintroduce the conflict class. F6's documented add-list is
   prose; this is the mechanism.
2. The registry names exactly those eleven and sweeps in nothing that ships.

The real-git half — ``integrate`` and the F11 gate — is in
test_derived_snapshots_integrate.py (split only to stay inside the 300-LOC guideline).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import DERIVED_MDS, TEST_RESULTS  # noqa: E402
from lib.derived_snapshots import (  # noqa: E402
    DERIVED_SNAPSHOTS,
    restore_derived_to_head,
)

_DASH = ".shipwright/compliance/dashboard.md"
_RUN_ID = "iterate-2026-07-27-derived-snapshots-off-branch"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="Derived Test",
        GIT_AUTHOR_EMAIL="derived@test.invalid",
        GIT_COMMITTER_NAME="Derived Test",
        GIT_COMMITTER_EMAIL="derived@test.invalid",
    )
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=_env(), capture_output=True, text=True, check=check
    )


def _set_repo_identity(work: Path) -> None:
    _git(work, "config", "user.email", "derived@test.invalid")
    _git(work, "config", "user.name", "Derived Test")


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# --- the registry -----------------------------------------------------------

def test_registry_covers_every_derived_md_plus_the_two_json_snapshots() -> None:
    """The eleven paths, derived from the churn registry rather than hand-listed
    so a newly added derived MD is picked up here instead of drifting."""
    assert DERIVED_MDS < DERIVED_SNAPSHOTS
    assert TEST_RESULTS in DERIVED_SNAPSHOTS
    assert ".shipwright/compliance/ci-security.json" in DERIVED_SNAPSHOTS
    assert ".shipwright/compliance/test-traceability.json" in DERIVED_SNAPSHOTS
    assert len(DERIVED_SNAPSHOTS) == 11


def test_registry_excludes_the_append_logs_and_per_run_paths() -> None:
    """The append-only logs compose across branches via ``merge=union`` and the
    per-run / per-campaign paths cannot collide — all of them still ship in the PR.
    Sweeping them in here would strand the run's own evidence."""
    for keeper in (
        "shipwright_events.jsonl",
        ".shipwright/triage.jsonl",
        ".shipwright/agent_docs/architecture.md",
    ):
        assert keeper not in DERIVED_SNAPSHOTS


# --- restore ----------------------------------------------------------------

def test_restore_undoes_a_derived_snapshot_a_producer_already_staged(git_origin_repo) -> None:
    """The load-bearing robustness property: staging is not enough to get a derived
    snapshot into the commit. Without this, F6's add-list is the only thing
    standing between a stray ``git add -A`` and the reinstated conflict class."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "committed dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")

    _write(work, _DASH, "a producer regenerated me\n")
    _git(work, "add", "--", _DASH)  # a producer STAGED it
    assert _git(work, "diff", "--cached", "--quiet", check=False).returncode != 0

    restored = restore_derived_to_head(work)

    assert restored == [_DASH]
    assert (work / _DASH).read_text(encoding="utf-8") == "committed dashboard\n"
    assert not _git(work, "status", "--porcelain").stdout.strip(), "tree must be clean"


def test_restore_undoes_a_DELETED_derived_snapshot(git_origin_repo) -> None:
    """External review, medium: filtering on `exists()` skipped a deleted tracked
    snapshot — it is dirty precisely BECAUSE it is gone — and the deletion then rode
    into the iterate commit. Presence on disk is not the question; being known to
    HEAD is. Covers both an unstaged delete and a staged `git rm`."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "committed dashboard\n")
    _write(work, TEST_RESULTS, '{"coverage": {}}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed two derived snapshots")

    (work / _DASH).unlink()                        # plain worktree deletion
    _git(work, "rm", "--quiet", "--", TEST_RESULTS)  # staged deletion

    restored = restore_derived_to_head(work)

    assert restored == sorted([_DASH, TEST_RESULTS])
    assert (work / _DASH).read_text(encoding="utf-8") == "committed dashboard\n"
    assert (work / TEST_RESULTS).exists()
    assert not _git(work, "status", "--porcelain").stdout.strip(), "tree must be clean"


def test_restore_of_one_odd_path_does_not_defeat_the_others(git_origin_repo) -> None:
    """`git checkout HEAD -- a b c` is all-or-nothing: one path unknown to HEAD can
    abort the whole call and silently leave the rest dirty. Restoring per path keeps
    one odd file from defeating the others."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "committed dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ONE derived snapshot")

    _write(work, _DASH, "regenerated\n")                       # tracked + dirty
    _write(work, TEST_RESULTS, "never tracked at all\n")       # unknown to HEAD

    restored = restore_derived_to_head(work)

    assert restored == [_DASH], "the tracked one must still be restored"
    assert (work / _DASH).read_text(encoding="utf-8") == "committed dashboard\n"
    assert (work / TEST_RESULTS).exists(), "an untracked file must not be deleted"


def test_restore_is_a_noop_on_a_clean_tree_and_never_raises(git_origin_repo) -> None:
    """Restoring is hygiene, not a gate — it must not become a new failure mode."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "committed dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")

    assert restore_derived_to_head(work) == []


def test_restore_ignores_a_snapshot_the_project_does_not_track(git_origin_repo) -> None:
    """``git checkout HEAD --`` on a never-tracked path exits non-zero. A project
    that simply doesn't keep, say, `.shipwright/compliance/` must not be aborted."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _git(work, "commit", "--allow-empty", "-m", "no compliance dir at all")

    _write(work, _DASH, "untracked, never committed\n")  # present but unknown to git

    assert restore_derived_to_head(work) == []
    assert (work / _DASH).exists(), "an untracked file must not be deleted"


# --- the ledger survives the restore ----------------------------------------

def test_completeness_ledger_reads_the_per_run_entry_after_a_restore(tmp_path) -> None:
    """The ordering trap this change created in its own finalization.

    F5 writes the ledger into ``shipwright_test_results.json``; F6 no longer commits
    it; F11's `ensure_current` then restores it to HEAD on a behind branch — wiping
    the ledger *before* `check_test_completeness_ledger` (severity ERROR) reads it.
    A run that did everything right would fail its own gate. The ledger therefore
    lives in the per-run F5c entry, which is collision-free and ships.
    """
    import json

    from tools.verifiers.iterate_checks import check_test_completeness_ledger

    run_id = "iterate-2026-07-27-probe"
    ledger = {
        "status": "complete",
        "enumeration_basis": {"acs": 1, "covered_acs": 1},
        "counts": {"total": 1, "tested": 1, "untestable": 0, "untested_testable": 0},
        "behaviors": [
            {"behavior": "a thing", "disposition": "tested", "evidence": "test_x — passed"}
        ],
    }
    entries = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entries.mkdir(parents=True)
    (entries / f"{run_id}.json").write_text(
        json.dumps({
            "run_id": run_id, "type": "change", "complexity": "medium",
            "tests_passed": True, "test_completeness": ledger,
        }),
        encoding="utf-8",
    )

    # No shipwright_test_results.json at all — exactly the post-restore shape.
    assert not (tmp_path / "shipwright_test_results.json").exists()

    result = check_test_completeness_ledger(tmp_path, run_id)

    assert result.ok is True, result.detail


def test_integration_coverage_reads_the_per_run_entry_after_a_restore(tmp_path, monkeypatch) -> None:
    """The same trap, second victim — caught by the gate on its own iterate.

    `check_integration_coverage` also read the ledger from the shared results file,
    so a cross-component change that HAD its integration test would be failed for
    lacking it, purely because the file was restored before F11 looked.
    """
    import json

    from tools.verifiers import integration_coverage as ic

    run_id = "iterate-2026-07-27-probe"
    entries = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entries.mkdir(parents=True)
    (entries / f"{run_id}.json").write_text(
        json.dumps({
            "run_id": run_id, "type": "change", "complexity": "medium",
            "test_completeness": {
                "status": "complete",
                "behaviors": [
                    {"behavior": "the pieces compose", "disposition": "tested",
                     "evidence": "test_x — passed", "category": "integration"}
                ],
            },
        }),
        encoding="utf-8",
    )
    # A cross-component path in the commit, and no shared results file at all.
    monkeypatch.setattr(ic, "_commit_changed_paths",
                        lambda *_a, **_k: ["shared/scripts/tools/integrate_main.py"])
    assert not (tmp_path / "shipwright_test_results.json").exists()

    result = ic.check_integration_coverage(tmp_path, run_id, "deadbeef")

    assert result.ok is True, result.detail
