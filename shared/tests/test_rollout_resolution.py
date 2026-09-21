"""Real-git tests for the shared commit-resolution primitive
(:mod:`_rollout_resolution`), extracted from ``_project_gate_rollout.py`` and
``_layer_coverage_rollout.py`` (`iterate-2026-09-20-shared-rollout-commit-resolver`,
closing a THIRD-near-identical-copy finding external plan review (glm) raised
on `iterate-2026-09-12-project-gate-rollout-transition`).

Deliberately uses an epoch that belongs to NEITHER existing gate family
(``_ARBITRARY_EPOCH`` below) — this primitive owns the git plumbing only, not
any one family's rollout instant, and a test suite that reused a family's own
epoch constant could not tell the two apart. Each family's own module keeps
its own real-git behavioural coverage (``test_project_gate_rollout.py``,
``test_layer_coverage_rollout.py``) pinned against ITS epoch; this file pins
the shared algorithm once.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._rollout_resolution import (  # noqa: E402
    is_shallow,
    resolve_head_sha,
    resolve_rollout_commit,
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit_at(root: Path, msg: str, iso_date: str, *, on_trunk: bool = True) -> str:
    """``on_trunk=True`` (the default) also advances a simulated
    ``origin/main`` to the new commit — standing in for "this content is
    already merged", the trust anchor `resolve_rollout_commit` requires
    (`trg-4380c61a`). Pass ``on_trunk=False`` to build a commit that exists
    only on the local branch, unreachable from that anchor."""
    _git(root, "add", "-A")
    proc = subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", msg],
        capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git commit failed: {proc.stderr}")
    sha = _git(root, "rev-parse", "HEAD")
    if on_trunk:
        _git(root, "update-ref", "refs/remotes/origin/main", sha)
    return sha


# Neither `_project_gate_rollout.GATE_ROLLOUT_AT_EPOCH` (1789194186) nor
# `_layer_coverage_rollout.GATE_ROLLOUT_AT_EPOCH` (1788797359) — an
# unrelated instant, by design (see module docstring).
_ARBITRARY_EPOCH = 1780000000  # 2026-05-28T20:26:40Z
_BEFORE = "2026-05-20T00:00:00+00:00"
_AT = "2026-05-28T20:26:40+00:00"  # == _ARBITRARY_EPOCH, to the second
_AFTER = "2026-06-05T00:00:00+00:00"


def test_epoch_fixture_matches_the_boundary_instant_to_the_second():
    import datetime
    boundary = datetime.datetime.fromisoformat(_AT)
    assert int(boundary.timestamp()) == _ARBITRARY_EPOCH


def test_resolve_head_sha_resolves_head_to_a_concrete_sha(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "a.txt", "x")
    head_sha = _commit_at(root, "c1", _BEFORE)
    assert resolve_head_sha(root, "HEAD") == head_sha


def test_resolve_head_sha_none_on_an_unresolvable_ref(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "a.txt", "x")
    _commit_at(root, "c1", _BEFORE)
    assert resolve_head_sha(root, "not-a-real-ref") is None


def test_is_shallow_false_for_a_normal_full_clone(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "a.txt", "x")
    _commit_at(root, "c1", _BEFORE)
    assert is_shallow(root) is False


def test_resolve_rollout_commit_finds_a_commit_strictly_before_the_given_epoch(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "pre")
    pre_sha = _commit_at(root, "pre", _BEFORE)
    _write(root, "f.txt", "post")
    head_sha = _commit_at(root, "post", _AFTER)

    assert resolve_rollout_commit(root, head_sha, epoch=_ARBITRARY_EPOCH) == pre_sha


def test_resolve_rollout_commit_accepts_a_commit_exactly_at_the_boundary_instant(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "at boundary")
    boundary_sha = _commit_at(root, "at boundary", _AT)
    _write(root, "f.txt", "post")
    head_sha = _commit_at(root, "post", _AFTER)

    assert resolve_rollout_commit(root, head_sha, epoch=_ARBITRARY_EPOCH) == boundary_sha


def test_resolve_rollout_commit_none_when_repo_born_entirely_after_the_epoch(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "post")
    head_sha = _commit_at(root, "born after", _AFTER)

    assert resolve_rollout_commit(root, head_sha, epoch=_ARBITRARY_EPOCH) is None


def test_resolve_rollout_commit_none_for_a_shallow_clone(tmp_path):
    """The discriminating assertion here is ``is_shallow(shallow) is True`` —
    the `--depth 1` clone retains only the post-epoch HEAD, so
    `resolve_rollout_commit` would return ``None`` from the plain
    `rev-list -1 --before` lookup finding nothing even if the `is_shallow`
    short-circuit were deleted. The trailing `resolve_rollout_commit(...) is
    None` is corroboration, not the guard's own proof (code review, low)."""
    origin = tmp_path / "origin"
    _init(origin)
    _write(origin, "f.txt", "pre")
    _commit_at(origin, "pre", _BEFORE)
    _write(origin, "f.txt", "post")
    _commit_at(origin, "post", _AFTER)

    # Only a `file://` URL forces git through the real network-clone code path
    # that honours `--depth` (a same-machine PATH clone takes git's local-clone
    # fast path and copies full history regardless) — asserted below rather
    # than assumed, per the identical precedent in the two family test files.
    shallow = tmp_path / "shallow"
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", origin.as_uri(), str(shallow)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true", (
        "clone did not actually produce a shallow repository"
    )
    head_sha = _git(shallow, "rev-parse", "HEAD")

    assert is_shallow(shallow) is True
    assert resolve_rollout_commit(shallow, head_sha, epoch=_ARBITRARY_EPOCH) is None


