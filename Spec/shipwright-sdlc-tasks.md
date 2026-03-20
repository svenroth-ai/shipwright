# Shipwright SDLC -- Implementation Roadmap (tasks.md)

> **Pattern**: Each task is a self-contained work unit for ONE Claude Code session.
> After each task: `/clear` and start the next task.
> Each task can be verified before moving on.
>
> **Reference**: `shipwright-sdlc-spec.md` for full context on any topic.

---

## Overview

| Phase | Tasks | Focus | Priority |
|-------|-------|-------|----------|
| 1: Foundation | 01-03 | Stack profiles, templates, shared scripts | Must Have |
| 2: Core Trilogy | 04-09 | shipwright-project, shipwright-plan, shipwright-build | Must Have |
| 3: DevOps Skills | 10-13 | shipwright-changelog, shipwright-test, shipwright-deploy | Must Have |
| 4: Orchestrator | 14-17 | shipwright-run + iteration mode | Must Have |
| 5: Agent Teams | 18-20 | Optional parallel enhancement | Enhancement |

**Dependencies:**
```
Phase 1 (Foundation)     → No dependencies, start here
Phase 2 (Core Trilogy)   → Depends on Phase 1
Phase 3 (DevOps Skills)  → Depends on Phase 1; can overlap with Phase 2
Phase 4 (Orchestrator)   → Depends on Phase 2 + 3
Phase 5 (Agent Teams)    → Depends on Phase 2
```

---

## Phase 1: Foundation (Tasks 01-03)

**Goal**: Create monorepo structure, stack profiles, shared templates, and utilities.

---

### Task 01: Monorepo Scaffolding + Stack Profiles

**Description**: Create the `shipwright` monorepo structure and define the stack profile JSON files. Research best practices for each profile's exact versions and libraries.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Sections 5 (Stack Profiles) and 15 (Monorepo Structure)
- Upstream repos for plugin structure patterns:
  - https://github.com/piercelamb/deep-project (`.claude-plugin/`, `hooks/`, `scripts/`, `skills/`)
  - https://github.com/piercelamb/deep-plan
  - https://github.com/piercelamb/deep-implement

**Outputs:**
```
shipwright/
  README.md
  CLAUDE.md                               # For developing shipwright itself
  LICENSE
  pyproject.toml                          # Root project (shared deps)

  shared/
    profiles/
      supabase-nextjs.json                # Complete profile:
                                          #   Stack versions, folder structure,
                                          #   deploy target, test strategy,
                                          #   linting config, CI template

  plugins/                                # Empty plugin dirs with .gitkeep
    shipwright-run/
    shipwright-project/
    shipwright-plan/
    shipwright-build/
    shipwright-test/
    shipwright-changelog/
    shipwright-deploy/

  integration-tests/
  docs/
```

**Verification:**
- [x] Monorepo structure matches spec section 15
- [x] Profile JSONs are valid and contain all required fields
- [x] Profile versions are current (research latest stable versions)
- [x] `CLAUDE.md` documents how to develop shipwright

**Status: COMPLETE** (2026-03-20)

**Notes:**
- Stack versions updated to latest stable (March 2026): Next.js 16.2, React 19.2, Tailwind 4.2, ESLint 10, Zod 4.3, Zustand 5.0, Vitest 4.1, TS 5.9.3
- Plugin dirs include `.claude-plugin/plugin.json` following upstream deep-trilogy pattern
- No README.md created (per convention — CLAUDE.md serves as project documentation)
- Upstream plugin structure researched: deep-project v0.2.1, deep-plan v0.3.2, deep-implement v0.2.1

---

### Task 02: Templates (CLAUDE.md, agent_docs, CI)

**Description**: Create all reusable templates that shipwright-project will use to scaffold new projects.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Section 14 (Best Practices: CLAUDE.md + agent_docs)
- Stack profiles from Task 01

**Outputs:**
```
shipwright/
  shared/
    templates/
      claude-md-template.md               # CLAUDE.md with WHAT/WHY/HOW placeholders
      agent-docs/
        architecture.md.template          # System architecture
        decision-log.md.template          # Decision log with example entry
        conventions.md.template           # Code conventions (profile-specific)
        current-sprint.md.template        # Sprint status
        session-handoff.md.template       # Handoff with all fields
      github-actions/
        ci-nextjs.yml.template            # CI for supabase-nextjs profile
      README.md                           # How to use the templates
```

