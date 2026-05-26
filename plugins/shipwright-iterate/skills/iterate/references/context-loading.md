# Context Loading (Progressive Disclosure)

Authoritative companion to SKILL.md First Actions Step B2 and the broader
context-loading discipline.

## Layer 1 — Always Load (read in Step B2)

1. `shipwright_run_config.json` — project metadata, profile, completed sections
2. `CLAUDE.md` — project conventions, stack, commands
3. `.shipwright/agent_docs/conventions.md` — coding standards, naming, patterns
4. `.shipwright/agent_docs/decision_log.md` — ALL architectural decisions (read completely)
5. `.shipwright/agent_docs/architecture.md` — app structure, component tree, data flow
6. `shipwright_sync_config.json` — file-to-FR mappings (if exists)
7. `.shipwright/planning/*/spec.md` — ALL spec files across all splits (read completely)
8. `git log --oneline -20` — recent commits (prevents duplicate work)
9. `shipwright_test_results.json` — last test run status, degraded conditions
10. `shipwright_events.jsonl` — ALL events — complete project history (work_completed, deployments, etc.)

## Layer 2 — Load On-Demand

Read only when the change touches their domain:

- `.shipwright/planning/*/sections/*.md` — only the section files for affected areas
- `.shipwright/designs/visual-guidelines.md` — only for UI changes
- `.shipwright/designs/screens/*.html` — only for UI changes requiring mockup reference
- `.shipwright/designs/chrome-definition.md` — only for UI changes needing chrome context
- `{build_plugin_root}/skills/build/references/shadcn-rules.md` — Core Rules only, for UI changes
- `{build_plugin_root}/skills/build/references/shadcn-project-conventions.md` — Card/Button conventions, for UI changes
- `{build_plugin_root}/skills/build/references/shadcn-block-patterns.md` — Index + matching category only
- `{build_plugin_root}/skills/build/references/mockup-to-shadcn-mapping.md` — for UI changes
- `supabase/migrations/` — only for database changes

Where `{build_plugin_root}` = path to `plugins/shipwright-build` (resolve from
`shipwright_run_config.json` or relative to shared).
