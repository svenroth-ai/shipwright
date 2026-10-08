"""Shared by the ``check_rtm_coverage`` tests: a hermetic git environment and repo helpers.

Any inherited ``GIT_*`` variable (``GIT_DIR`` / ``GIT_WORK_TREE`` / ``GIT_INDEX_FILE``
from a git hook or a worktree pipeline, ``GIT_CONFIG_*`` injections, ...) or the
developer's system / global config would point the hook's index / ``HEAD`` read
somewhere other than the test's ``tmp_path``; every ``GIT_*`` is dropped, system and
global config are switched off and discovery is capped above ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

REL = Path(".shipwright") / "compliance" / "test-traceability.json"


def _hermetic(tmp_root: Path) -> dict[str, str]:
    return {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CEILING_DIRECTORIES": str(Path(tmp_root).resolve().parent)}


def _dropped(name: str) -> bool:
    return name.startswith("GIT_") or name == "SHIPWRIGHT_PROJECT_ROOT"


def hook_env(tmp_root: Path) -> dict[str, str]:
    """``os.environ`` minus every ``GIT_*`` (and the project-root override), git-hermetic.

    *tmp_root* is the test's ``tmp_path``: git discovery stops above it.
    """
    env = {k: v for k, v in os.environ.items() if not _dropped(k)}
    return {**env, **_hermetic(tmp_root)}


@pytest.fixture(autouse=True)
def scrub_git_env(monkeypatch, tmp_path):
    """Autouse wherever imported: in-process git reads see ``tmp_path``, not the caller's repo."""
    for name in [k for k in os.environ if _dropped(k)]:
        monkeypatch.delenv(name, raising=False)
    for name, value in _hermetic(tmp_path).items():
        monkeypatch.setenv(name, value)


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
    """``git -C <root>``; *root* is the test's ``tmp_path`` (the repo root)."""
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env=hook_env(root), timeout=30)


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "core.hooksPath", str(root / ".no-hooks"))


def commit_all(root: Path) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "manifest")
