# Project Scaffolding (Shipwright Enhancement)

## Purpose

After spec generation, shipwright-project generates CLAUDE.md and .shipwright/agent_docs/ for the target project. This provides immediate context for all subsequent skills (/shipwright-plan, /shipwright-build, etc.) and serves as living documentation.

**Only runs for Full Application scope.** Extensions already have these files.

## Profile Detection

1. Scan interview transcript and requirements for technology mentions
2. Match against available profiles in `{plugin_root}/../../shared/profiles/`
3. Load the matching profile JSON

**Detection heuristics:**
- "Supabase" + "Next.js" → `supabase-nextjs`
- "Supabase" + "React" → `supabase-nextjs` (Next.js is the default React framework)
- No match → generic scaffolding (user fills in details)

**Versions are minimums, not pins.** A profile's `stack` versions are a
security-relevant floor, not an exact snapshot to transcribe into the
scaffolded `package.json` — when authoring dependency versions, resolve and
install the latest version satisfying each declared range instead of copying
the range string verbatim. A profile that goes stale between framework
releases must not carry that staleness into every new project it scaffolds.

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

### 2. AGENTS.md

Codex CLI reads `AGENTS.md` as its own, native, first-class convention — not
as a fallback for a missing `CLAUDE.md`. Write it unconditionally, alongside
CLAUDE.md, for every Full Application scope project — never gated on an
interview answer.

Do **not** load a second template. Reuse the CLAUDE.md content you just
filled from `claude-md-template.md`, with two substitutions — miss either one
and the generated AGENTS.md misnames itself or cites a gate that doesn't
apply to it:
1. In the standing-request section (`## Review subagents: standing request.
   Workflows: ask every time.`), change `Claude Code withholds subagent
   spawning until the user asks` to `Codex withholds subagent spawning until
   the user asks`.
2. In the `## Editing this file (keep it lean)` section: change the opening
   `CLAUDE.md is **orientation + a terse invariant index**` to `AGENTS.md is
   **orientation + a terse invariant index**`, and replace the final
   `- **Growth is gated:** ...` bullet (which names a `check_agent_doc_budget.py`
   enforcement and a `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK` env var that only ever
   apply to CLAUDE.md) with `- **No automated growth gate for this file
   yet** — keep it lean by the same restraint CLAUDE.md's line-cap enforces;
   watch it by hand.`

No other text changes — those two spots are the only host-specific content
in the whole shared body.

Then append the Codex-only appendix verbatim: load
`{plugin_root}/../../shared/templates/codex-agents-md-appendix.md` and add its
full content to the end of the file, separated by a blank line. This is the
same appendix `/shipwright-adopt` appends when writing a brownfield project's
`AGENTS.md` — the two producers share this one appendix file so there is
nothing Codex-specific to keep in sync in two places.

### 3. .shipwright/agent_docs/architecture.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/architecture.md.template`.

Fill with:
- Stack details from profile
- Architecture decisions from interview
- Data flow description from requirements

### 4. .shipwright/agent_docs/decision_log.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/decision-log.md.template`.

Initialize with project name and profile name. No entries yet — shipwright-build will populate this.

### 5. .shipwright/agent_docs/conventions.md

Load template from `{plugin_root}/../../shared/templates/agent-docs/conventions.md.template`.

Fill with:
- `{ARCHITECTURE_RULES}` — from profile's `architecture_rules` (as bullet list)
- `{FOLDER_STRUCTURE}` — from profile's `folder_structure` (as tree)

## Config Output

Write `shipwright_project_config.json` to the project root:

```json
{
  "status": "complete",
  "scope": "full_app",
  "profile": "supabase-nextjs",
  "planning_dir": ".shipwright/planning",
  "splits": [
    {"name": "01-auth", "status": "not_started"},
    {"name": "02-dashboard", "status": "not_started"}
  ],
  "artifacts": {
    "claude_md": true,
    "agents_md": true,
    "agent_docs": true,
    "manifest": true
  }
}
```
