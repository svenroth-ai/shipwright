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

## Ongoing Changes
For any code changes after the initial build (features, bug fixes, refactoring, modifications):
→ Use `/shipwright-iterate` — it keeps specs, tests, and ADRs in sync automatically.

## Structure
{FOLDER_STRUCTURE}

## Key Files
{KEY_FILES}

## Gotchas
{GOTCHAS}

## Context

**Read first** (stable, always relevant):
- @.shipwright/agent_docs/architecture.md — system overview, layers, security model
- @.shipwright/agent_docs/conventions.md — code patterns, naming, git workflow

**Read on demand** (volatile, changes per session):
- @.shipwright/agent_docs/decision_log.md — when making or reviewing decisions
- @.shipwright/agent_docs/build_dashboard.md — when checking progress or planning next steps
- @.shipwright/agent_docs/session_handoff.md — when resuming after a pause or /clear

**Other references:**
- @.shipwright/planning/ — specs and section files

**Pipeline state** (machine-generated, do not edit manually):
- @shipwright_run_config.json — pipeline state (scope, profile, autonomy, current/completed steps)
- @shipwright_project_config.json — requirements splits, profile, project metadata
- @shipwright_plan_config.json — section references for build
- @shipwright_build_config.json — build progress per section
- @shipwright_security_config.json — security scan results
- @shipwright_compliance_config.json — compliance audit metadata

## Path-migration awareness

If you see `.shipwright/stale-folders.md` in this project, the Shipwright
drift detector flagged a legacy artefact directory at the project root that
should live under `.shipwright/` (e.g. legacy `planning/`, `designs/`,
`agent_docs/`, `compliance/`). The file contains the exact `git mv`
remediation commands — follow them, do not skip or delete it. The file
auto-clears when the next SessionStart runs cleanly. Per-artefact migration
guides live in the Shipwright repo under `docs/migrations/`.