**Verification:**
- [x] Each template is valid Markdown
- [x] CLAUDE.md template is under 100 lines (22 lines)
- [x] Placeholders use consistent naming (`{PROJECT_NAME}`, `{TECH_STACK}`, etc.)
- [x] CI templates match spec section 12

**Status: COMPLETE** (2026-03-20)

**Notes:**
- 7 templates created: claude-md, architecture, decision-log, conventions, current-sprint, session-handoff, ci-nextjs
- All placeholders use UPPER_SNAKE_CASE in curly braces
- CI template includes: lint, type-check, unit tests, Aikido on PR, Jelastic deploy stubs
- No README.md for templates dir (templates are self-documenting)

---

### Task 03: Shared Utilities (Session Handoff, Decision Log, Config)

**Description**: Create shared Python utilities used across all skills: session handoff generator, decision log writer, config handling.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Section 8 (Context Management)
- Upstream patterns: `deep-implement/scripts/lib/config.py`, `deep-implement/scripts/tools/update_section_state.py`

**Outputs:**
```
shipwright/
  shared/
    scripts/
      lib/
        __init__.py
        config.py                         # Config read/write for all shipwright_*_config.json
        state.py                          # State management (checkpoint, resume detection)
        cost_tracker.py                   # Track estimated tokens + API calls per section
      tools/
        generate_session_handoff.py       # Reads git, config, decision log → writes handoff
        write_decision_log.py             # Appends decision entry (auto-numbering, auto-date)
      hooks/
        check_destructive_migration.sh    # Scans migration SQL for DROP TABLE/COLUMN/lossy ALTER
        validate_command.sh               # Blocks git push --force, rm -rf, unguarded PROD deploy
        verify_documentation.sh           # Checks agent_docs/ files exist and are recent
    tests/
      test_config.py
      test_state.py
      test_generate_session_handoff.py
      test_write_decision_log.py
      test_hooks.py                       # Hook script unit tests (mock file system)
      test_integration.py                 # Templates + handoff + decision log together
```

**Verification:**
- [ ] `uv run pytest shared/tests/ -v` -- all green
- [ ] Session handoff generates all required fields
- [ ] Decision log appends without overwriting, numbering is sequential
- [ ] Config handles all 4 config files (shipwright_run, shipwright_project, shipwright_plan, shipwright_build)
- [ ] Cost tracker writes `estimated_tokens_used` and `estimated_api_calls` per section to shipwright_build_config.json
- [ ] Hook scripts: `check_destructive_migration.sh` detects DROP TABLE/COLUMN in .sql files
- [ ] Hook scripts: `validate_command.sh` blocks dangerous commands (exit 2 on match)

---

## Phase 2: Core Trilogy (Tasks 04-09)

**Goal**: Fork and enhance the three core skills.

---

### Task 04: shipwright-project -- Fork + Plugin Structure

**Description**: Fork `deep-project` into `shipwright/plugins/shipwright-project/`. Set up plugin structure, rename skill, integrate profile system.

**Inputs:**
- https://github.com/piercelamb/deep-project (full repo, v0.2.1)
- `shipwright-sdlc-spec.md` -- Section 6.1 (shipwright-project spec)
- Stack profiles from Task 01

**Outputs:**
```
shipwright/plugins/shipwright-project/
  .claude-plugin/plugin.json              # Renamed to shipwright-project
  hooks/hooks.json
  skills/shipwright-project/
    SKILL.md                              # Renamed + enhanced:
                                          #   - Profile-aware interview depth
                                          #   - Scope detection (Full App, Extension)
                                          #   - CLAUDE.md + agent_docs generation (new step)
    references/                           # Original + new references
  scripts/                                # Original + adapted
  tests/
```

**Changes to SKILL.md:**
- Rename all `deep-project` references to `shipwright-project`
- Rename env vars: `DEEP_SESSION_ID` → `SHIPWRIGHT_SESSION_ID`, `DEEP_PLUGIN_ROOT` → `SHIPWRIGHT_PLUGIN_ROOT`
- Add scope detection logic (infer from user description)
- Add profile-aware interview depth (Full App=deep, Extension=light)
- New step after spec generation: generate CLAUDE.md + agent_docs/ from templates
- Generate `shipwright_project_config.json` instead of `deep_project_config.json`

