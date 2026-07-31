"""Shared helpers for the compliance-evidence refresh tests.

Three test modules need the same seeded repository
(iterate-2026-07-31-derived-docs-at-release). The constants and the seeding
function live here, matching ``_c3_fixtures`` and the other ``_*_fixtures``
helpers in this directory.

The pytest FIXTURE is declared in each test module rather than shared from here,
and neither obvious alternative works: importing a fixture by NAME and then
taking it as a test parameter shadows the import (ruff F811), and putting the
body in ``conftest.py`` ratchets that file past its bloat baseline. Four
four-line declarations is the cheap answer; :func:`seed_repo` keeps the actual
seeding in one place, which is what would have been worth sharing anyway.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from source_state import SourceState, banner_line  # noqa: E402

#: Names no commit in the seeded repo — used where the base must be unresolvable.
BASE = "dcf85f874e8e528e9961f3d4d615a8a7c8dfee4b"
DASHBOARD = ".shipwright/compliance/dashboard.md"
RUN = "iterate-2026-07-31-derived-docs-at-release"

__all__ = ["BASE", "DASHBOARD", "RUN", "all_ok", "git", "head_sha", "seed_repo"]


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """A git call carrying its own committer identity — a CI runner has none."""
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Refresh Test", "GIT_AUTHOR_EMAIL": "t@test.invalid",
        "GIT_COMMITTER_NAME": "Refresh Test", "GIT_COMMITTER_EMAIL": "t@test.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, encoding="utf-8", env=env,
    )


def head_sha(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def all_ok() -> dict[str, str]:
    """Every producer leg reporting success."""
    return {rel: "regenerated" for rel in sorted(REFRESH_SET)}


def seed_repo(root: Path) -> Path:
    """Initialise ``root`` with all seven paths committed, carrying real content.

    Plausible content matters: the content floor compares against ``HEAD``, so a
    seed of a few bytes would let an emptied document pass and the floor tests
    would prove nothing.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    banner = banner_line(SourceState(run_id=RUN))
    for rel in sorted(REFRESH_SET):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            path.write_text(json.dumps({"rows": ["x"] * 40}), encoding="utf-8")
        else:
            header = f"# {Path(rel).stem}\n\nGenerated: 2026-07-01\n{banner}\n\n"
            path.write_text(header + "row\n" * 40, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-m", "seed")
    return root
