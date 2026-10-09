"""Shared by the git-side coverage-gate tests: real temp repos and the real ``pre-commit``."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


if str(Path(__file__).parent) not in sys.path:  # sibling support module
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import (  # noqa: E402, F401 - scrub_git_env is autouse
    REL,
    collector_manifest as _collector_manifest,
    git,
    hook_env,
    init_repo,
    scrub_git_env,
    write_manifest,
)

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / "scripts" / "hooks"
LIB = REPO / "plugins" / "shipwright-compliance" / "scripts" / "lib"
SCRIPT_DIR = REPO / "plugins" / "shipwright-compliance" / "scripts" / "hooks"
LOG = Path(".shipwright/agent_docs/compliance_overrides.log")
BLOCKED = "BLOCKED (check_rtm_coverage, git pre-commit)"


def collector_manifest(passing: int, total: int = 2, **kw):
    """Uncovered requirements FAIL (a not_run one would be "not measured", not uncovered)."""
    kw.setdefault("executed_rest", "fail")
    return _collector_manifest(passing, total, **kw)


def make_repo(tmp_path):
    """A repo whose HEAD holds a covered (2/2) manifest, hooks installed afterwards."""
    init_repo(tmp_path)
    write_manifest(tmp_path, collector_manifest(2, 2))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "config", "core.hooksPath", str(HOOKS))
    return tmp_path


def commit(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "x", *args],
                          capture_output=True, text=True, env=hook_env(root), timeout=120)


def stage_manifest(root: Path, passing: int, total: int = 2, **kw) -> None:
    write_manifest(root, collector_manifest(passing, total, **kw))
    git(root, "add", str(REL))


def head_count(root: Path) -> int:
    out = subprocess.run(["git", "-C", str(root), "rev-list", "--count", "HEAD"],
                         capture_output=True, text=True, env=hook_env(root), check=True)
    return int(out.stdout)


def log_override(root: Path, hook: str = "check_rtm_coverage") -> None:
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} | {hook} | OVERRIDE | operator said continue\n")


def release_token(root: Path, hook: str = "check_rtm_coverage"):
    """What the PreToolUse hook does on an override release: log, consume, then grant."""
    sys.path.insert(0, str(LIB))
    try:
        import compliance_override
        import git_side_release
    finally:
        sys.path.remove(str(LIB))
    log_override(root, hook)
    found, why = compliance_override.try_release(root, hook)
    assert found is not None, why
    assert git_side_release.grant(root, hook, found.at) is None
    return found