**Verification:**
- [ ] All existing tests pass (adapted to new names)
- [ ] Plugin loads with `claude --plugin-dir ./plugins/shipwright-project`
- [ ] SKILL.md references correct config file names
- [ ] New step generates valid CLAUDE.md and all 5 agent_docs files

---

### Task 05: shipwright-project -- Profile Integration + Testing

**Description**: Deep integration of stack profiles into shipwright-project. Profile determines folder structure, conventions, and generated templates.

**Inputs:**
- `plugins/shipwright-project/` from Task 04
- Stack profiles from Task 01
- Templates from Task 02

**Outputs:**
- Extended SKILL.md: profile selection based on user description
- Profile-specific convention generation in `agent_docs/conventions.md`
- Profile-specific folder structure in generated specs
- Tests covering supabase-nextjs and custom profiles

**Verification:**
- [ ] "SaaS app with Supabase" → selects supabase-nextjs profile
- [ ] Generated conventions match profile
- [ ] All tests pass

---

### Task 06: shipwright-plan -- Fork + Plugin Structure

**Description**: Fork `deep-plan` into `shipwright/plugins/shipwright-plan/`. Set up plugin structure, rename skill, add E2E test plan generation.

**Inputs:**
- https://github.com/piercelamb/deep-plan (full repo, v0.3.2)
- `shipwright-sdlc-spec.md` -- Section 6.2 (shipwright-plan spec)

**Dependencies (inherited from upstream):**
- `google-genai >= 1.0.0` -- for external LLM review via Gemini
- `openai >= 1.0.0` -- for external LLM review via OpenAI

**Outputs:**
```
shipwright/plugins/shipwright-plan/
  .claude-plugin/plugin.json              # Renamed to shipwright-plan
  agents/                                 # Original subagents (explore, web-search-researcher, section-writer)
  skills/shipwright-plan/
    SKILL.md                              # Renamed + enhanced:
                                          #   - Optional Playwright E2E test plan
                                          #   - current_sprint.md updates
    references/
  scripts/
  config.json                             # External LLM config (Gemini/OpenAI, retry: 3x, timeout: 120s)
  tests/
```

**Changes to SKILL.md:**
- Rename all `deep-plan` references to `shipwright-plan`
- Rename env vars: `DEEP_SESSION_ID` → `SHIPWRIGHT_SESSION_ID`, `DEEP_PLUGIN_ROOT` → `SHIPWRIGHT_PLUGIN_ROOT`
- Preserve SubagentStop JSONL race condition fix from v0.3.1 (critical: wait for flush before read)
- New optional step: generate E2E test plan as `claude-plan-e2e.md`
- Update interview step: also update `agent_docs/current_sprint.md`
- Generate `shipwright_plan_config.json`

**Verification:**
- [ ] All existing tests pass (adapted to new names)
- [ ] Plugin loads correctly
- [ ] When E2E disabled: workflow identical to original
- [ ] When E2E enabled: test plan is generated

---

### Task 07: shipwright-build -- Fork + Plugin Structure

**Description**: Fork `deep-implement` into `shipwright/plugins/shipwright-build/`. Set up plugin structure, rename skill.

**Inputs:**
- https://github.com/piercelamb/deep-implement (full repo, v0.2.1)
- `shipwright-sdlc-spec.md` -- Section 6.3 (shipwright-build spec)

**Outputs:**
```
shipwright/plugins/shipwright-build/
  .claude-plugin/plugin.json              # Renamed to shipwright-build
  agents/                                 # Original subagents (code review, etc.)
  skills/shipwright-build/
    SKILL.md                              # Renamed, base functionality preserved
                                          # Env vars: DEEP_* → SHIPWRIGHT_*
    references/
  scripts/
  tests/
```

**Verification:**
- [ ] All existing tests pass (adapted to new names)
- [ ] Plugin loads correctly
- [ ] TDD loop works as before
- [ ] All `DEEP_` env var references renamed to `SHIPWRIGHT_`

