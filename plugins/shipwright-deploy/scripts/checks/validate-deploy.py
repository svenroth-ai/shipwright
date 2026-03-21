#!/usr/bin/env python3
"""Validate deployment prerequisites.

Usage:
    uv run validate-deploy.py

Output (JSON):
    {
        "success": true/false,
        "jelastic_token": true/false,
        "supabase_token": true/false,
        "git_remote": "origin" | null,
        "warnings": []
    }
"""

import json
import os
import subprocess
import sys


def main() -> int:
    warnings: list[str] = []

    jelastic_token = bool(os.environ.get("JELASTIC_TOKEN"))
    supabase_token = bool(os.environ.get("SUPABASE_ACCESS_TOKEN"))

    if not jelastic_token:
        warnings.append("JELASTIC_TOKEN not set — deployment will fail")

    if not supabase_token:
        warnings.append("SUPABASE_ACCESS_TOKEN not set — migrations will be skipped")

    # Check git remote
    git_remote = None
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode == 0:
            git_remote = result.stdout.strip()
    except (FileNotFoundError, OSError):
        warnings.append("git not available")

    success = jelastic_token  # Minimum requirement

    print(json.dumps({
        "success": success,
        "jelastic_token": jelastic_token,
        "supabase_token": supabase_token,
        "git_remote": git_remote,
        "warnings": warnings,
    }, indent=2))

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
