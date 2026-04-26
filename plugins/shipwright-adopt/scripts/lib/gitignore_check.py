"""Classify a list of paths against the project's `.gitignore`.

Used by /shipwright-adopt to surface a "GITIGNORED OUTPUTS" block in the
handoff: if a substantial fraction of adopt-generated artifacts (e.g.
agent_docs/, planning/, shipwright_*_config.json) are gitignored, the
user discovers it only at `git status` after Adopt finishes — too late
for the adoption commit. We catch it during Step E and prompt the user.

Implementation uses `git check-ignore --no-index` per path so the
project's full gitignore semantics (negations, nested files, etc.) are
honored.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def check_paths_against_gitignore(
    project_root: Path,
    rel_paths: list[str],
    *,
    majority_threshold: float = 0.5,
) -> dict[str, Any]:
    """Return a classification dict.

    Output:
        {
          "total": N,
          "gitignored": [paths that match a gitignore rule],
          "majority_gitignored": bool,  # True if >= majority_threshold are ignored
        }

    Paths are evaluated as STRINGS (no need for the file to exist on
    disk yet — adopt is checking what would happen IF it wrote them).
    """
    gitignored: list[str] = []
    for rel in rel_paths:
        try:
            r = subprocess.run(
                ["git", "-C", str(project_root), "check-ignore", "--no-index", rel],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
        # check-ignore returns 0 when the path IS ignored, 1 when not, 128 on errors
        if r.returncode == 0:
            gitignored.append(rel)

    total = len(rel_paths)
    ratio = (len(gitignored) / total) if total else 0.0
    return {
        "total": total,
        "gitignored": gitignored,
        "majority_gitignored": ratio >= majority_threshold and total > 0,
    }
