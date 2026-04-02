# {PROJECT_NAME}

## WHAT
- **Stack**: {TECH_STACK}
- **Purpose**: {PROJECT_PURPOSE}

## HOW
- **Build**: {BUILD_COMMAND}
- **Test**: {TEST_COMMAND}
- **Lint**: {LINT_COMMAND}
- **Deploy DEV**: git push (auto)
- **Deploy PROD**: /shipwright-deploy --env prod

## Structure
{FOLDER_STRUCTURE}

## Key Files
{KEY_FILES}

## Gotchas
{GOTCHAS}

## Context

**Read first** (stable, always relevant):
- @agent_docs/architecture.md — system overview, layers, security model
- @agent_docs/conventions.md — code patterns, naming, git workflow

**Read on demand** (volatile, changes per session):
- @agent_docs/decision_log.md — when making or reviewing decisions
- @agent_docs/current_sprint.md — when checking progress or planning next steps
- @agent_docs/session_handoff.md — when resuming after a pause or /clear

**Other references:**
- @planning/ — specs and section files
- @shipwright_run_config.json — pipeline state and settings
