"""Real-git tests for the FR-01.02 #5/#10 rollout-transition grace's commit
resolution (:mod:`_project_gate_rollout`), `trg-9583d3a8`. Mirrors
``test_layer_coverage_rollout.py``'s pattern (its own precedent's git-history
tests) — since this module's whole purpose is asking a repo's OWN git
ancestry a wall-clock question, a purely synthetic test cannot exercise the
resolution itself.

Commit dates are pinned via ``GIT_AUTHOR_DATE``/``GIT_COMMITTER_DATE`` with an
explicit UTC offset so the test is immune to the runner's timezone;
``commit.gpgsign=false`` is set per-repo so a developer machine with commit
signing enabled cannot hang or fail these commits.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._project_gate_rollout import (  # noqa: E402
    GATE_ROLLOUT_AT_EPOCH,
    cached_rollout_sha,
    clear_rollout_sha_cache,
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


def _commit_at(root: Path, msg: str, iso_date: str) -> str:
    _git(root, "add", "-A")
    proc = subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", msg],
        capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git commit failed: {proc.stderr}")
    return _git(root, "rev-parse", "HEAD")


_BEFORE_ROLLOUT = "2026-09-06T00:00:00+00:00"
_AT_ROLLOUT = "2026-09-12T06:23:06+00:00"  # == GATE_ROLLOUT_AT_EPOCH, to the second
_AFTER_ROLLOUT = "2026-09-13T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_rollout_sha_cache()
    yield
    clear_rollout_sha_cache()


def test_gate_rollout_epoch_matches_the_documented_boundary_instant():
    import datetime
    boundary = datetime.datetime.fromisoformat(_AT_ROLLOUT)
    assert int(boundary.timestamp()) == GATE_ROLLOUT_AT_EPOCH


def test_resolve_head_sha_resolves_head_to_a_concrete_sha(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "a.txt", "x")
    head_sha = _commit_at(root, "c1", _BEFORE_ROLLOUT)
    assert resolve_head_sha(root, "HEAD") == head_sha


def test_resolve_head_sha_none_on_an_unresolvable_ref(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, "a.txt", "x")
    _commit_at(root, "c1", _BEFORE_ROLLOUT)
    assert resolve_head_sha(root, "not-a-real-ref") is None


def test_resolve_rollout_commit_finds_a_commit_strictly_before_cutoff(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", "pre")
    pre_sha = _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", "post")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    resolved = resolve_rollout_commit(root, head_sha)
    assert resolved == pre_sha


def test_resolve_rollout_commit_accepts_a_commit_exactly_at_the_boundary_instant(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", "pre")
    boundary_sha = _commit_at(root, "at boundary", _AT_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", "post")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    resolved = resolve_rollout_commit(root, head_sha)
    assert resolved == boundary_sha


def test_resolve_rollout_commit_none_when_repo_born_entirely_after_rollout(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", "pre")
    head_sha = _commit_at(root, "born after rollout", _AFTER_ROLLOUT)

    assert resolve_rollout_commit(root, head_sha) is None


def test_resolve_rollout_commit_none_for_a_shallow_clone(tmp_path):
    origin = tmp_path / "origin"
    _init(origin)
    _write(origin, ".shipwright/planning/app/spec.md", "pre")
    _commit_at(origin, "pre-rollout", _BEFORE_ROLLOUT)
    _write(origin, ".shipwright/planning/app/spec.md", "post")
    _commit_at(origin, "post-rollout", _AFTER_ROLLOUT)

    # Only a `file://` URL forces git through the real network-clone code path
    # that honours `--depth` (a same-machine PATH clone takes git's local-clone
    # fast path and copies full history regardless) — asserted below rather
    # than assumed, per the identical precedent in test_layer_coverage_rollout.py.
    shallow = tmp_path / "shallow"
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", origin.as_uri(), str(shallow)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    is_shallow = _git(shallow, "rev-parse", "--is-shallow-repository")
    assert is_shallow == "true", "clone did not actually produce a shallow repository"
    head_sha = _git(shallow, "rev-parse", "HEAD")

    assert resolve_rollout_commit(shallow, head_sha) is None


def test_resolve_rollout_commit_none_for_empty_commit_hash(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", "pre")
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)

    assert resolve_rollout_commit(root, "") is None


def test_resolve_rollout_commit_none_when_gits_before_answer_postdates_cutoff(tmp_path, monkeypatch):
    """Defense-in-depth: even if git's own ``--before`` parse somehow resolved
    to a commit whose real committer time postdates the cutoff (a hostile or
    buggy git build), the committer-time re-verification in Python must
    refuse to trust it rather than grant grace off an unverified answer."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", "post")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    import tools.verifiers._project_gate_rollout as rollout_mod
    real_run_git = rollout_mod._run_git

    def _lying_rev_list(project_root, *args, **kwargs):
        if args[:1] == ("rev-list",):
            return 0, head_sha, ""  # lies: claims head_sha is "before" the cutoff
        return real_run_git(project_root, *args, **kwargs)

    monkeypatch.setattr(rollout_mod, "_run_git", _lying_rev_list)
    assert resolve_rollout_commit(root, head_sha) is None


def test_cached_rollout_sha_caches_by_root_and_commit(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", "pre")
    pre_sha = _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", "post")
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    first = cached_rollout_sha(root, head_sha)
    assert first == pre_sha

    import tools.verifiers._project_gate_rollout as rollout_mod
    def _boom(*_a, **_kw):
        raise AssertionError("resolve_rollout_commit should not run again on a cache hit")
    monkeypatch.setattr(rollout_mod, "resolve_rollout_commit", _boom)

    second = cached_rollout_sha(root, head_sha)
    assert second == first