def test_resolve_rollout_commit_none_when_gits_before_answer_postdates_cutoff(tmp_path, monkeypatch):
    """Defense-in-depth: even if git's own ``--before`` parse somehow resolved
    to a commit whose real committer time postdates the cutoff (a hostile or
    buggy git build), the committer-time re-verification in Python must
    refuse to trust it rather than grant grace off an unverified answer.

    Lives here, not in a family test file — this is the shared primitive's
    own contract, and both family wrappers rely on it identically (code
    review, low: `iterate-2026-09-20-shared-rollout-commit-resolver`)."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "post")
    head_sha = _commit_at(root, "post", _AFTER)

    import tools.verifiers._rollout_resolution as rollout_mod
    real_run_git = rollout_mod._run_git

    def _lying_rev_list(project_root, *args, **kwargs):
        if args[:1] == ("rev-list",):
            return 0, head_sha, ""  # lies: claims head_sha is "before" the cutoff
        return real_run_git(project_root, *args, **kwargs)

    monkeypatch.setattr(rollout_mod, "_run_git", _lying_rev_list)
    assert resolve_rollout_commit(root, head_sha, epoch=_ARBITRARY_EPOCH) is None


def test_resolve_rollout_commit_none_for_a_non_int_epoch(tmp_path):
    """A malformed ``epoch`` (not a genuine int) is refused up front rather
    than propagating into either an approxidate-misparse hazard or a raised
    ``TypeError`` out of a function documented as never-raising (code
    review, low)."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "only commit")
    sha = _commit_at(root, "only commit", _AT)

    assert resolve_rollout_commit(root, sha, epoch="") is None  # type: ignore[arg-type]
    assert resolve_rollout_commit(root, sha, epoch=True) is None  # bool is an int subclass


def test_resolve_rollout_commit_none_for_empty_commit_hash(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "pre")
    _commit_at(root, "pre", _BEFORE)

    assert resolve_rollout_commit(root, "", epoch=_ARBITRARY_EPOCH) is None


def test_resolve_rollout_commit_refuses_a_forged_unmerged_branch_commit(tmp_path):
    """`trg-4380c61a`: a contributor controls every commit on their own
    branch, including `GIT_COMMITTER_DATE` — so a backdated, never-merged
    commit must NOT qualify merely because it carries an early date."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "trunk content")
    trunk_sha = _commit_at(root, "genuine pre-epoch trunk commit", _BEFORE)

    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "f.txt", "forged content")
    forged_sha = _commit_at(root, "forged, unmerged commit", _BEFORE, on_trunk=False)

    assert resolve_rollout_commit(root, forged_sha, epoch=_ARBITRARY_EPOCH) is None
    # Genuine trunk content is unaffected by the trust-anchor check.
    assert resolve_rollout_commit(root, trunk_sha, epoch=_ARBITRARY_EPOCH) == trunk_sha


def test_resolve_rollout_commit_none_without_a_corroborated_trunk_anchor(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _git(root, "checkout", "-q", "-b", "not-a-trunk-name")
    _write(root, "f.txt", "pre")
    head_sha = _commit_at(root, "pre, no anchor", _BEFORE, on_trunk=False)

    assert resolve_rollout_commit(root, head_sha, epoch=_ARBITRARY_EPOCH) is None


def test_resolve_rollout_commit_is_epoch_parameterised_not_hardcoded(tmp_path):
    """The same commit resolves — or not — purely as a function of the
    caller-supplied `epoch`, never a module-level constant: this is the
    property the extraction exists to prove (each family keeps its OWN
    rollout instant, only the mechanism is shared)."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, "f.txt", "only commit")
    sha = _commit_at(root, "only commit", _AT)

    assert resolve_rollout_commit(root, sha, epoch=_ARBITRARY_EPOCH) == sha
    # A strictly earlier caller-supplied epoch excludes the SAME commit.
    assert resolve_rollout_commit(root, sha, epoch=_ARBITRARY_EPOCH - 1) is None
