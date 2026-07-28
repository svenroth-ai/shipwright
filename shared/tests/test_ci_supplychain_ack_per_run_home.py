"""The CI supply-chain ack reads from a per-run home, not from a derived snapshot
(iterate-2026-07-28-ci-ack-per-run-home).

Two F11 checks, both ERROR, could not be satisfied at once by an iterate
touching `.github/workflows/**`:

- `check_ci_supplychain_ack` read the ack from the COMMITTED
  `shipwright_test_results.json` (its disk fallback fires only when `git show`
  fails, i.e. when the file is untracked at that commit — it is tracked on main,
  so the committed, ack-less copy always won); and
- `check_no_derived_snapshots_committed` errors when the commit touches that
  same file, because it is a `DERIVED_SNAPSHOTS` path.

Commit it and the second fails; omit it and the first does.

The ack now lives at `.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json`
— the directory `reviews.json` already occupies: tracked, not derived, per-run.

This module pins the READ semantics: the new home, source precedence, the legacy
leg, and run-id path safety. The composition failure itself (both gates green on
one commit), the writer CLI and `restore_derived_to_head` live in
``test_ci_supplychain_ack_deadlock.py``, which imports the helpers below.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.derived_snapshots import DERIVED_SNAPSHOTS  # noqa: E402
from test_integrate_main import _git, _write  # noqa: E402
from tools.verifiers import ci_supplychain as cs  # noqa: E402

_RUN = "iterate-2026-07-28-ci-ack-per-run-home"
_WF = ".github/workflows/ci.yml"
_BODY = "on: push\n"
_WITH = "ADR-042"
_STMT = "GitHub-owned actions stay on mutable tags; third-party stay SHA-pinned."


def _fp(paths: list[str], body: str = _BODY) -> str:
    return cs.ci_supplychain_fingerprint(paths, lambda _rel: body)


def _ack(run_id: str = _RUN, fingerprint: str | None = None, **over) -> dict:
    ack = {
        "run_id": run_id,
        "paths_fingerprint": fingerprint if fingerprint is not None else _fp([_WF]),
        "consistent_with": _WITH,
        "statement": _STMT,
        "ci_paths": [_WF],
    }
    ack.update(over)
    return ack


def _write_per_run_ack(wt: Path, ack: dict, run_id: str = _RUN) -> str:
    rel = cs.ack_relpath(run_id)
    _write(wt, rel, json.dumps(
        {"schema_version": 1, "run_id": run_id, "ci_supplychain_ack": ack}, indent=2))
    return rel


def _write_legacy_ack(wt: Path, ack: dict) -> None:
    _write(wt, "shipwright_test_results.json",
           json.dumps({"iterate_latest": {"run_id": _RUN, "ci_supplychain_ack": ack}}))


def _touch_workflow(wt: Path, body: str = _BODY) -> None:
    _write(wt, _WF, body)


def _commit(wt: Path, *paths: str) -> str:
    # Repo-level identity, set here rather than per test: the linked worktree
    # shares config through the common .git dir, so one call covers every commit
    # and a runner with no global git identity still works.
    _git(wt, "config", "user.email", "iterate@test.invalid")
    _git(wt, "config", "user.name", "Iterate Test")
    _git(wt, "add", *(paths or ("-A",)))
    _git(wt, "commit", "-m", "feat(ci): touch the trust boundary")
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


# --- the new home -----------------------------------------------------------

def test_ack_relpath_is_the_per_run_planning_dir():
    """Same directory as reviews.json — tracked, not derived, cannot collide."""
    rel = cs.ack_relpath(_RUN)
    assert rel == f".shipwright/planning/iterate/{_RUN}/ci_supplychain_ack.json"
    assert rel not in DERIVED_SNAPSHOTS


def test_passes_with_a_committed_per_run_ack(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-ok")
    _touch_workflow(wt)
    rel = _write_per_run_ack(wt, _ack())
    commit = _commit(wt, _WF, rel)

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True, res.detail
    # read from the commit: the durable case carries no caveat
    assert "working tree" not in res.detail
    assert "legacy" not in res.detail


def test_per_run_ack_untracked_at_the_commit_falls_back_to_the_worktree(
        git_origin_repo, make_worktree):
    """A brand-new ack file not yet staged is genuinely absent from the tree, and
    absence — unlike a git failure — may consult the working copy.

    The gate PASSES, but such an ack is not in the commit and will not ship in
    the PR, so the result must say so: "recorded" must not silently read as
    "recorded and durable" (Stage-1 spec review, observation 2).
    """
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-untracked")
    _touch_workflow(wt)
    _write_per_run_ack(wt, _ack())
    commit = _commit(wt, _WF)          # ack deliberately NOT staged

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True, res.detail
    assert "working tree" in res.detail and "will not ship" in res.detail


# --- precedence: a PRESENT source is terminal (external review, GPT #3) -----

def test_per_run_ack_takes_precedence_over_a_legacy_ack(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-precedence")
    _touch_workflow(wt)
    rel = _write_per_run_ack(wt, _ack(consistent_with="#497"))
    _write_legacy_ack(wt, _ack(consistent_with=_WITH))
    commit = _commit(wt, _WF, rel, "shipwright_test_results.json")

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True
    assert "#497" in res.detail, "the per-run ack must be the one that answered"


def test_invalid_per_run_ack_does_not_fall_back_to_a_valid_legacy_ack(
        git_origin_repo, make_worktree):
    """The sharpest external-review finding. If a stale per-run ack quietly
    deferred to a valid legacy one, the new home would be bypassable: park a good
    old-style ack, then write whatever you like to the new path."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-nobypass")
    _touch_workflow(wt)
    rel = _write_per_run_ack(wt, _ack(run_id="iterate-2026-01-01-something-else"))
    _write_legacy_ack(wt, _ack())      # perfectly valid
    commit = _commit(wt, _WF, rel, "shipwright_test_results.json")

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "run" in res.detail.lower()


