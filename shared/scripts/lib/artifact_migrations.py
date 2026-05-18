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
        # Negative lookbehinds keep us from matching:
        #   - identifiers like ``replanning`` (word-char before)
        #   - sub-paths like ``foo/planning`` or ``.shipwright/planning`` (path-char before)
        #   - Path-division contexts like ``... / "planning"`` (space-quote pattern)
        "old_path_patterns": [
            r"(?<![\w/.\\])planning/",
            r"(?<![\w/.\\])planning\\",
            # ``"planning"`` as a sole string literal — but NOT when preceded by
            # `` / `` (Path-division) which is the canonical post-migration shape.
            r'(?<![\w/.\\])(?<!/ )"planning"',
            r"(?<![\w/.\\])(?<!/ )'planning'",
        ],
        # AST-mode trigger string. Used inside ``Path(...)``,
        # ``os.path.join(...)``, the ``/`` operator (Path division),
        # f-string segments, or argparse defaults.
        "ast_check_string": "planning",
        "status": "migrated",
        "started": "2026-04-26",
        "completed": "2026-04-27",
    },
    {
        "name": "designs",
        "canonical": ".shipwright/designs",
        "legacy_dirname": "designs",
        "old_path_patterns": [
            r"(?<![\w/.\\])designs/",
            r"(?<![\w/.\\])designs\\",
            r'(?<![\w/.\\])(?<!/ )"designs"',
            r"(?<![\w/.\\])(?<!/ )'designs'",
        ],
        "ast_check_string": "designs",
        "status": "migrated",
        "started": "2026-04-27",
        "completed": "2026-04-27",
    },
    {
        "name": "agent_docs",
        "canonical": ".shipwright/agent_docs",
        "legacy_dirname": "agent_docs",
        "old_path_patterns": [
            r"(?<![\w/.\\])agent_docs/",
            r"(?<![\w/.\\])agent_docs\\",
            r'(?<![\w/.\\])(?<!/ )"agent_docs"',
            r"(?<![\w/.\\])(?<!/ )'agent_docs'",
        ],
        "ast_check_string": "agent_docs",
        "status": "migrated",
        "started": "2026-04-27",
        "completed": "2026-04-28",
    },
    {
        "name": "compliance",
        "canonical": ".shipwright/compliance",
        "legacy_dirname": "compliance",
        "old_path_patterns": [
            r"(?<![\w/.\\])compliance/",
            r"(?<![\w/.\\])compliance\\",
            r'(?<![\w/.\\])(?<!/ )"compliance"',
            r"(?<![\w/.\\])(?<!/ )'compliance'",
        ],
        "ast_check_string": "compliance",
        "status": "migrated",
        "started": "2026-04-29",
        "completed": "2026-04-29",
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
        # Self-adopted shipwright records (historical / write-once data
        # files). JSON has no comment syntax (per INLINE_MARKER docs);
        # change-history.md by design records past commits referencing
        # legacy paths; archived iterate plans are write-once descriptions
        # of work done at that point in time.
        ".shipwright/adopt/enrichment.json",
        ".shipwright/agent_docs/architecture.md",
        ".shipwright/agent_docs/decision_log.md",
        ".shipwright/compliance/change-history.md",
        ".shipwright/planning/iterate/**.md",
        # External-review JSON captures (e.g. iterate-2026-05-11-triage-
        # inbox-1a-{external,code}-review.json). These files store LLM
        # feedback that legitimately mentions legacy paths verbatim. JSON
        # has no comment syntax so inline `artifact-path-canon: legacy`
        # markers can't be applied. Added in iterate-2026-05-11-triage-
        # inbox-1a after external/code review captures landed under
        # .shipwright/planning/iterate/.
        ".shipwright/planning/iterate/**.json",
        # Layer 2 setup-contract test — intentionally asserts that the legacy
        # path is NOT created. Must reference legacy by name to do so.
        "shared/tests/test_setup_writes_canonical.py",
        # Sub-Iterate F deliverables — migration CLI + chain helper +
        # their tests reference "planning" as the artifact name.
        "shared/scripts/tools/migrate_artifact_dir.py",
        "shared/scripts/tools/print_next_migration_prompt.py",
        "shared/tests/test_migrate_artifact_dir.py",
        "shared/tests/test_print_next_migration_prompt.py",
        # Plan files (this migration's own design docs)
        "C:/Users/you/.claude/plans/iterate-shipwright-relocation-*.md",
        "C:/Users/you/.claude/plans/ich-bin-am-berarbeiten-glittery-sun.md",
        # Historical changelog & migration docs (must not be rewritten)
        "CHANGELOG.md",
        "CHANGELOG-unreleased.d/**",
        "docs/migrations/**",
        # Pre-migration touchpoint inventory — every glob currently using
        # legacy paths.  These narrow as Sub-Iterates B-E migrate them.
        # Sub-Iterate B (shared/) — narrowed: drift_parsers.py + iterate_entry.py
        # + external_review_config.py kept (legacy descriptive references).
        "shared/scripts/lib/drift_parsers.py",
        "shared/scripts/lib/iterate_entry.py",
        "shared/scripts/lib/external_review_config.py",
        # Sub-Iterate D (prose) migrated all plugin .md files.
        # Remaining: plugin.json keywords (descriptive word "planning",
        # not a path).
        "plugins/**/.claude-plugin/plugin.json",
        # pyproject.toml keywords ("planning" as descriptive metadata, not a path)
        "**/pyproject.toml",
        # .gitignore retains the legacy entry under a `# legacy` comment
        # (Gemini #2 — Sub-Iterate F flips status to migrated; Layer-5
        # gitignore_canon test asserts the legacy entry stays present).
        ".gitignore",
        ".claude-plugin/**",
        # Previous-iteration plan reference (memo)
        "**/project_paths_refactor_evaluated.md",
        # claude-md-template.md path-migration-awareness section intentionally
        # lists legacy artefact names (planning/designs/agent_docs/compliance) so
        # user-projects know what to do when drift detector fires.
        "shared/templates/claude-md-template.md",
    ],
    "designs": [
        # Migration framework itself — references both paths by design
        "shared/scripts/lib/artifact_migrations.py",
        "shared/scripts/lib/stale_artifact_detector.py",
        "shared/scripts/hooks/check_artifact_drift.py",
        "shared/scripts/lib/drift_parsers.py",  # HIDDEN_DIR_DEFAULTS line 108
        "shared/tests/test_artifact_path_canon.py",
        "shared/tests/test_stale_artifact_detector.py",
        "shared/tests/test_gitignore_canon.py",
        "shared/tests/test_constants_match_manifest.py",
        "shared/tests/test_path_canon_windows.py",
        # Self-adopted shipwright records — see "planning" entry above.
        ".shipwright/adopt/enrichment.json",
        ".shipwright/agent_docs/architecture.md",
        ".shipwright/agent_docs/decision_log.md",
        ".shipwright/compliance/change-history.md",
        ".shipwright/planning/iterate/**.md",
        # External-review JSON captures (e.g. iterate-2026-05-11-triage-
        # inbox-1a-{external,code}-review.json). These files store LLM
        # feedback that legitimately mentions legacy paths verbatim. JSON
        # has no comment syntax so inline `artifact-path-canon: legacy`
        # markers can't be applied. Added in iterate-2026-05-11-triage-
        # inbox-1a after external/code review captures landed under
        # .shipwright/planning/iterate/.
        ".shipwright/planning/iterate/**.json",
        # Layer-2 setup-contract test references both paths by design
        "shared/tests/test_setup_writes_canonical.py",
        # Migration tooling (CLI + helpers) takes artifact name as argument
        "shared/scripts/tools/migrate_artifact_dir.py",
        "shared/scripts/tools/print_next_migration_prompt.py",
        "shared/tests/test_migrate_artifact_dir.py",
        "shared/tests/test_print_next_migration_prompt.py",
        # Plan files (this migration's own design docs)
        "C:/Users/you/.claude/plans/iterate-shipwright-relocation-designs-*.md",
        # Historical changelog & migration docs (must not be rewritten)
        "CHANGELOG.md",
        "CHANGELOG-unreleased.d/**",
        "docs/migrations/**",
        # Production code + tests for plugins migrated through Sub-Iterate C.
        # Earlier sub-iterates removed entries already migrated.
        # Remaining narrows as Sub-Iterate D (prose) lands.
        # Plugin prose touched in D — completed, kept here only as
        # commented record. Removed from active glob list.
        # Templates + docs touched in E — completed.
        # New edge-case test file that intentionally references both paths.
        "shared/tests/test_artifact_drift_edge_cases.py",
        # Plugin metadata: descriptive keyword "designs", not a path. Permanent.
        "plugins/**/.claude-plugin/plugin.json",
        "**/pyproject.toml",
        # .gitignore retains legacy entry with "# legacy path" comment.
        # Sub-Iterate F flips status to migrated; Layer-5 gitignore_canon
        # asserts the legacy entry stays present.
        ".gitignore",
        ".claude-plugin/**",
        # claude-md-template.md path-migration-awareness section.
        "shared/templates/claude-md-template.md",
    ],
    "agent_docs": [
        # Migration framework itself — references both paths by design
        "shared/scripts/lib/artifact_migrations.py",
        "shared/scripts/lib/stale_artifact_detector.py",
        "shared/scripts/hooks/check_artifact_drift.py",
        "shared/scripts/lib/drift_parsers.py",  # HIDDEN_DIR_DEFAULTS:108
        "shared/tests/test_artifact_path_canon.py",
        "shared/tests/test_stale_artifact_detector.py",
        "shared/tests/test_gitignore_canon.py",
        "shared/tests/test_constants_match_manifest.py",
        "shared/tests/test_path_canon_windows.py",
        # Self-adopted shipwright records — see "planning" entry above.
        # shipwright_project_config.json carries `"agent_docs": true` as a
        # feature-flag dict key (not a path); regex matches the JSON value.
        ".shipwright/adopt/enrichment.json",
        ".shipwright/agent_docs/architecture.md",
        ".shipwright/agent_docs/decision_log.md",
        ".shipwright/compliance/change-history.md",
        ".shipwright/planning/iterate/**.md",
        # External-review JSON captures (e.g. iterate-2026-05-11-triage-
        # inbox-1a-{external,code}-review.json). These files store LLM
        # feedback that legitimately mentions legacy paths verbatim. JSON
        # has no comment syntax so inline `artifact-path-canon: legacy`
        # markers can't be applied. Added in iterate-2026-05-11-triage-
        # inbox-1a after external/code review captures landed under
        # .shipwright/planning/iterate/.
        ".shipwright/planning/iterate/**.json",
        "shipwright_project_config.json",
        # Layer-2 setup-contract test references both paths by design
        "shared/tests/test_setup_writes_canonical.py",
        # Edge-case test file that intentionally references both paths (introduced in designs migration)
        "shared/tests/test_artifact_drift_edge_cases.py",
        # Migration tooling (CLI + helpers) takes artifact name as argument
        "shared/scripts/tools/migrate_artifact_dir.py",
        "shared/scripts/tools/print_next_migration_prompt.py",
        "shared/tests/test_migrate_artifact_dir.py",
        "shared/tests/test_print_next_migration_prompt.py",
        # Plan files (this migration's own design docs)
        "C:/Users/you/.claude/plans/iterate-shipwright-relocation-agent_docs-*.md",
        # Historical changelog & migration docs (must not be rewritten)
        "CHANGELOG.md",
        "CHANGELOG-unreleased.d/**",
        "docs/migrations/**",
        # Sub-Iterate B (shared/) — narrowed: lokale Konstanten in spec_parser /
        # generate_handoff_on_stop / verifiers/common kept (Layer-6 manifest
        # binds `LEGACY_AGENT_DOCS_DIRNAME = "agent_docs"`). Files no longer
        # constructing legacy paths are removed from the allowlist.
        "shared/scripts/hooks/generate_handoff_on_stop.py",
        "shared/scripts/hooks/check_secrets.sh",
        "shared/scripts/lib/spec_parser.py",
        "shared/scripts/lib/external_review_config.py",
        "shared/scripts/tools/verifiers/common.py",
        "shared/scripts/tools/verifiers/design_compliance.py",
        # Sub-Iterate C (plugins/) — narrowed: lokale Konstanten in
        # artifact_writer.py + visual_docs_generator.py + config_writer.py JSON-flag
        # remain in allowlist. All other plugin scripts migrated.
        "plugins/shipwright-adopt/scripts/lib/artifact_writer.py",
        "plugins/shipwright-adopt/scripts/lib/visual_docs_generator.py",
        "plugins/shipwright-adopt/scripts/lib/config_writer.py",
        # project-scaffolding.md documents the same JSON-flag config_writer.py
        # writes — `"agent_docs": true` is metadata, not a path. Permanent.
        "plugins/shipwright-project/skills/project/references/project-scaffolding.md",
        # Tests — narrowed in B + C as files migrate. Tests using helper-construct
        # `tmp / ".shipwright" / "agent_docs"` are post-shipwright canonical and
        # don't need to be in allowlist (AST treats them as canonical-form).
        # Tests that still reference legacy literals (preservation_log keys,
        # backup-path mirroring) remain covered by per-file globs.
        "shared/tests/**",
        "shared/scripts/tests/**",
        "plugins/shipwright-adopt/tests/**",
        "plugins/shipwright-build/tests/**",
        "plugins/shipwright-compliance/tests/**",
        "plugins/shipwright-run/tests/**",
        "integration-tests/**",
        # Sub-Iterate D (prose) completed. Plugin SKILLs/agents/references +
        # README + CLAUDE.md + constitution all migrated. Removed.
        # Sub-Iterate E (templates + docs) completed. shared/templates/**,
        # docs/guide.md, docs/hooks-and-pipeline.md, bug_report.yml, and
        # run_config.v2.schema.json all migrated to canonical. Removed.
        # Plugin metadata: descriptive keyword "agent_docs", not a path. Permanent.
        "plugins/**/.claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "**/pyproject.toml",
        # .gitignore retains legacy entry with "# legacy path" comment in F.
        ".gitignore",
        ".claude-plugin/**",
        # shipwright-security oss-scanners.md describes the scanner-exclusion contract
        # which intentionally references the legacy `agent_docs/` path as the historical
        # state being migrated away from. Added 2026-04-29 after security Sub-Iterate H
        # added these references without updating the allowlist (pre-existing regression).
        "plugins/shipwright-security/skills/security/references/oss-scanners.md",
        # claude-md-template.md path-migration-awareness section.
        "shared/templates/claude-md-template.md",
    ],
    "compliance": [
        # Migration framework itself — references both paths by design
        "shared/scripts/lib/artifact_migrations.py",
        "shared/scripts/lib/stale_artifact_detector.py",
        "shared/scripts/hooks/check_artifact_drift.py",
        "shared/scripts/lib/drift_parsers.py",  # HIDDEN_DIR_DEFAULTS:108
        "shared/tests/test_artifact_path_canon.py",
        "shared/tests/test_stale_artifact_detector.py",
        "shared/tests/test_gitignore_canon.py",
        "shared/tests/test_constants_match_manifest.py",
        "shared/tests/test_path_canon_windows.py",
        # Self-adopted shipwright records — see "planning" entry above.
        ".shipwright/adopt/enrichment.json",
        ".shipwright/agent_docs/architecture.md",
        ".shipwright/agent_docs/decision_log.md",
        # conventions.md accumulates Learnings prose that mentions "compliance"
        # as a phase name, the `shipwright-compliance` plugin dir, or a triage
        # `source=` enum value — never as a legacy artifact path. Same class as
        # architecture.md / decision_log.md above; it was simply missed when
        # those sibling agent_docs were allowlisted.
        ".shipwright/agent_docs/conventions.md",
        ".shipwright/compliance/change-history.md",
        ".shipwright/planning/iterate/**.md",
        # External-review JSON captures (e.g. iterate-2026-05-11-triage-
        # inbox-1a-{external,code}-review.json). These files store LLM
        # feedback that legitimately mentions legacy paths verbatim. JSON
        # has no comment syntax so inline `artifact-path-canon: legacy`
        # markers can't be applied. Added in iterate-2026-05-11-triage-
        # inbox-1a after external/code review captures landed under
        # .shipwright/planning/iterate/.
        ".shipwright/planning/iterate/**.json",
        # Layer-2 setup-contract test references both paths by design
        "shared/tests/test_setup_writes_canonical.py",
        # Edge-case test file that intentionally references both paths (introduced in designs migration)
        "shared/tests/test_artifact_drift_edge_cases.py",
        # Migration tooling (CLI + helpers) takes artifact name as argument
        "shared/scripts/tools/migrate_artifact_dir.py",
        "shared/scripts/tools/print_next_migration_prompt.py",
        "shared/tests/test_migrate_artifact_dir.py",
        "shared/tests/test_print_next_migration_prompt.py",
        # Plan files (this migration's own design docs)
        "C:/Users/you/.claude/plans/iterate-shipwright-relocation-compliance-*.md",
        # Historical changelog & migration docs (must not be rewritten)
        "CHANGELOG.md",
        "CHANGELOG-unreleased.d/**",
        "docs/migrations/**",
        "shared/constitution.md",
        "README.md",
        "CLAUDE.md",
        # Files migrated in B that retain legitimate LEGACY_COMPLIANCE_DIRNAME constant
        # (per Layer-6 cross-validation pattern) or KEYWORD/PHASE-NAME dict keys.
        # The PATH-ref hits in these files are gone; what remains is by design.
        "shared/scripts/lib/phase_quality.py",                            # LEGACY_COMPLIANCE_DIRNAME + phase-name dict keys
        "shared/scripts/tools/finalize_iterate.py",                       # result["steps"]["compliance"] phase-name key
        "shared/scripts/tools/verifiers/compliance_compliance.py",        # LEGACY_COMPLIANCE_DIRNAME constant
        "shared/scripts/tools/verifiers/infrastructure_checks.py",        # LEGACY_COMPLIANCE_DIRNAME constant
        "shared/scripts/tools/verifiers/security_compliance.py",          # LEGACY_COMPLIANCE_DIRNAME constant
        # plugins/ (C-scope) — migrated in C; files retaining legitimate
        # LEGACY_COMPLIANCE_DIRNAME constants stay allowlisted:
        "plugins/shipwright-compliance/scripts/lib/compliance_report.py",  # COMPLIANCE_DIR + LEGACY constant
        "plugins/shipwright-compliance/scripts/lib/sbom_generator.py",     # COMPLIANCE_DIR + LEGACY constant
        "plugins/shipwright-compliance/scripts/lib/rtm_generator.py",      # COMPLIANCE_DIR + LEGACY constant
        "plugins/shipwright-compliance/scripts/lib/test_evidence.py",      # COMPLIANCE_DIR + LEGACY constant
        "plugins/shipwright-compliance/scripts/lib/change_history.py",     # COMPLIANCE_DIR + LEGACY constant
        "plugins/shipwright-compliance/scripts/audit/audit_staleness.py",  # COMPLIANCE_DIR + LEGACY constant
        # Plugin-path comment in audit_adapters.py (PLUGIN-PATH, not artifact path)
        "plugins/shipwright-compliance/scripts/audit/audit_adapters.py",
        # PHASE-NAME / skill-compliance subdir refs (compliance is a phase name; the
        # `skill-compliance/` subdir under .shipwright/compliance/ is the dominant text).
        "plugins/shipwright-run/scripts/lib/orchestrator.py",
        "plugins/shipwright-run/scripts/lib/phase_validators.py",
        # Triage Inbox (iterate-2026-05-11-triage-inbox-1a) — uses
        # "compliance" as an ENUM value (kind, source, suggestedDomain),
        # not as a path reference. audit_detector.py's added
        # mirror_findings_to_triage uses `source="compliance"` /
        # `kind="compliance"` for the wire format. The docs file
        # references `plugins/shipwright-compliance/...` plugin paths
        # in explanatory tables.
        "shared/scripts/triage.py",
        "plugins/shipwright-compliance/scripts/audit/audit_detector.py",
        "docs/triage-inbox.md",
        # Tests (narrowed in B+C as files migrate)
        "shared/tests/**",
        "shared/scripts/tests/**",
        "plugins/shipwright-compliance/tests/**",
        "plugins/shipwright-adopt/tests/**",
        "plugins/shipwright-run/tests/**",
        "integration-tests/**",
        # Plugin Prosa (D-scope) — migrated in D, no longer in ALLOWLIST.
        # Templates + Docs (E-scope) — migrated in E. Both files retain legitimate
        # KEYWORD/PHASE-NAME refs ("compliance" as pipeline-phase) and skill-compliance/
        # subdir refs (canonical, but regex matches due to `-compliance/` substring).
        "docs/guide.md",
        "docs/hooks-and-pipeline.md",
        # Plugin metadata: descriptive keyword "compliance", not a path. Permanent.
        "plugins/**/.claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "**/pyproject.toml",
        # .gitignore retains legacy entry under "# legacy path" comment (F adds the block).
        ".gitignore",
        ".claude-plugin/**",
        # Schema field "last_compliance_update" — KEYWORD only, not a path. Permanent.
        "shared/schemas/run_config.v2.schema.json",
        # GitHub Issue Template — only KEYWORD plugin name "shipwright-compliance"
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        # Dependabot config — plugin-dir reference (descriptive)
        ".github/dependabot.yml",
        # Spec/ markdown referenced plugin internals (gitignored, but Layer-1 may scan)
        "Spec/**",
        # claude-md-template.md path-migration-awareness section.
        "shared/templates/claude-md-template.md",
        # KEYWORD / PHASE-NAME / PLUGIN-PATH-COMMENT entries (descriptive, not PATH-REFs).
        # All discovered during A's Layer-1-lint baseline; documented as non-touchpoints.
        "plugins/shipwright-iterate/scripts/lib/classify_phase.py",      # phase-name dict + lists
        "plugins/shipwright-iterate/tests/test_classify_phase.py",       # phase-name assertion
        "plugins/shipwright-project/scripts/write_run_config.py",        # PIPELINE_PHASES list
        "shared/scripts/hooks/suggest_iterate.py",                       # phase-regex dict + slash-cmd map
        "shared/scripts/lib/config.py",                                  # config-file mapping
        "shared/scripts/tools/__init__.py",                              # docstring plugin-path comment
        "shared/scripts/tools/update_build_dashboard.py",                # PIPELINE_PHASES list
        "plugins/shipwright-compliance/scripts/audit/audit_adapters.py", # plugin-path comment
        "plugins/shipwright-compliance/scripts/tools/update_compliance.py", # action-mapping dict key
        # Pending C-migration (path-ref in adopt's decision-log template, line 204).
        # The entry will narrow once Sub-Iterate C migrates the template string.
        "plugins/shipwright-adopt/scripts/lib/artifact_writer.py",
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
