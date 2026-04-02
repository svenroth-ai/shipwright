#!/usr/bin/env python3
"""Validate deployment prerequisites.

Usage:
    uv run validate-deploy.py [--project-root <path>]

Output (JSON):
    {
        "success": true/false,
        "jelastic_token": true/false,
        "supabase_token": true/false,
        "supabase_linked": true/false,
        "has_migrations": true/false,
        "git_remote": "origin" | null,
        "warnings": [],
        "errors": []
    }
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _has_migrations(project_root: Path) -> bool:
    """Check if supabase/migrations/ contains any forward .sql files."""
    migrations_dir = project_root / "supabase" / "migrations"
    if not migrations_dir.is_dir():
        return False
    for f in migrations_dir.iterdir():
        if f.is_file() and f.suffix == ".sql" and not f.name.startswith("."):
            return True
    return False


def _is_supabase_linked(project_root: Path) -> bool:
    """Check if supabase project is linked (config.toml + .supabase/ exist)."""
    has_config = (project_root / "supabase" / "config.toml").exists()
    has_link = (project_root / ".supabase").is_dir()
    return has_config and has_link


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deployment prerequisites")
    parser.add_argument("--project-root", help="Path to project root")
    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    warnings: list[str] = []
    errors: list[str] = []

    jelastic_token = bool(os.environ.get("JELASTIC_TOKEN"))
    supabase_token = bool(os.environ.get("SUPABASE_ACCESS_TOKEN"))
    has_migrations = _has_migrations(project_root)
    supabase_linked = _is_supabase_linked(project_root)

    if not jelastic_token:
        errors.append("JELASTIC_TOKEN not set — deployment will fail")

    if has_migrations and not supabase_token:
        errors.append(
            "SUPABASE_ACCESS_TOKEN not set — required because supabase/migrations/ "
            "contains migration files. Get token at: https://supabase.com/dashboard/account/tokens"
        )
    elif not has_migrations and not supabase_token:
        warnings.append("SUPABASE_ACCESS_TOKEN not set — migrations will be skipped (no migrations found)")

    if has_migrations and not supabase_linked:
        errors.append(
            "Supabase project not linked — run 'supabase init' and 'supabase link --project-ref <ref>' first"
        )

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

    success = jelastic_token and len(errors) <= (0 if has_migrations else 1)
    # If only issue is missing Jelastic token, that's always a failure
    # If migrations exist and supabase isn't set up, that's also a failure
    success = len(errors) == 0

    print(json.dumps({
        "success": success,
        "jelastic_token": jelastic_token,
        "supabase_token": supabase_token,
        "supabase_linked": supabase_linked,
        "has_migrations": has_migrations,
        "git_remote": git_remote,
        "warnings": warnings,
        "errors": errors,
    }, indent=2))

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
