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
  shipwright-plan/          # Planning (fork of deep-plan)
  shipwright-build/         # Implementation (fork of deep-implement)
  shipwright-test/          # Testing (unit + E2E + security)
  shipwright-changelog/     # Git sync + changelog + PR
  shipwright-deploy/        # Deployment (extensible flavors)
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
- **Upstream**: github.com/piercelamb/deep-{project,plan,implement}
