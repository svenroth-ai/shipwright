"""Tests for shared/scripts/ci_verified_anchor.py — resolve_verified_anchor()
(P3.4c "Build B: anchor to the newest verified ancestor").

Every test monkeypatches ``ci_verified_anchor.resolve_ci_verification``
directly (never the real GitHub API) — the SAME per-commit seam
``ci_execution_evidence.py``'s own tests use for composing with the real
predicate at a higher level. The git plumbing (``git log --first-parent``)
is real, against a real tmp_path repo, so the ancestor ORDERING and the
``max_commits``/``since_days`` BOUNDS are proven against real git behavior,
not a hand-rolled fake of it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import ci_verified_anchor as mod
from ci_provenance import CIVerification


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


def _init_repo_with_commits(tmp_path, n: int) -> tuple[Path, list[str]]:
    """``n`` commits, oldest first; returns ``(repo, [sha_of_commit_1, ...,
    sha_of_commit_n])`` — ``shas[-1]`` is HEAD."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    shas = []
    for i in range(n):
        (tmp_path / "f.txt").write_text(str(i), encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", f"commit {i}")
        shas.append(_git(tmp_path, "rev-parse", "HEAD").strip())
    return tmp_path, shas


def test_head_itself_verified_is_found_at_depth_zero(tmp_path, monkeypatch):
    project, shas = _init_repo_with_commits(tmp_path, 1)

    monkeypatch.setattr(
        mod, "resolve_ci_verification",
        lambda commit, **kw: CIVerification("verified", "ok", 1) if commit == shas[-1]
        else CIVerification("not_verified", "no"),
    )

    anchor = mod.resolve_verified_anchor(shas[-1], project_root=project)
    assert anchor.status == "found"
    assert anchor.commit == shas[-1]
    assert anchor.depth == 0


def test_falls_back_to_a_verified_parent_when_head_is_not_verified(tmp_path, monkeypatch):
    project, shas = _init_repo_with_commits(tmp_path, 3)
    head, verified_ancestor = shas[-1], shas[-2]

    monkeypatch.setattr(
        mod, "resolve_ci_verification",
        lambda commit, **kw: CIVerification("verified", "ok", 1) if commit == verified_ancestor
        else CIVerification("not_verified", "no"),
    )

    anchor = mod.resolve_verified_anchor(head, project_root=project)
    assert anchor.status == "found"
    assert anchor.commit == verified_ancestor
    assert anchor.depth == 1


def test_no_verified_commit_within_bound_reports_unavailable_not_error(tmp_path, monkeypatch):
    project, shas = _init_repo_with_commits(tmp_path, 3)

    monkeypatch.setattr(mod, "resolve_ci_verification", lambda commit, **kw: CIVerification("not_verified", "no"))

    anchor = mod.resolve_verified_anchor(shas[-1], project_root=project)
    assert anchor.status == "unavailable"
    assert anchor.commit is None


def test_a_query_error_on_one_candidate_does_not_abort_the_search(tmp_path, monkeypatch):
    # Degrades toward the SAFE direction (keep looking / end up unavailable),
    # never aborts a search that could still find an older, genuinely
    # verified commit -- this fallback is a best-effort improvement over an
    # already-safe "unavailable" default, not a new load-bearing check.
    project, shas = _init_repo_with_commits(tmp_path, 3)
    head, older_verified = shas[-1], shas[0]

    def fake(commit, **kw):
        if commit == head:
            return CIVerification("error", "gh hiccup")
        if commit == older_verified:
            return CIVerification("verified", "ok", 1)
        return CIVerification("not_verified", "no")

    monkeypatch.setattr(mod, "resolve_ci_verification", fake)

    anchor = mod.resolve_verified_anchor(head, project_root=project)
    assert anchor.status == "found"
    assert anchor.commit == older_verified


def test_five_consecutive_errors_give_up_before_reaching_a_verified_commit_beyond_them(tmp_path, monkeypatch):
    # Stage-3 doubt review, medium: a systemic query fault (offline,
    # unauthenticated, rate limited) must not burn the FULL max_commits
    # bound of `gh api` calls to reach the same "unavailable" conclusion a
    # handful of consecutive errors already establishes. The genuinely
    # verified commit here sits one candidate PAST the circuit breaker's
    # limit -- proving the walk actually gives up early, not merely that it
    # tolerates isolated errors (that's the pre-existing test above).
    project, shas = _init_repo_with_commits(tmp_path, 8)
    head = shas[-1]
    erroring = set(shas[3:8])  # depths 0-4 (the 5 newest commits): all error
    unreachable_verified = shas[2]  # depth 5 -- past the limit, must never be reached

    def fake(commit, **kw):
        if commit in erroring:
            return CIVerification("error", "gh hiccup")
        if commit == unreachable_verified:
            return CIVerification("verified", "ok", 1)
        return CIVerification("not_verified", "no")

    monkeypatch.setattr(mod, "resolve_ci_verification", fake)

    anchor = mod.resolve_verified_anchor(head, project_root=project)
    assert anchor.status == "unavailable"
    assert "consecutive" in anchor.detail


def test_non_consecutive_errors_never_trip_the_circuit_breaker(tmp_path, monkeypatch):
    # The counter must reset on any non-error verdict -- a query path that
    # is merely spotty (one hiccup here and there), not systemically broken,
    # must still be able to reach a verified commit further back even past
    # more than `_CONSECUTIVE_ERROR_LIMIT` TOTAL (non-consecutive) errors.
    project, shas = _init_repo_with_commits(tmp_path, 8)
    head, older_verified = shas[-1], shas[0]
    # Every other candidate (depths 0,2,4,6) errors; none of them are
    # adjacent, so the consecutive-error counter never exceeds 1.
    erroring = {shas[7], shas[5], shas[3], shas[1]}

    def fake(commit, **kw):
        if commit == older_verified:
            return CIVerification("verified", "ok", 1)
        if commit in erroring:
            return CIVerification("error", "gh hiccup")
        return CIVerification("not_verified", "no")

    monkeypatch.setattr(mod, "resolve_ci_verification", fake)

    anchor = mod.resolve_verified_anchor(head, project_root=project)
    assert anchor.status == "found"
    assert anchor.commit == older_verified


def test_head_commit_case_is_normalised_before_the_git_log_call(tmp_path, monkeypatch):
    # Stage-3 doubt review, low: `git log --format=%H` always emits
    # lowercase, so an uppercase/mixed-case `head_commit` must not make the
    # depth-0 candidate's `sha` differ from the caller's own string by case
    # alone (defeating an `anchor.commit != sha` guard at the call site).
    project, shas = _init_repo_with_commits(tmp_path, 1)
    upper = shas[-1].upper()

    monkeypatch.setattr(
        mod, "resolve_ci_verification",
        lambda commit, **kw: CIVerification("verified", "ok", 1) if commit == shas[-1]
        else CIVerification("not_verified", "no"),
    )

    anchor = mod.resolve_verified_anchor(upper, project_root=project)
    assert anchor.status == "found"
    assert anchor.commit == shas[-1]  # lowercase, matching resolve_head_sha's own output


def test_max_commits_bounds_the_walk(tmp_path, monkeypatch):
    project, shas = _init_repo_with_commits(tmp_path, 3)
    head, older_verified = shas[-1], shas[0]

    monkeypatch.setattr(
        mod, "resolve_ci_verification",
        lambda commit, **kw: CIVerification("verified", "ok", 1) if commit == older_verified
        else CIVerification("not_verified", "no"),
    )

    # Bounded to 2 candidates (head + one parent) -- the verified commit is
    # 2 commits back and must never be reached.
    anchor = mod.resolve_verified_anchor(head, project_root=project, max_commits=2)
    assert anchor.status == "unavailable"


def test_since_days_bound_is_threaded_through_without_crashing(tmp_path, monkeypatch):
    # A precise "excludes an old commit" assertion would be timing-flaky
    # against freshly-made test commits (git's `--since` resolves relative
    # to wall-clock "now" at query time) -- covered instead by
    # `max_commits`, above, which bounds the exact same walk
    # deterministically. This pins only that the kwarg reaches `git log`
    # without error and still returns a well-formed result either way.
    project, shas = _init_repo_with_commits(tmp_path, 2)
    head, older = shas[-1], shas[0]

    monkeypatch.setattr(
        mod, "resolve_ci_verification",
        lambda commit, **kw: CIVerification("verified", "ok", 1) if commit == older
        else CIVerification("not_verified", "no"),
    )

    anchor = mod.resolve_verified_anchor(head, project_root=project, since_days=3650, max_commits=50)
    assert anchor.status == "found"
    assert anchor.commit == older


def test_git_log_failure_reports_error(tmp_path):
    # Not a git repository at all -- `git log` itself fails to run.
    anchor = mod.resolve_verified_anchor("a" * 40, project_root=tmp_path)
    assert anchor.status == "error"


def test_a_non_sha_head_commit_reports_error_without_running_git(tmp_path):
    # External code review, low: `head_commit` reaches `git log ...
    # <head_commit>` with no injection guard otherwise -- a value starting
    # with `-` would be parsed as a git option. Validated the same way
    # `ci_provenance._COMMIT_RE` already validates its own `commit` argument.
    anchor = mod.resolve_verified_anchor("--output=/tmp/pwned", project_root=tmp_path)
    assert anchor.status == "error"
    assert anchor.commit is None
