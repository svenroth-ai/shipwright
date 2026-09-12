"""Shared git-repo fixture builders for the local-preflight test modules.

`test_pr_review_local_diff.py` (pure `pr_review_local` functions) and
`test_pr_review_local_preflight.py` (`pr_review.main()` orchestration) are
separate modules only because one file carrying both crossed the source-size
guideline. They describe one subject, so the fixture lives in one place —
same pattern as `_pr_review_fixtures.py` for the stale-verdict test modules.

Not `conftest.py`: that module owns the source-tree pollution guards, and
this is a plain builder rather than a pytest fixture.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__ = ["FAKE_KEY", "_GIT_ENV", "_git", "_git_init_only", "_repo_with_branch_history"]

FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), env=_GIT_ENV,
                   capture_output=True, text=True, check=True)


def _git_init_only(root: Path) -> None:
    """A minimal repo with one commit and no `origin` remote — enough to make
    `git merge-base <ref> HEAD` fail cleanly on an unresolvable `<ref>`."""
    _git(root, "init", "-q", "-b", "main")
    (root / "f.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")


def _repo_with_branch_history(root: Path) -> None:
    """base(main) -> commit on main -> checkout a feature branch, add an
    untracked file. Mirrors an iterate branch that has diverged from a
    `--base` ref that has ALSO moved — so a naive "diff against the ref's
    tip" would misattribute the main-only commit to the feature branch."""
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    (root / "shared.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    (root / "feature.py").write_text("def feature():\n    return 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feature work")
    # main moves AFTER the branch point — must not leak into the diff.
    _git(root, "checkout", "-q", "main")
    (root / "shared.py").write_text("def a():\n    return 1\n\ndef b():\n    return 2\n",
                                    encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "unrelated main-only change")
    _git(root, "checkout", "-q", "feature")
    # An UNTRACKED file — never `git add`-ed. Constraint (5): must still show up.
    (root / "untracked.py").write_text("def never_added():\n    return 3\n", encoding="utf-8")