def test_per_run_ack_with_a_wrong_fingerprint_is_rejected(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-fp")
    _touch_workflow(wt)
    rel = _write_per_run_ack(wt, _ack(fingerprint=_fp([".github/dependabot.yml"])))
    commit = _commit(wt, _WF, rel)

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "fingerprint" in res.detail.lower()


def test_corrupt_per_run_ack_fails_closed(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-corrupt")
    _touch_workflow(wt)
    rel = cs.ack_relpath(_RUN)
    _write(wt, rel, "{ not json at all")
    _write_legacy_ack(wt, _ack())      # must NOT rescue it
    commit = _commit(wt, _WF, rel, "shipwright_test_results.json")

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "unreadable" in res.detail.lower() or "corrupt" in res.detail.lower()


# --- legacy compatibility (in-flight branches) ------------------------------

def test_legacy_iterate_latest_ack_is_still_accepted(git_origin_repo, make_worktree):
    """Branches that recorded the ack the old way must not red-line at F11 for a
    reason they cannot act on without a rebase."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-legacy")
    _touch_workflow(wt)
    _write_legacy_ack(wt, _ack())
    commit = _commit(wt, _WF, "shipwright_test_results.json")

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True, res.detail
    # the result names the legacy leg, so a reader can tell the run predates the move
    assert "legacy" in res.detail


def test_legacy_ack_read_from_disk_is_reported_as_not_shipping(
        git_origin_repo, make_worktree):
    """The legacy leg has the same durability question as the per-run one. Marking
    it merely "legacy" dropped the non-shipping warning when the results file was
    on disk but absent from the commit — the exact hole this change closes on the
    new path, left open on the old one (external code review)."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-legacy-disk")
    _touch_workflow(wt)
    _write_legacy_ack(wt, _ack())
    commit = _commit(wt, _WF)          # results file deliberately NOT staged

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True, res.detail
    assert "legacy" in res.detail
    assert "will not ship" in res.detail


def test_legacy_ack_is_still_run_and_fingerprint_bound(git_origin_repo, make_worktree):
    """The legacy leg is a different LOCATION, not a weaker rule."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-legacy-stale")
    _touch_workflow(wt)
    _write_legacy_ack(wt, _ack(run_id="iterate-2026-01-01-something-else"))
    commit = _commit(wt, _WF, "shipwright_test_results.json")

    assert cs.check_ci_supplychain_ack(wt, _RUN, commit).ok is False


def test_no_ack_anywhere_still_fails(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-none")
    _touch_workflow(wt)
    commit = _commit(wt, _WF)

    assert cs.check_ci_supplychain_ack(wt, _RUN, commit).ok is False


# --- run_id is a path component (external review, GPT #4) -------------------

def test_unsafe_run_id_fails_closed(git_origin_repo, make_worktree):
    """`run_id` becomes a directory name; traversal must not silently resolve
    somewhere else — and must not degrade into 'no ack needed'."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-traversal")
    _touch_workflow(wt)
    commit = _commit(wt, _WF)

    assert cs.check_ci_supplychain_ack(wt, "../../etc/passwd", commit).ok is False


def test_load_ack_guards_the_run_id_itself(git_origin_repo, make_worktree):
    """Defence in depth: `load_ack` builds a filesystem path from `run_id`, so it
    enforces the guard rather than trusting every caller to (Stage-2 review)."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-loadguard")
    ack, err, source = cs.load_ack(wt, "../../etc/passwd", "")
    assert ack is None and source == ""
    assert err and "safe path component" in err


def test_unrecognised_schema_version_is_refused(git_origin_repo, make_worktree):
    """The version field is load-bearing, not decorative: an unknown envelope read
    with v1 semantics is the one place a format change would be MISread rather than
    fail closed, in a gate whose whole posture is fail-closed (Stage-2 review)."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-schema")
    _touch_workflow(wt)
    rel = cs.ack_relpath(_RUN)
    _write(wt, rel, json.dumps(
        {"schema_version": 99, "run_id": _RUN, "ci_supplychain_ack": _ack()}))
    commit = _commit(wt, _WF, rel)

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "schema_version" in res.detail


def test_unsafe_run_id_does_not_fire_when_no_ci_file_is_touched(
        git_origin_repo, make_worktree):
    """The run-id guard must not manufacture a finding on an unrelated diff."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "prh-traversal-noci")
    _write(wt, "src/app/page.tsx", "export default null\n")
    commit = _commit(wt, "src/app/page.tsx")

    assert cs.check_ci_supplychain_ack(wt, "../../etc/passwd", commit).ok is True
