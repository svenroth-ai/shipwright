"""Manifest of Shipwright artifact directory migrations into ``.shipwright/``.

Single source of truth for the canonical/legacy paths of each artifact
that is being (or has been) relocated under the hidden ``.shipwright/``
project-state directory.  Consumed by:

- ``test_artifact_path_canon.py`` (Layer 1) — text + AST lint that forbids
  legacy-path string literals outside the per-artifact allowlist.
- ``test_gitignore_canon.py`` (Layer 5) — verifies legacy + canonical
  gitignore entries during/after migration.
- ``test_constants_match_manifest.py`` (Layer 6) — cross-validates that
  per-plugin local constants equal the manifest values.
- ``stale_artifact_detector.py`` — runtime drift scan (warn during
  ``in_progress``, hard-gate during ``migrated``).

Adding a new artifact migration:
1. Append a dict to ``ARTIFACT_MIGRATIONS`` (status starts at ``"pending"``).
2. Sub-Iterate A-style framework Skeleton has nothing to do — Layer 1
   silently treats ``pending`` as no-op.
3. When the rewrite kicks off, flip status to ``"in_progress"`` and seed
   ``ALLOWLIST[name]`` with globs covering every file currently using the
   legacy path. Narrow the allowlist as the migration progresses.
4. After the final cleanup sub-iterate, flip status to ``"migrated"``.
   Drift detector becomes a hard gate.

See ``docs/migrations/artifact-migration-reference.md`` (written in
Sub-Iterate G of the planning relocation) for the full pattern.
"""
from __future__ import annotations

ARTIFACT_MIGRATIONS: list[dict] = [
    {
        "name": "planning",
        "canonical": ".shipwright/planning",
        "legacy_dirname": "planning",
        # Text-mode regex patterns the lint forbids (POSIX + Windows).
        # Negative lookbehind avoids matching identifiers like ``replanning``
        # or paths like ``foo/planning`` (substrings, not bare path roots).
        "old_path_patterns": [
            r"(?<![\w/.\\])planning/",
            r"(?<![\w/.\\])planning\\",
            r"(?<![\w/.\\])\"planning\"",
            r"(?<![\w/.\\])'planning'",
        ],
        # AST-mode trigger string. Used inside ``Path(...)``,
        # ``os.path.join(...)``, the ``/`` operator (Path division),
        # f-string segments, or argparse defaults.
        "ast_check_string": "planning",
        "status": "in_progress",
        "started": "2026-04-26",
    },
]

# Files exempt from the lint, per migration. Entries may be exact paths
# or glob patterns (matched against the repo-relative POSIX path).
#
# Bootstrap policy: start with the WIDEST safe glob set (catches every
# current hit), then narrow per sub-iterate as files are migrated.
# After the final cleanup sub-iterate, the allowlist should contain only:
#   - migration helpers that intentionally reference the legacy path
#   - tests that exercise the legacy code path
#   - changelog / migration-doc entries (historical record)
ALLOWLIST: dict[str, list[str]] = {
    "planning": [
        # Migration framework itself — references both paths by design
        "shared/scripts/lib/artifact_migrations.py",
        "shared/scripts/lib/stale_artifact_detector.py",
        "shared/scripts/hooks/check_artifact_drift.py",
        "shared/tests/test_artifact_path_canon.py",
        "shared/tests/test_stale_artifact_detector.py",
        "shared/tests/test_gitignore_canon.py",
        "shared/tests/test_constants_match_manifest.py",
        "shared/tests/test_path_canon_windows.py",
        # Plan files (this migration's own design docs)
        "C:/Users/SvenRoth/.claude/plans/iterate-shipwright-relocation-*.md",
        "C:/Users/SvenRoth/.claude/plans/ich-bin-am-berarbeiten-glittery-sun.md",
        # Historical changelog & migration docs (must not be rewritten)
        "CHANGELOG.md",
        "CHANGELOG-unreleased.d/**",
        "docs/migrations/**",
        # Pre-migration touchpoint inventory — every glob currently using
        # legacy paths.  These narrow as Sub-Iterates B-E migrate them.
        "shared/scripts/lib/drift_parsers.py",
        "shared/scripts/lib/spec_parser.py",
        "shared/scripts/lib/autonomous_loop.py",
        "shared/scripts/lib/iterate_entry.py",
        "shared/scripts/lib/external_review_config.py",
        "shared/scripts/tools/**",
        "shared/scripts/checks/**",
        "shared/scripts/hooks/**",
        "shared/templates/**",
        "shared/tests/**",
        "shared/config/**",
        "shared/prompts/**",
        "shared/schemas/**",
        "plugins/**/*.py",
        "plugins/**/*.md",
        "plugins/**/*.json",
        # pyproject.toml keywords ("planning" as descriptive metadata, not a path)
        "**/pyproject.toml",
        "integration-tests/**",
        "docs/**",
        ".gitignore",
        ".claude-plugin/**",
        # Previous-iteration plan reference (memo)
        "**/project_paths_refactor_evaluated.md",
    ],
}

# Inline opt-out marker — per-line escape hatch. Add as a comment
# (Python ``#``, HTML ``<!-- -->``, JSON not supported) on the offending
# line when an allowlist entry would be too broad.
INLINE_MARKER = "artifact-path-canon: legacy"


def get_migration(name: str) -> dict | None:
    """Return the migration entry for *name*, or ``None`` if not found."""
    for migration in ARTIFACT_MIGRATIONS:
        if migration["name"] == name:
            return migration
    return None


def active_migrations() -> list[dict]:
    """Migrations the drift detector should scan (warn or block)."""
    return [m for m in ARTIFACT_MIGRATIONS if m["status"] in ("in_progress", "migrated")]
