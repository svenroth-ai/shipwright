"""Shared by the ``check_rtm_coverage`` tests: a clean git environment and repo helpers.

An inherited ``GIT_DIR`` / ``GIT_WORK_TREE`` / ``GIT_INDEX_FILE`` (a test run from a
git hook, or inside a worktree pipeline) would point the hook's index / ``HEAD``
read at the developer's repository instead of the test's ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

GIT_ENV_DROP = ("SHIPWRIGHT_PROJECT_ROOT", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
REL = Path(".shipwright") / "compliance" / "test-traceability.json"


def hook_env() -> dict[str, str]:
    """``os.environ`` without the variables that would redirect the hook or its git."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_DROP}


@pytest.fixture(autouse=True)
def scrub_git_env(monkeypatch):
    """Autouse wherever imported: in-process git reads see ``tmp_path``, not the caller's repo."""
    for name in GIT_ENV_DROP:
        monkeypatch.delenv(name, raising=False)


def collector_manifest(passing: int, total: int, *, executed_rest="not_run",
                       schema_version=4, generated_at=None, source_commit="a" * 40):
    """A collector-shaped (``test_links/1.0.0``) manifest: *passing* of *total* FRs pass."""
    reqs = {}
    for i in range(total):
        fr = f"FR-01.{i:02d}"
        link = {"id": f"plugins/x/tests/test_x.py::test_{i}",
                "path": f"plugins/x/tests/test_x.py::test_{i}", "layer": "unit",
                "status": "enabled", "executed": "pass" if i < passing else executed_rest,
                "tag_source": "pytest_marker", "ac_id": "AC01"}
        reqs[f"01::{fr}"] = {
            "id": fr, "spec_path": ".shipwright/planning/01-adopted/spec.md",
            "title": f"req {i}", "priority": "Must", "status": "active",
            "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
            "tests": {"unit": [link]}, "acs": {"AC01": {"tests": {"unit": [dict(link)]}}},
        }
    return {
        "schema_version": schema_version, "collector_version": "test_links/1.0.0",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit, "spec_hash": "sha256:" + "0" * 64,
        "requirements": reqs, "orphans": [], "invalid_tags": [], "invalid_layers": [],
        "untagged_tests": [],
    }


def write_manifest(root: Path, manifest: dict) -> None:
    path = root / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env=hook_env(), timeout=30)


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "core.hooksPath", str(root / ".no-hooks"))


def commit_all(root: Path) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "manifest")
