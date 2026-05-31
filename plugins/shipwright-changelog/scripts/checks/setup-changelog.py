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
        "has_unreleased": true
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.git_utils import get_commits_since, get_current_branch, get_last_tag


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
        "message": f"{len(commits)} commits since {last_tag or 'beginning'}",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
