# Shipwright SDLC Framework

## WHAT
- **Purpose**: AI-powered SDLC pipeline built on Claude Code — from user description to deployed, tested, secured application
- **Architecture**: Monorepo of Claude Code plugins (skills + hooks + scripts)
- **Stack**: Python 3.11+ scripts, Claude Code plugin system, uv package manager

## Structure
```
plugins/                    # Claude Code plugins (one per SDLC phase)
  shipwright-run/           # Orchestrator (entry point)
  shipwright-project/       # Requirements decomposition (fork of deep-project)
  shipwright-design/        # UI mockups from IREB specs (HTML)
  shipwright-plan/          # Planning (fork of deep-plan)
  shipwright-build/         # Implementation (fork of deep-implement)
  shipwright-test/          # Testing (unit + E2E + security)
  shipwright-changelog/     # Git sync + changelog + PR
  shipwright-deploy/        # Deployment (extensible flavors)
  shipwright-compliance/    # IREB traceability, RTM, SBOM, reports
shared/                     # Shared across all plugins
  profiles/                 # Stack profile definitions (JSON)
  templates/                # CLAUDE.md, agent_docs, CI templates
  scripts/                  # Shared Python utilities
integration-tests/          # Cross-plugin integration tests
Spec/                       # Design specifications (temporary)
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
- Upstream: deep-project v0.2.1, deep-plan v0.3.2, deep-implement v0.2.1
- Env var prefix: `SHIPWRIGHT_` (replaces upstream `DEEP_`)
- Config file prefix: `shipwright_` (replaces upstream `deep_`)

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
- **Spec**: Spec/shipwright-sdlc-spec.md (v3.3)
- **Tasks**: Spec/shipwright-sdlc-tasks.md
- **Guide**: docs/guide.md (primary user-facing documentation)
- **Upstream**: github.com/piercelamb/deep-{project,plan,implement}
