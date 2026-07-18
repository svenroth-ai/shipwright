"""`check_ci_supplychain_ack` — the non-dodgeable F11 gate for the
`touches_ci_supplychain` risk flag (iterate-2026-07-18-ci-supplychain-risk-flag,
triage trg-9509c2e8).

A diff touching the CI trust boundary (workflows, dependabot config, composite
actions) MUST carry an acknowledgement naming the recorded posture decision it is
consistent with. The gate RECOMPUTES the flag from the actual diff
(merge-base..HEAD), and the ack is bound to BOTH the run id and a fingerprint of
this diff's CI paths — so a stale ack from an earlier iterate cannot license a
later CI change (the false-green the external review caught in the first draft).

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
from tools.verifiers import ci_supplychain as cs  # noqa: E402

_RUN = "iterate-2026-07-18-ci-supplychain-risk-flag"
_GOOD_WITH = "ADR-042"
_GOOD_STMT = "GitHub-owned actions stay on mutable tags; third-party stay SHA-pinned."


def _seed_ack(wt: Path, **overrides) -> None:
    ack = {
        "run_id": _RUN,
        "paths_fingerprint": overrides.pop("fingerprint", None),
        "consistent_with": _GOOD_WITH,
        "statement": _GOOD_STMT,
    }
    ack.update(overrides)
    _write(wt, "shipwright_test_results.json",
           json.dumps({"iterate_latest": {"run_id": _RUN, "ci_supplychain_ack": ack}}))


def _commit_change(wt: Path, path: str, msg: str) -> str:
    _write(wt, path, "on: push\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", msg)
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


_BODY = "on: push\n"


def _fp(paths: list[str]) -> str:
    """Fingerprint as the verifier will compute it: paths AND committed content."""
    return cs.ci_supplychain_fingerprint(paths, lambda rel: _BODY)


# --- the flag does not fire -------------------------------------------------

def test_passes_when_no_ci_file_touched(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-none")
    commit = _commit_change(wt, "src/app/page.tsx", "unrelated change")
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True


# --- the flag fires ---------------------------------------------------------

def test_fails_when_ci_touched_without_any_ack(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-noack")
    commit = _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    _write(wt, "shipwright_test_results.json", json.dumps({"iterate_latest": {"run_id": _RUN}}))
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "ci.yml" in res.detail


def test_passes_with_a_valid_bound_ack(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-ok")
    commit = _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    _seed_ack(wt, fingerprint=_fp([".github/workflows/ci.yml"]))
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True


# --- the freshness binding (the external-review finding) --------------------

def test_rejects_ack_from_a_different_run(git_origin_repo, make_worktree):
    """A leftover ack in iterate_latest must not license THIS run's CI change."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-stale-run")
    commit = _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    _seed_ack(wt, run_id="iterate-2026-01-01-something-else",
              fingerprint=_fp([".github/workflows/ci.yml"]))
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "run" in res.detail.lower()


def test_rejects_ack_whose_fingerprint_matches_a_different_change(git_origin_repo, make_worktree):
    """Acknowledging a workflow tweak must not license a dependabot.yml revival."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-stale-fp")
    commit = _commit_change(wt, ".github/dependabot.yml", "reintroduce the hosted updater")
    _seed_ack(wt, fingerprint=_fp([".github/workflows/ci.yml"]))
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "fingerprint" in res.detail.lower()


# --- filler cannot satisfy it ----------------------------------------------

def test_rejects_filler_statement(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-filler")
    commit = _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    _seed_ack(wt, fingerprint=_fp([".github/workflows/ci.yml"]), statement="   N/A   ")
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False


def test_rejects_consistent_with_that_names_no_recorded_decision(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-noref")
    commit = _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    _seed_ack(wt, fingerprint=_fp([".github/workflows/ci.yml"]),
              consistent_with="we talked about it and it seemed fine")
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False


# --- fail closed ------------------------------------------------------------

def test_corrupt_results_file_is_reported_explicitly(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-corrupt")
    commit = _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    _write(wt, "shipwright_test_results.json", "{ this is not json")
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "unreadable" in res.detail.lower() or "corrupt" in res.detail.lower()


def test_non_repo_skips_but_missing_commit_inside_a_repo_fails_closed(
        tmp_path, git_origin_repo, make_worktree):
    """Two different situations that must NOT be conflated.

    Outside a repo there is nothing to merge, so the gate stands down (and the CLI
    sandbox tests keep their contract). INSIDE a repo an absent commit IS an
    unobtainable diff — otherwise omitting one flag would bypass the gate entirely,
    making the cheaper input the safer one for a dodger.
    """
    assert cs.check_ci_supplychain_ack(tmp_path, _RUN, "").ok is True

    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-headless")
    _commit_change(wt, ".github/workflows/ci.yml", "touch CI boundary")
    res = cs.check_ci_supplychain_ack(wt, _RUN, "")   # HEAD resolves; ack absent
    assert res.ok is False


def _const_reader(_rel: str) -> str:
    return _BODY


def test_fingerprint_is_order_and_separator_stable():
    a = cs.ci_supplychain_fingerprint(
        [".github/workflows/b.yml", ".github/workflows/a.yml", "README.md"], _const_reader)
    b = cs.ci_supplychain_fingerprint(
        [".github\\workflows\\a.yml", ".github/workflows/b.yml"], _const_reader)
    assert a == b, "fingerprint must sort, normalize separators and ignore non-CI paths"


def test_fingerprint_changes_when_ci_file_content_changes():
    """Path-only binding let an author ack "adds a ruff step" and then slip
    `pull_request_target:` into the same file before committing."""
    paths = [".github/workflows/ci.yml"]
    before = cs.ci_supplychain_fingerprint(paths, lambda _r: "on: push\n")
    after = cs.ci_supplychain_fingerprint(paths, lambda _r: "on: pull_request_target\n")
    assert before != after


def test_quoted_non_ascii_path_still_detected():
    """git quotes non-ASCII paths by default; a leading quote must not defeat the
    `^` anchor and smuggle a new workflow past the gate."""
    assert cs._is_ci_supplychain(['".github/workflows/\\303\\244.yml"']) is True


def test_renovate_config_is_covered():
    """Reintroducing a hosted updater under a different filename must not escape."""
    for p in [".github/renovate.json", "renovate.json5", ".renovaterc"]:
        assert cs._is_ci_supplychain([p]) is True, p
