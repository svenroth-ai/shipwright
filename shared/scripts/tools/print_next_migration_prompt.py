"""Emit a kickoff prompt for the next `.shipwright/` artifact migration.

Sub-Iterate F deliverable. Reads ``shared/scripts/lib/artifact_migrations.py``
to find the next non-completed artifact and prints a /shipwright-iterate prompt
plus a pointer to the reference doc + pattern memory.

Used by:
- the human, after a migration sub-iterate finishes
- the migration sub-iterate's commit/PR-description automation

Idempotent and side-effect-free aside from stdout.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_SHARED_SCRIPTS = _HERE.parent.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.artifact_migrations import ARTIFACT_MIGRATIONS  # noqa: E402


def _just_completed(manifest: list[dict]) -> dict | None:
    migrated = [m for m in manifest if m["status"] == "migrated"]
    return migrated[-1] if migrated else None


def _next_up(manifest: list[dict]) -> dict | None:
    """Prefer in_progress > pending. Returns None if everything is migrated."""
    for status in ("in_progress", "pending"):
        for m in manifest:
            if m["status"] == status:
                return m
    return None


def _all_done_message(manifest: list[dict]) -> str:
    migrated_count = sum(1 for m in manifest if m["status"] == "migrated")
    return (
        f"All {migrated_count} artifact migration(s) complete. Nothing pending.\n"
        f"To plan a new artifact migration, append a dict with status='pending' "
        f"to ARTIFACT_MIGRATIONS in shared/scripts/lib/artifact_migrations.py."
    )


def render_prompt(manifest: list[dict]) -> str:
    """Return the human-readable kickoff string for the next migration."""
    next_one = _next_up(manifest)
    if next_one is None:
        return _all_done_message(manifest)

    just_done = _just_completed(manifest)
    others = [
        m["name"] for m in manifest if m["status"] in ("in_progress", "pending") and m["name"] != next_one["name"]
    ]
    others_line = ", ".join(others) if others else "none"

    just_done_line = (
        f"Just completed: {just_done['name']} -> {just_done['canonical']}\n\n"
        if just_done is not None
        else ""
    )

    status_label = (
        "in progress -- resume here"
        if next_one["status"] == "in_progress"
        else "pending"
    )

    return (
        "=== Next .shipwright/ migration ready ===\n"
        f"{just_done_line}"
        f"Suggested next: {next_one['name']} -> {next_one['canonical']} "
        f"({status_label})\n\n"
        f"To kick off:\n"
        f"  /shipwright-iterate \"{next_one['name']} relocation to "
        f"{next_one['canonical']}\"\n\n"
        f"Pattern-memory to consult: feedback_artifact_migration_pattern.md\n"
        f"Reference doc: docs/migrations/artifact-migration-reference.md\n"
        f"Plan-file template: re-use the iterate-shipwright-relocation-A..G-*.md "
        f"shape from C:/Users/you/.claude/plans/.\n\n"
        f"Other pending artifacts (after {next_one['name']}): {others_line}\n"
    )


def main(argv: list[str] | None = None) -> int:
    print(render_prompt(ARTIFACT_MIGRATIONS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
