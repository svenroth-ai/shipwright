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
**Use `/shipwright-iterate` for code changes — Do NOT edit code directly.**
The skill keeps specs, tests, ADRs, and the CHANGELOG in sync.

What `/shipwright-iterate` automates:
- ADR entry in `.shipwright/agent_docs/decision_log.md`
- CHANGELOG fragment under `CHANGELOG-unreleased.d/<category>/`
- Conventional Commits on an `iterate/<slug>` branch, merged to main on green tests
- FR / acceptance-criteria sync in `.shipwright/planning/`
- Compliance + dashboard refresh

Do NOT invoke `/shipwright-project`, `/shipwright-plan`, or `/shipwright-build` directly — those are pre-onboarding phases.

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

## Asking the user questions (plain language)

When you ask the user a question — a clarification, a choice between options,
or a confirmation — phrase it so a **non-senior developer or a normal user**
can understand, from a functional standpoint, what is actually being decided.
The person answering may not know the internals; do not make them decode
jargon to reply.

- **Lead with the functional meaning:** say what the choice changes about how
  the app behaves or what the user gets — not the implementation detail.
- **Avoid unexplained jargon.** If a technical term is unavoidable, add a short
  plain-language gloss in parentheses (e.g. "idempotent — safe to run twice
  without doubling the effect").
- **Make options concrete and comparable.** Give each option in plain words
  with its real-world trade-off ("Option A is simpler but slower; Option B is
  faster but adds a setup step"), not a raw technical menu.
- **Rule of thumb:** a product owner should be able to answer without asking
  "what does that mean?". If they couldn't, rewrite it.

This governs *phrasing only* — the rigor of the work is unchanged.
