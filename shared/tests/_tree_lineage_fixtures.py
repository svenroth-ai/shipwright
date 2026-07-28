"""Real-git fixtures for the ``tree_lineage`` tests
(iterate-2026-07-28-grade-snapshot-lineage).

Shared by ``test_tree_lineage.py`` (what git says) and
``test_tree_lineage_degradation.py`` (what happens when it cannot say). The
subject under test is "what does git actually report here", so these build
**real repositories**: the failure modes that mattered in review — a ``master``
default, a detached HEAD, an unobtainable merge-base — are precisely the ones a
mocked ``subprocess`` would have answered wrongly and confidently.

Underscore-prefixed so pytest imports it as a helper rather than collecting it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    """Run git in ``root``, raising with git's own stderr on failure."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def commit(root: Path, name: str, body: str = "x") -> str:
    (root / name).write_text(body, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-m", f"add {name}")
    return git(root, "rev-parse", "HEAD")


def init_repo(root: Path, branch: str = "main") -> Path:
    """A repo with one commit on ``branch``, with identity and signing pinned so
    the fixture never depends on the developer's global git config."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", branch)
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "fixture")
    git(root, "config", "commit.gpgsign", "false")
    commit(root, "one.txt", "1")
    return root


def ancestry_blinded(monkeypatch, root: Path):
    """Resolve ``root`` with ``merge-base --is-ancestor`` forced to error.

    Exit 128 is git's "could not tell" (a shallow clone with truncated history,
    an unreadable object) — distinct from exit 1, "genuinely not an ancestor".
    Every other git call still runs for real, so this isolates exactly the one
    answer the resolver has to cope with losing.
    """
    import tree_lineage

    real = tree_lineage.subprocess.run

    def _fake(cmd, *a, **k):
        if "merge-base" in cmd and "--is-ancestor" in cmd:
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: bad object")
        return real(cmd, *a, **k)

    monkeypatch.setattr(tree_lineage.subprocess, "run", _fake)
    return tree_lineage.resolve_tree_lineage(root)