---

### Task 08: shipwright-build -- Enhancements (Commits, Decision Log, Handoff, Migration Safety)

**Description**: Add Conventional Commits, decision log integration, session handoff, auto-push, and migration safety to shipwright-build.

**Inputs:**
- `plugins/shipwright-build/` from Task 07
- Shared utilities from Task 03 (including hook scripts)
- `shipwright-sdlc-spec.md` -- Section 6.3, Section 3.5 (Build-Test-Deploy Loop), Section 5.1 (Database Migrations), Section 11.5 (Quality Gate Hooks)

**Outputs:**
- SKILL.md extended with:
  - Conventional Commits format for all commits
  - Decision log call after code review interviews
  - Session handoff generation before context limits
  - Optional auto-push after commit (`"auto_push": true`)
  - Optional feature branch creation (`"auto_feature_branch": true`)
  - Migration safety: generate down.sql alongside each migration (best-effort)
  - Destructive change detection: DROP TABLE, DROP COLUMN, lossy ALTER TYPE → always warn user, require confirmation regardless of autonomy level
  - DEV migrations: `supabase db push` (automatic)
  - PROD migrations: `supabase db push --dry-run` first, user reviews, then manual confirm
- Integrated shared utilities (`write_decision_log.py`, `generate_session_handoff.py`)
- Quality Gate Hooks in `hooks/hooks.json`:
  - `PreToolUse` (Bash): dangerous command guard via `validate_command.sh`
  - `PostToolUse` (Write|Edit): migration safety gate via `check_destructive_migration.sh`
  - `Stop`: documentation completeness check (agent hook)
- New tests for all enhancements

**Verification:**
- [ ] Commits follow Conventional Commits format (feat:, fix:, etc.)
- [ ] Decision log entries are written after interview triage
- [ ] Session handoff is generated before context warnings
- [ ] Auto-push works when enabled, skipped when disabled
- [ ] Migrations generate corresponding down.sql files
- [ ] Destructive DB changes trigger explicit user warning + confirmation
- [ ] PROD migrations run dry-run before apply
- [ ] Hook: `PreToolUse` blocks `git push --force` and `rm -rf` (exit 2)
- [ ] Hook: `PostToolUse` detects DROP TABLE in migration files and warns
- [ ] Hook: `Stop` verifies decision_log.md and session_handoff.md are current
- [ ] All tests pass

---

### Task 09: Core Trilogy Integration Test

**Description**: Test the full flow from shipwright-project → shipwright-plan → shipwright-build with a mini-project. Sequential, single-agent mode.

**Inputs:**
- All core plugins from Tasks 04-08
- `shipwright-sdlc-spec.md` -- Section 3.5 (Build-Test-Deploy Loop)

**Outputs:**
```
shipwright/
  integration-tests/
    test_core_trilogy_flow.py              # E2E test:
                                          #   - Creates minimal requirements
                                          #   - Runs scripts from each plugin
                                          #   - Verifies all artifacts exist
                                          #   - Checks CLAUDE.md, agent_docs, decision_log, handoff
    fixtures/
      mini-requirements.md                # Minimal test project
    README.md
```

**Verification:**
- [ ] `uv run pytest integration-tests/ -v` -- all green
- [ ] All expected artifacts are generated
- [ ] State recovery works (interrupt + resume from config files)

---

## Phase 3: DevOps Skills (Tasks 10-13)

**Goal**: Build shipwright-changelog, shipwright-test, and shipwright-deploy as new skills.

---

### Task 10: shipwright-changelog -- Plugin + Core Logic

**Description**: Create the shipwright-changelog skill. Parses Conventional Commits, generates Keep-a-Changelog format, creates PRs.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Section 6.5 (shipwright-changelog)
- Plugin structure pattern from Phase 2
- Conventional Commits spec, Keep-a-Changelog format

**Outputs:**
```
shipwright/plugins/shipwright-changelog/
  .claude-plugin/plugin.json
  hooks/hooks.json
  skills/shipwright-changelog/
    SKILL.md                              # Steps: analyze git → categorize → generate → preview → commit → tag → PR
    references/
      conventional-commits.md
      changelog-format.md
  scripts/
    lib/
      git_utils.py                        # get_commits_since_tag, parse_conventional_commit, create_tag
      changelog.py                        # parse_existing_changelog, categorize_commits, generate_entry
    checks/setup-changelog.py
  tests/
    test_git_utils.py
    test_changelog.py
    test_integration.py                   # Real git repo test
  pyproject.toml
  README.md
```

