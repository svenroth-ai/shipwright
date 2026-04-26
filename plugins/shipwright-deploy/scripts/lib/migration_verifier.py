#!/usr/bin/env python3
"""Post-apply migration verification.

Replit-pattern adopt (Sub-Iterate B): every migration written under the
new convention carries one or more `-- VERIFY: <SQL>` comments. After
applying a migration to a target database, this module parses those
blocks, runs each VERIFY SQL via psql, and reports whether all
verifications passed.

The verifier itself never invokes rollback — it returns the failure
signal (`all_passed=False`) which `shipwright-deploy/skills/deploy/SKILL.md`
then uses to enter the existing rollback path. This keeps the verifier
free of jelastic_client coupling and trivially testable.

Backwards-compat: migrations without a `-- VERIFY:` block are reported
as `skipped=True, all_passed=True` so legacy migrations (and migrations
where the author opted out) never break a deploy.

Usage:
    uv run scripts/lib/migration_verifier.py \\
        --migration supabase/migrations/20260426_add_theme.sql \\
        [--migration ...] \\
        [--db-url postgres://...] \\
        [--dry-run] \\
        [--output report.json]

Exit codes: 0 if every migration passed (or was skipped), 1 if any
verification failed. The deploy SKILL branches on this.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# `-- VERIFY: <sql>` — case-sensitive marker. Allows leading whitespace
# and arbitrary SQL after the marker. Each verify block is one line.
VERIFY_PATTERN = re.compile(r"^[ \t]*--\s*VERIFY:\s*(.+?)\s*$", re.MULTILINE)

VERIFY_TIMEOUT_SECONDS = 30


def parse_verify_blocks(sql_text: str) -> list[str]:
    """Extract every `-- VERIFY: <SQL>` line from migration text.

    Returns the SQL bodies in source order. Empty list when no markers
    are present (this is the backwards-compat path — caller should treat
    it as "skip verification, do not fail").
    """
    return [match.strip() for match in VERIFY_PATTERN.findall(sql_text) if match.strip()]


def run_verification(
    verify_sql: str,
    db_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run a single VERIFY SQL via psql and report the outcome.

    Verification semantics:
    - psql exits non-zero  → verified=False (CLI/syntax/connection error)
    - empty stdout         → verified=False (no evidence of post-state)
    - stdout in {f, false, 0} → verified=False (explicit failure assertion)
    - anything else        → verified=True

    The SQL is treated as read-only by convention; the verifier does not
    enforce it (psql does), but generated migrations should only use
    SELECT / EXPLAIN / function-call statements that do not mutate state.
    """
    if dry_run:
        return {
            "verified": True,
            "sql": verify_sql,
            "stdout": "[dry-run]",
            "stderr": "",
            "returncode": 0,
        }

    cmd: list[str] = ["psql"]
    if db_url:
        cmd.append(db_url)
    cmd.extend(["-At", "-c", verify_sql])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "verified": False,
            "sql": verify_sql,
            "stdout": "",
            "stderr": f"Verification timed out (>{VERIFY_TIMEOUT_SECONDS}s)",
            "returncode": -1,
        }
    except FileNotFoundError:
        return {
            "verified": False,
            "sql": verify_sql,
            "stdout": "",
            "stderr": "psql not found on PATH",
            "returncode": -2,
        }

    if proc.returncode != 0:
        return {
            "verified": False,
            "sql": verify_sql,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }

    out_stripped = proc.stdout.strip()
    if not out_stripped:
        return {
            "verified": False,
            "sql": verify_sql,
            "stdout": proc.stdout,
            "stderr": "Empty result — verification expected at least one row",
            "returncode": 0,
        }
    if out_stripped.lower() in ("f", "false", "0"):
        return {
            "verified": False,
            "sql": verify_sql,
            "stdout": proc.stdout,
            "stderr": f"Verification returned {out_stripped!r}",
            "returncode": 0,
        }

    return {
        "verified": True,
        "sql": verify_sql,
        "stdout": proc.stdout,
        "stderr": "",
        "returncode": 0,
    }


def verify_migration_file(
    migration_path: Path,
    db_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Verify all `-- VERIFY:` blocks in a single migration file.

    Returns a per-file report:
        {
          "file": str,
          "verify_count": int,
          "results": [run_verification result, ...],
          "all_passed": bool,
          "skipped": bool,   # True when no VERIFY blocks present
        }
    """
    sql_text = migration_path.read_text(encoding="utf-8")
    blocks = parse_verify_blocks(sql_text)

    if not blocks:
        return {
            "file": str(migration_path),
            "verify_count": 0,
            "results": [],
            "all_passed": True,
            "skipped": True,
        }

    results = [run_verification(b, db_url=db_url, dry_run=dry_run) for b in blocks]
    return {
        "file": str(migration_path),
        "verify_count": len(blocks),
        "results": results,
        "all_passed": all(r["verified"] for r in results),
        "skipped": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run -- VERIFY: blocks against one or more migration files.",
    )
    parser.add_argument(
        "--migration",
        required=True,
        action="append",
        help="Path to a migration .sql file (repeatable for batch verification)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="DB connection URL passed to psql (e.g. postgres://...). "
        "If omitted, psql uses its default connection (PGHOST/PGUSER/etc.).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + report without invoking psql. Useful for CI sanity checks.",
    )
    parser.add_argument(
        "--output",
        help="Write the JSON report to a file instead of stdout.",
    )
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.migration]
    reports = [
        verify_migration_file(p, db_url=args.db_url, dry_run=args.dry_run)
        for p in paths
    ]

    summary = {
        "migrations_checked": len(paths),
        "migrations_with_verify": sum(1 for r in reports if not r["skipped"]),
        "migrations_passed": sum(
            1 for r in reports if r["all_passed"] and not r["skipped"]
        ),
        "migrations_failed": sum(1 for r in reports if not r["all_passed"]),
        "migrations_skipped": sum(1 for r in reports if r["skipped"]),
        "all_passed": all(r["all_passed"] for r in reports),
        "reports": reports,
    }

    out = json.dumps(summary, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
