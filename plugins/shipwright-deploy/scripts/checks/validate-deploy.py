#!/usr/bin/env python3
"""Validate deployment prerequisites.

Usage:
    uv run validate-deploy.py [--project-root <path>] [--confirm-failing-tests]

Output (JSON):
    {
        "success": true/false,
        "jelastic_token": true/false,
        "supabase_token": true/false,
        "supabase_linked": true/false,
        "has_migrations": true/false,
        "git_remote": "origin" | null,
        "test_gate": "passed" | "failing-unconfirmed" | "failing-confirmed" | "no-results",
        "warnings": [],
        "errors": []
    }

FR-01.08 criterion 1: a release is refused on failing tests until a person
confirms. ``evaluate_test_gate`` (``../lib/test_gate.py``) reads the same
fields shipwright-deploy's own SKILL.md Step B4 documents (``unit.status`` /
``e2e.status``) so both sides describe one rule; it also backs the coded
refusal in ``release.py``, so both callers read the identical oracle rather
than two independently-maintained copies. A person's confirmation reaches
this script ONLY via ``--confirm-failing-tests`` — never inferred from an
environment variable or a config default, so the refusal cannot be silenced
by anything but the flag the SKILL.md sets after its own ``AskUserQuestion``.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ``test_gate.py`` lives in the plugin's own scripts/lib/, a sibling of
# scripts/checks/ (this file's own directory) — added to sys.path explicitly
# rather than as a package import, matching how the rest of this plugin's
# scripts resolve plugin-local modules (rollback.py's own _SHARED_SCRIPTS
# shim is the same pattern one level up).
_LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from test_gate import evaluate_test_gate  # noqa: E402


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
    parser.add_argument(
        "--confirm-failing-tests", action="store_true",
        help="A person has explicitly confirmed deploying despite failing/missing tests",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    warnings: list[str] = []
    errors: list[str] = []

    jelastic_token = bool(os.environ.get("JELASTIC_TOKEN"))
    supabase_token = bool(os.environ.get("SUPABASE_ACCESS_TOKEN"))
    has_migrations = _has_migrations(project_root)
    supabase_linked = _is_supabase_linked(project_root)
    test_gate, test_gate_error = evaluate_test_gate(project_root, args.confirm_failing_tests)

    if test_gate_error:
        errors.append(test_gate_error)
    elif test_gate == "no-results":
        warnings.append(
            "shipwright_test_results.json not found — deploying without test "
            "verification, confirmed by a person (--confirm-failing-tests)"
        )
    elif test_gate == "failing-confirmed":
        warnings.append("deploying with failing tests — confirmed by a person (--confirm-failing-tests)")

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

    success = len(errors) == 0

    print(json.dumps({
        "success": success,
        "jelastic_token": jelastic_token,
        "supabase_token": supabase_token,
        "supabase_linked": supabase_linked,
        "has_migrations": has_migrations,
        "git_remote": git_remote,
        "test_gate": test_gate,
        "warnings": warnings,
        "errors": errors,
    }, indent=2))

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