**Verification:**
- [ ] `uv run pytest tests/ -v` -- all green
- [ ] Changelog output is valid Keep-a-Changelog format
- [ ] All Conventional Commit types are recognized
- [ ] Integration test creates/parses real git history

---

### Task 11: shipwright-test -- Plugin + Test Runner

**Description**: Create the shipwright-test skill. Runs unit tests, Playwright E2E, smoke tests, and Aikido security scans.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Sections 6.4 (shipwright-test), 10 (Aikido), 11 (Test Layers)
- Stack profiles from Task 01

**Outputs:**
```
shipwright/plugins/shipwright-test/
  .claude-plugin/plugin.json
  skills/shipwright-test/
    SKILL.md                              # Steps:
                                          #   1. Detect profile → determine test strategy
                                          #   2. Run unit tests (Vitest or pytest)
                                          #   3. Run smoke test (HTTP 200 on DEV URL)
                                          #   4. Run Playwright E2E (if UI, if DEV URL available)
                                          #   5. Run Aikido (if --security flag)
                                          #   6. Report results
                                          #   7. If --fix: auto-fix failures, re-run
    references/
      test-layers.md
      aikido-integration.md
  scripts/
    lib/
      test_runner.py                      # Profile-aware test execution
      smoke_test.py                       # HTTP health check
      aikido_client.py                    # Aikido API integration (stub)
  tests/
  pyproject.toml
  README.md
```

**Verification:**
- [ ] SKILL.md covers all 5 test layers from spec
- [ ] Profile detection works (supabase-nextjs → Vitest+Playwright)
- [ ] `--fix` mode triggers auto-fix loop (max 3 retries)
- [ ] `--security` mode triggers Aikido scan

---

### Task 12: shipwright-deploy -- Jelastic Client + Plugin + Rollback

**Description**: Create the shipwright-deploy skill with a "flavor" architecture. Jelastic is the first deploy flavor, with the design extensible for additional targets in the future. Includes REST API client, smoke test verification, and rollback strategy (DEV: git-based, PROD: Jelastic snapshots).

**Inputs:**
- `shipwright-sdlc-spec.md` -- Sections 6.6 (shipwright-deploy), 13 (Deployment Strategy incl. 13.4 Rollback)
- `jelastic-cloud-deployment.md` -- REST API examples

**Outputs:**
```
shipwright/plugins/shipwright-deploy/
  .claude-plugin/plugin.json
  skills/shipwright-deploy/
    SKILL.md                              # Steps:
                                          #   1. Validate credentials
                                          #   2. Determine flavor + target (Jelastic DEV/PROD)
                                          #   3. PROD: create Jelastic snapshot (pre-deploy)
                                          #   4. Execute deployment via selected flavor
                                          #   5. Wait for ready (polling)
                                          #   6. Run smoke test
                                          #   7. Smoke FAIL? → Rollback (DEV: last green commit, PROD: restore snapshot)
                                          #   8. Report results + log rollback in decision_log.md if triggered
                                          # --rollback flag: manual rollback to last snapshot (PROD only, user confirms)
                                          # Flavor concept: extensible deploy targets
                                          #   - jelastic (first flavor)
                                          #   - future: other providers
    references/
      jelastic-api.md
      deploy-flavors.md
      rollback-strategy.md
  scripts/
    lib/
      jelastic_client.py                  # REST API: deploy, status, wait, create_env, list_envs, create_snapshot, restore_snapshot
      smoke_test.py                       # HTTP 200 + response time + health endpoint
      rollback.py                         # DEV: git-based rollback, PROD: Jelastic snapshot restore
    checks/validate-deploy.py
  tests/
    test_jelastic_client.py
    test_smoke_test.py
    test_rollback.py
  pyproject.toml
  README.md
```

