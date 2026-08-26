#!/usr/bin/env python3
"""Setup changelog session — analyze git state.

Usage:
    uv run setup-changelog.py --plugin-root <path>

Output (JSON):
    {
        "success": true/false,
        "last_tag": "v0.1.0" | null,
        "commits_since_tag": 15,
        "branch": "main",
        "has_unreleased": true,
        "previous_tag_has_release": true | false | null
    }

``previous_tag_has_release`` is a tri-state ADVISORY, never a gate: whether the
immediately preceding tag has a GitHub Release. ``null`` means not checkable
(no previous tag, ``gh`` missing/unauthenticated, or an indeterminate ``gh``
failure) — treated as "nothing to report", not as "missing". A definite
``false`` is what the calling skill surfaces as a one-line notice, so a
release note that silently failed or was skipped (Step 7 is itself
best-effort) surfaces once, at the next release, rather than never. See
`references/release-workflow.md`.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.git_utils import get_commits_since, get_current_branch, get_last_tag

# parents[0]=checks, [1]=scripts, [2]=shipwright-changelog, [3]=plugins, [4]=repo_root.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from repo_identity import resolve_repo_identity  # noqa: E402


def _check_previous_release(project_root: Path, last_tag: str | None) -> bool | None:
    if not last_tag:
        return None
    try:
        version = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if version.returncode != 0:
        return None

    repo_identity = resolve_repo_identity(project_root)
    if not repo_identity:
        return None

    try:
        view = subprocess.run(
            ["gh", "release", "view", last_tag, "--repo", repo_identity, "--json", "url"],
            capture_output=True, text=True, timeout=15.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if view.returncode == 0:
        return True
    stderr = (view.stderr or "").lower()
    if "release not found" in stderr or "404" in stderr:
        return False
    return None  # indeterminate (auth/network/API error) — advisory, not a gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup changelog session")
    parser.add_argument("--plugin-root", required=True)
    parser.parse_args()

    last_tag = get_last_tag()
    commits = get_commits_since(last_tag)
    branch = get_current_branch()

    result = {
        "success": True,
        "last_tag": last_tag,
        "commits_since_tag": len(commits),
        "branch": branch,
        "has_unreleased": len(commits) > 0,
        "previous_tag_has_release": _check_previous_release(Path.cwd(), last_tag),
        "message": f"{len(commits)} commits since {last_tag or 'beginning'}",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
