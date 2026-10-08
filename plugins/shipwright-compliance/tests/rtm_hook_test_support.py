"""Shared by the ``check_rtm_coverage`` hook tests: the environment a hook subprocess gets.

An inherited ``GIT_DIR`` / ``GIT_WORK_TREE`` / ``GIT_INDEX_FILE`` (a test run from a
git hook, or inside a worktree pipeline) would point the hook's ``git show HEAD:``
at the developer's repository instead of the test's ``tmp_path``.
"""

from __future__ import annotations

import os

GIT_ENV_DROP = ("SHIPWRIGHT_PROJECT_ROOT", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")


def hook_env() -> dict[str, str]:
    """``os.environ`` without the variables that would redirect the hook or its git."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_DROP}