**Verification:**
- [ ] `uv run pytest tests/ -v` -- all green
- [ ] Jelastic client handles HTTP errors (401, 404, 500)
- [ ] Smoke test produces structured report
- [ ] PROD deploy requires explicit confirmation
- [ ] PROD deploy creates snapshot before deploying
- [ ] Smoke failure triggers automatic rollback (max 1 attempt, then escalate)
- [ ] `--rollback` flag restores last PROD snapshot with user confirmation
- [ ] Rollback events are logged in decision_log.md
- [ ] Flavor architecture allows adding new deploy targets without modifying core logic

---

### Task 13: DevOps Integration Test

**Description**: Test shipwright-changelog + shipwright-test + shipwright-deploy together with a mock project.

**Inputs:**
- All DevOps plugins from Tasks 10-12
- Core trilogy from Phase 2

**Outputs:**
```
shipwright/
  integration-tests/
    test_devops_flow.py                   # E2E: build → test → deploy → changelog
```

**Verification:**
- [ ] Full loop executes without errors
- [ ] Changelog reflects committed changes
- [ ] Test results are reported correctly

---

## Phase 4: Orchestrator (Tasks 14-17)

**Goal**: Build shipwright-run as the master orchestrator that ties everything together.

---

### Task 14: shipwright-run -- Core Orchestrator Logic

**Description**: Create the shipwright-run skill with inference engine, scope detection, and profile selection.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Section 3 (shipwright-run: The Orchestrator)
- All skills from Phases 2-3

**Outputs:**
```
shipwright/plugins/shipwright-run/
  .claude-plugin/plugin.json
  skills/shipwright-run/
    SKILL.md                              # Core flow:
                                          #   1. "What do you want to build?" (free text)
                                          #   2. Infer scope, profile, defaults
                                          #   3. "How much control?" (autonomy level)
                                          #   4. Show inferred settings, allow override
                                          #   5. Write shipwright_run_config.json
                                          #   6. Dispatch to shipwright-project
    references/
      inference-rules.md                  # Scope + profile inference logic
      autonomy-levels.md                  # Level 1/2/3 behavior differences
      scope-flows.md                      # Full App, Extension
  scripts/
    lib/
      inference.py                        # Scope + profile inference from description
      orchestrator.py                     # Flow control: which skill runs next
  tests/
    test_inference.py
    test_orchestrator.py
```

**Verification:**
- [ ] Inference correctly maps descriptions to scopes and profiles
- [ ] Autonomy levels change interview depth
- [ ] `shipwright_run_config.json` is written with all required fields
- [ ] Flow dispatches to shipwright-project correctly

---

### Task 15: shipwright-run -- Scope Flows (Full App, Extension)

**Description**: Implement all scope-dependent flows in shipwright-run: Full Application, Extension.

**Inputs:**
- `plugins/shipwright-run/` from Task 14
- `shipwright-sdlc-spec.md` -- Section 3.4 (Scope-Driven Flows)

**Outputs:**
- Extended orchestrator: complete flow for each scope
- Per-split loop: plan → build → test → deploy → changelog → PR
- Inter-skill communication via config files
- Tests for each scope flow

**Verification:**
- [ ] Full App flow: multi-split with full build-test-deploy loop
- [ ] Extension flow: reads existing CLAUDE.md, lighter decomposition

---

### Task 16: shipwright-run -- Iteration Mode

**Description**: Implement `--iterate` mode for quick changes to existing projects.

**Inputs:**
- `plugins/shipwright-run/` from Task 15
- `shipwright-sdlc-spec.md` -- Section 7 (Iteration Mode)

**Outputs:**
- `--iterate` flag handling in SKILL.md
- Context-aware: reads CLAUDE.md + agent_docs
- Light decomposition: 1-2 questions, 1 split, 1-2 sections
- Reuses existing `shipwright_run_config.json`

**Verification:**
- [ ] `--iterate` skips full interview
- [ ] Reads existing project context
- [ ] Creates modification sections (not just new files)
- [ ] Full build-test-deploy loop still executes

---

### Task 17: Orchestrator End-to-End Test

**Description**: Test shipwright-run orchestrating the complete flow: description → deployed app on DEV.

**Inputs:**
- All plugins from Phases 1-4
- `shipwright-sdlc-spec.md`

