"""Trust-anchor tests for `resolve_rollout_commit` (`trg-4380c61a`), split
from ``test_layer_coverage_rollout.py`` at the 300-LOC guideline. Mirrors
``test_project_gate_rollout.py``'s identical trust-anchor test pair for its
own sibling gate family — since a committer-date claim alone is forgeable by
whoever controls the candidate commit, both modules now require the same
corroborated-trunk-ancestry check (``git_helpers._branch_base_commit``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_rollout import (  # noqa: E402
    clear_rollout_cache,
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
    already merged", the trust anchor ``resolve_rollout_commit`` now requires
    (`trg-4380c61a`). Pass ``on_trunk=False`` to build a commit that exists
    only on the local branch, unreachable from that anchor — e.g. an open
    PR's own unmerged commit."""
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


_BEFORE_ROLLOUT = "2026-09-06T00:00:00+00:00"

_SPEC_PRE = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-09.30 | Pre-rollout requirement | Should | unit |\n"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_rollout_cache()
    yield
    clear_rollout_cache()


def test_resolve_rollout_commit_refuses_a_forged_unmerged_branch_commit(tmp_path):
    """A contributor controls every commit on their own branch, including
    ``GIT_COMMITTER_DATE`` — so a backdated, never-merged commit on that
    branch must NOT qualify for grace merely because it carries an early
    date. The genuine trunk commit is built on ``main`` (tracked via
    ``on_trunk=True``, the default — standing in for "already merged"); the
    forged commit sits on a separate, never-merged branch
    (``on_trunk=False``), reproducing an open PR whose own HEAD carries a
    backdated commit no reviewer or CI ever saw on trunk."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    trunk_sha = _commit_at(root, "genuine pre-rollout trunk commit", _BEFORE_ROLLOUT)

    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE.replace("unit", "unit, e2e"))
    forged_sha = _commit_at(
        root, "forged, unmerged commit", _BEFORE_ROLLOUT, on_trunk=False,
    )

    assert resolve_rollout_commit(root, forged_sha) is None
    # Genuine trunk content is unaffected by the new check.
    assert resolve_rollout_commit(root, trunk_sha) == trunk_sha


def test_resolve_rollout_commit_none_without_a_corroborated_trunk_anchor(tmp_path):
    """No ``origin`` remote, and the local branch name matches none of the
    trunk candidates — there is nothing to verify ancestry against, so this
    degrades to "no grace" (the same fail-closed direction as a shallow
    clone or a git failure), never to trusting the committer-date claim
    alone."""
    root = tmp_path / "repo"
    _init(root)
    _git(root, "checkout", "-q", "-b", "not-a-trunk-name")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    head_sha = _commit_at(root, "pre-rollout, no anchor", _BEFORE_ROLLOUT, on_trunk=False)

    assert resolve_rollout_commit(root, head_sha) is None
