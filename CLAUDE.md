# Shipwright SDLC Framework

## WHAT
- **Purpose**: AI-powered SDLC pipeline built on Claude Code — from user description to deployed, tested, secured application
- **Architecture**: Monorepo of Claude Code plugins (skills + hooks + scripts)
- **Stack**: Python 3.11+ scripts, Claude Code plugin system, uv package manager

## Structure
```
plugins/                    # Claude Code plugins (one per SDLC phase)
  shipwright-run/           # Orchestrator (entry point)
  shipwright-project/       # Requirements decomposition (IREB)
  shipwright-design/        # UI mockups from IREB specs (HTML)
  shipwright-plan/          # Deep planning + external LLM review
  shipwright-build/         # TDD implementation
  shipwright-test/          # Testing (unit + smoke + Playwright E2E)
  shipwright-security/      # Scanner chain + remediation loop
  shipwright-deploy/        # Deployment (extensible flavors)
  shipwright-changelog/     # Git sync + changelog + PR
  shipwright-compliance/    # IREB traceability, RTM, SBOM, dashboard
  shipwright-iterate/       # Daily iteration (complexity-adaptive)
  shipwright-preview/       # Local browser preview
  shipwright-adopt/         # Brownfield onboarding (analyze an existing repo)
# Command Center WebUI lives at github.com/svenroth-ai/shipwright-webui since v0.4.0
shared/                     # Shared across all plugins
  profiles/                 # Stack profile definitions (JSON) + deploy profiles
  templates/                # CLAUDE.md, .shipwright/agent_docs, CI templates
  prompts/                  # Shared subagent prompts (code_reviewer, iterate_reviewer)
  schemas/                  # JSON schemas (run_config v2)
  config/                   # Shared config (external_review.json)
  scripts/                  # Shared Python utilities
  tests/                    # Tests for shared scripts and hooks
  constitution.md           # ALWAYS / ASK FIRST / NEVER rules for all agents
scripts/                    # Top-level scripts (install.sh, verify-setup.sh)
docs/                       # User-facing docs (guide.md, hooks-and-pipeline.md)
integration-tests/          # Cross-plugin integration tests
CHANGELOG-unreleased.d/     # Pending changelog drop files (aggregated at release)
```

## HOW

### Development
```bash
uv sync                              # Install dependencies
uv run pytest tests/ -v               # Run tests for a plugin (from plugin dir)
uv run pytest integration-tests/ -v   # Run integration tests (from root)
```

### Plugin Structure (each plugin follows this pattern)
```
plugins/shipwright-{name}/
  .claude-plugin/plugin.json          # Plugin metadata
  hooks/hooks.json                    # Claude Code hooks
  agents/                             # Subagent definitions (markdown)
  skills/{name}/SKILL.md              # Main skill definition (folder = slash command suffix)
  scripts/                            # Python scripts (checks, hooks, lib, tools)
  tests/                              # Plugin-specific tests
  pyproject.toml                      # Plugin dependencies
```

### Key Environment Variables
```
SHIPWRIGHT_SESSION_ID        # Unified session ID across all plugins
SHIPWRIGHT_PLUGIN_ROOT       # Absolute path to active plugin directory
```

### Conventions
- All scripts invoked via `uv run`
- Hooks use `${CLAUDE_PLUGIN_ROOT}` for path resolution
- Config files: `shipwright_*_config.json` (written to target project)
- Env var prefix: `SHIPWRIGHT_`
- Config file prefix: `shipwright_`

### Hooks & Pipeline Reference
- **Reference doc:** `docs/hooks-and-pipeline.md`
- **ALWAYS read this file first** when working on any plugin. It contains the
  complete context loading matrix (who reads what), artifact write matrix (who
  writes what), hooks registry, config data flow, and between-phase actions.
- **Rule:** When modifying any hook (hooks.json), adding/removing a pipeline phase,
  changing phase validators, altering between-phase actions, or changing what a
  plugin reads at startup (context loading), you MUST update
  `docs/hooks-and-pipeline.md` to reflect the change.
- This document is the single source of truth for understanding what fires when,
  who reads/writes which artifacts, and the impact of pipeline changes.

### When editing plugin-side files

Changes under `plugins/*`, `shared/scripts/`, or any `SKILL.md` file do
NOT auto-sync to the plugin cache at `~/.claude/plugins/cache/shipwright/`
that Claude Code uses at runtime. After `git push`, run:

```bash
bash scripts/update-marketplace.sh
```

**Scope:** This is shipwright-monorepo-specific and only applies when
developing the plugins themselves. End-users who consume the plugins via
`/shipwright-iterate`, `/shipwright-build`, etc. on their own projects do
NOT need this step — they run the installed/cached plugin versions.

**Why it matters:** Without the sync, plugin-side fixes land in the dev
repo but never reach runtime. Iterates 7-11 all had plugin-side fixes
(SKILL.md F11 updates, shared script improvements) that silently never
took effect because this step was skipped.

**Enforcement (Iterate C.3, 2026-05-21):** the script
`scripts/check_plugin_cache_sync.py` detects drift between the local
plugin-cache and repo HEAD via per-file SHA-256 comparison. Run it
manually (fail-soft WARN by default; `--strict` for CI use) — a
future iterate will wire it into a SessionStart hook so every iterate
starts with a sync check.

### Documentation Guide
- **Reference doc:** `docs/guide.md`
- **Rule:** When adding a new skill, changing a skill's command/arguments/flags,
  modifying the pipeline flow, or changing the constitution, check whether
  `docs/guide.md` needs an update. Key sections to check:
  - Chapter 4 (phase descriptions) — if skill behavior changed
  - Chapter 7.5 (constitution) — if constitution rules changed
  - Chapter 8 (quality gates) — if hooks changed
  - Appendix B (command reference) — if commands/flags changed
- The guide is the primary user-facing documentation. README.md is a summary
  that links to the guide.

### Testing
```bash
# Single plugin
cd plugins/shipwright-build && uv run pytest tests/ -v

# All integration tests
uv run pytest integration-tests/ -v
```

## Context
- **Guide**: docs/guide.md (primary user-facing documentation)
- **Hooks & Pipeline**: docs/hooks-and-pipeline.md (context loading, hooks registry, between-phase actions)