**Outputs:**
```
shipwright/
  integration-tests/
    test_shipwright_run_e2e.py            # Full E2E: shipwright-run → project → plan → build → test → deploy → changelog
    test_shipwright_run_iterate.py        # Iteration mode E2E
```

**Verification:**
- [ ] Full flow completes from description to deployed state
- [ ] Iteration mode works on existing project
- [ ] All config files and artifacts are consistent
- [ ] Resume from any point works via config files

---

## Phase 5: Agent Teams (Tasks 18-20)

**Goal**: Optional parallel acceleration using Claude Code Agent Teams.

**Prerequisite**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

---

### Task 18: Agent Teams Patterns + Documentation

**Description**: Design and document Agent Teams patterns for each Shipwright skill.

**Inputs:**
- `shipwright-sdlc-spec.md` -- Section 9 (Agent Teams)
- Claude Code Agent Teams documentation

**Outputs:**
```
shipwright/
  docs/agent-teams/
    patterns.md                           # Fan-Out/Fan-In, Cross-Layer, Builder-Validator
    file-scope-assignment.md              # How to assign exclusive file scopes
    cost-benefit.md                       # Token usage, time comparison
    hooks-config.md                       # TeammateIdle + TaskCompleted hooks
```

**Verification:**
- [ ] Each pattern has a concrete Shipwright example
- [ ] File scope rules prevent conflicts
- [ ] Cost-benefit analysis is quantified

---

### Task 19: Agent Teams in shipwright-build (Parallel Sections)

**Description**: Extend shipwright-build with optional Agent Teams mode for parallel section implementation.

**Inputs:**
- `plugins/shipwright-build/` from Phase 2
- `docs/agent-teams/` from Task 18
- `shipwright-sdlc-spec.md` -- Section 9.2

**Outputs:**
- Extended SKILL.md: Agent Teams mode
- File scope assignment script
- Quality gate hooks (TeammateIdle, TaskCompleted)
- Config flag: `"agent_teams_enabled": true|false`

**Verification:**
- [ ] Single-agent mode unchanged when flag is false
- [ ] Parallel sections have non-overlapping file scopes
- [ ] Quality gates run after each agent completes
- [ ] ~40-60% faster for 3+ sections

---

### Task 20: Agent Teams in shipwright-plan (Parallel Research)

**Description**: Extend shipwright-plan with optional parallel research agents.

**Inputs:**
- `plugins/shipwright-plan/` from Phase 2
- `docs/agent-teams/` from Task 18
- `shipwright-sdlc-spec.md` -- Section 9.1

**Outputs:**
- Extended SKILL.md: 3 parallel research agents (codebase, web, competitor)
- Lead synthesizes into `claude-research.md`
- Config flag: `"agent_teams_research": true|false`

**Verification:**
- [ ] Single-agent mode remains default
- [ ] Research is richer with Agent Teams
- [ ] Cost overhead is documented and acceptable

---

## Summary

### Must Have (Phases 1-4): Tasks 01-17

Foundation + Core Trilogy + DevOps + Orchestrator. This delivers:
- Complete SDLC pipeline from description to deployed app
- Stack profiles with best-practice defaults
- TDD + code review + Conventional Commits
- Automated testing (unit + E2E + security)
- Deployment to Jelastic (DEV auto, PROD manual) with extensible flavor architecture + rollback strategy
- Database migration safety (dry-run, destructive change protection, rollback migrations)
- Cost tracking per section (tokens, API calls)
- Changelog + PR generation
- Context management with auto-compact + resume

### Enhancement (Phase 5): Tasks 18-20

Agent Teams. Add when core is stable:
- Parallel section implementation
- Parallel research during planning
- ~40-60% speedup for complex projects

---

## Open Questions (to resolve during implementation)

- Should shipwright-run support `--resume` to pick up after a crash?
- Should we add `/shipwright-status` to show project progress?
- ~~How exactly to handle Supabase migrations in the build loop?~~ → Resolved in spec v3.2 (dry-run + destructive change protection)
- BrowserStack for cross-browser testing before PROD?
- PostHog/Plausible analytics integration?
- Feature Flags (V2): Integration of a feature flagging service for staged rollouts
- Skill Versioning (V2): SemVer for skills, pin versions in shipwright_run_config.json for reproducibility
