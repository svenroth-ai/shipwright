# Project Scaffolding (Shipwright Enhancement)

## Purpose

After spec generation, shipwright-project generates CLAUDE.md and agent_docs/ for the target project. This provides immediate context for all subsequent skills (/shipwright-plan, /shipwright-build, etc.) and serves as living documentation.

**Only runs for Full Application scope.** Extensions already have these files.

## Profile Detection

1. Scan interview transcript and requirements for technology mentions
2. Match against available profiles in `{plugin_root}/../../shared/profiles/`
3. Load the matching profile JSON

**Detection heuristics:**
- "Supabase" + "Next.js" → `supabase-nextjs`
- "Supabase" + "React" → `supabase-nextjs` (Next.js is the default React framework)
- No match → generic scaffolding (user fills in details)

## Files to Generate

### 1. CLAUDE.md

Load template from `{plugin_root}/../../shared/templates/claude-md-template.md`.

Fill placeholders:
- `{PROJECT_NAME}` — from interview or requirements title
- `{TECH_STACK}` — from profile (e.g., "Next.js 16 + Supabase + Tailwind 4 + shadcn/ui")
- `{FOLDER_STRUCTURE}` — from profile's `folder_structure`
- `{KEY_FILES}` — infer from profile (e.g., "src/app/layout.tsx, src/lib/supabase/client.ts")
- `{PROJECT_PURPOSE}` — from interview summary
- `{ARCHITECTURE_SUMMARY}` — from interview decisions
- `{BUILD_COMMAND}` — from profile (e.g., "npm run build")
- `{TEST_COMMAND}` — from profile (e.g., "npx vitest run")

### 2. agent_docs/architecture.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/architecture.md.template`.

Fill with:
- Stack details from profile
- Architecture decisions from interview
- Data flow description from requirements

### 3. agent_docs/decision_log.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/decision-log.md.template`.

Initialize with project name and profile name. No entries yet — shipwright-build will populate this.

### 4. agent_docs/conventions.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/conventions.md.template`.

Fill with:
- `{ARCHITECTURE_RULES}` — from profile's `architecture_rules` (as bullet list)
- `{FOLDER_STRUCTURE}` — from profile's `folder_structure` (as tree)

### 5. agent_docs/current_sprint.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/current-sprint.md.template`.

Initialize with first split name and "not_started" status.

## Config Output

Write `shipwright_project_config.json` to the project root:

```json
{
  "status": "complete",
  "scope": "full_app",
  "profile": "supabase-nextjs",
  "planning_dir": "planning",
  "splits": [
    {"name": "01-auth", "status": "not_started"},
    {"name": "02-dashboard", "status": "not_started"}
  ],
  "artifacts": {
    "claude_md": true,
    "agent_docs": true,
    "manifest": true
  }
}
```
