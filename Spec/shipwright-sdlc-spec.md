# Shipwright SDLC -- Full Specification

> **Version**: 3.3
> **Date**: 2026-03-16
> **Status**: Design Complete
> **Source**: `deep-trilogy-evolution-v3-decisions.md`, SmartSDLC analysis, Replit Agent 4 gap analysis
> **Changes in 3.3**: Updated upstream versions (v0.2.1/v0.3.2/v0.2.1), added Environment Variables (8.3), Task Management (8.4), Quality Gate Hooks (11.5), External LLM Dependencies (6.2), critical upstream fixes documentation

---

## 1. Current State Analysis

### 1.1 The Deep Trilogy (Upstream)

Three open-source Claude Code plugins form the foundation:

| Plugin | Version | Purpose |
|--------|---------|---------|
| [deep-project](https://github.com/piercelamb/deep-project) | v0.2.1 | Requirements decomposition → splits + specs |
| [deep-plan](https://github.com/piercelamb/deep-plan) | v0.3.2 | Split planning → sections + research |
| [deep-implement](https://github.com/piercelamb/deep-implement) | v0.2.1 | Section implementation → TDD + code review |

**What they do well**: Structured decomposition, TDD loop, code review subagents, checkpoint/resume, unified session management (`DEEP_SESSION_ID`), plugin root discovery (`DEEP_PLUGIN_ROOT`), native Claude Code Tasks integration.

**What they lack**: Deployment, testing beyond unit tests, changelog/git workflow, orchestration, security scanning.

**Critical upstream fixes preserved in fork:**
- deep-plan v0.3.1: SubagentStop JSONL race condition fix (~64% corruption rate before fix)
- All v0.2.0+: Unified `DEEP_SESSION_ID` replacing plugin-specific IDs
- All latest: `DEEP_PLUGIN_ROOT` context injection (replaces slow `find` commands)

### 1.2 The Shipwright Vision

Shipwright is an alternative for developers who want more control and structure over their AI-assisted SDLC. It wraps the Deep Trilogy into a **full SDLC pipeline** -- from user description to deployed, tested, secured application. The prefix `shipwright-` comes from "ship right" -- deliver correctly.

**Key shift**: Instead of running 3 separate skills manually, the user invokes ONE command (`/shipwright-run`) and the agent handles everything.

---

## 2. The Shipwright System Overview

### 2.1 Skills

```
shipwright-run          Orchestrator (master skill, entry point)
shipwright-project      Decomposition (fork of deep-project)
shipwright-plan         Planning (fork of deep-plan)
shipwright-build        Implementation (fork of deep-implement)
shipwright-test         Testing (unit tests + E2E + security scans)
shipwright-changelog    Git sync + changelog + PR
shipwright-deploy       Deployment (extensible, Jelastic as first flavor)
```

### 2.2 Monorepo

All skills live in a single repository: **`shipwright`**

### 2.3 Design Principles

1. **Describe, don't configure** -- User describes what they want, agent infers settings
2. **shipwright-project ALWAYS drives** -- Even a simple task goes through decomposition
3. **Profile determines everything** -- Stack, folders, deploy target, test strategy, CI, UX patterns, architecture decisions (profiles replace most ADRs)
4. **Auto-compact, not manual /clear** -- Agent manages its own context
5. **DEV auto, PROD manual** -- Fast feedback loop, safe production
6. **Every skill works standalone** -- shipwright-run orchestrates, but each skill works independently
7. **Agent Teams optional** -- Everything works single-agent, teams accelerate
8. **Iteration is first-class** -- `--iterate` is the daily workflow after initial build
9. **5-layer testing** -- Unit → Review → Smoke → Playwright → Aikido
10. **agent_docs/ is the real documentation**

### 2.4 The Shipwright AI Framework

Shipwright is not just a set of skills -- it is an **AI Framework**: a structured collection of knowledge, rules, and behaviors that define how software gets built. Every component compounds: each project improves the framework for all future projects.

| Component | Shipwright Implementation | Purpose |
|-----------|--------------------------|---------|
| **Agents** | Code Review Subagent, Research Agents, Healer Agent | Specialized AI personas for specific tasks |
| **Skills** | shipwright-project, -plan, -build, -test, -changelog, -deploy | Auto-loaded context based on SDLC phase |
| **MCPs** | Git MCP, Jira/Linear MCP (planned) | Connections to external data and tools |
| **Prompts** | SKILL.md files per skill | Reusable instructions for consistent behavior |
| **Templates** | CLAUDE.md, agent_docs/, PR, Changelog templates | Standard structures for common outputs |
| **Rules** | Stack Profiles + Architecture Rules | Architectural constraints and conventions |
| **Examples** | agent_docs/conventions.md, visual guidelines | Reference implementations and patterns |

**Why this matters**: Without a framework, every AI interaction starts from zero. With the Shipwright AI Framework, AI becomes a team member who has read all documentation, knows all conventions, and remembers every decision.

**Compound effect**: Every Shipwright project enriches the framework -- decision logs, conventions, and architecture docs accumulate. Your AI Framework grows with every build.

**The Shipwright Stack** (bottom to top):
```
Claude Code              ← Foundation / Engine (powers everything)
Shipwright AI Framework  ← Orchestration (profiles, skills, rules, templates)
Your Project             ← Your business logic, data, requirements
```
Claude Code is the foundation. Shipwright builds on top of it with structured knowledge and process. Your project sits on top, benefiting from both layers.

---

## 3. shipwright-run: The Orchestrator

### 3.1 Core Principles

- `shipwright-run` is the entry point for EVERYTHING
- `shipwright-project` ALWAYS drives implementation, regardless of scope
- User describes what they want → agent infers everything else
- Only ONE real question: autonomy level

### 3.2 UX Flow (Infer, Don't Ask)

```
> /shipwright-run

"What do you want to build?"
> "A SaaS time tracking app with Supabase and Next.js"

[Agent infers from description:]
  Scope:    Full Application
  Profile:  supabase-nextjs
  Deploy:   DEV auto, PROD manual
  Testing:  Vitest + Playwright
  Git:      Auto-push + Changelog + PR

"How much control do you want?"
  ○ Let me drive (Recommended) -- I handle everything, show you milestones
  ○ Co-pilot -- We decide together at key points
  ○ Full control -- You review every step

"I'll use these settings:"
  ✓ Stack:    Next.js 15 + Supabase + Tailwind + shadcn/ui
  ✓ Deploy:   DEV automatically, PROD when you say so
  ✓ Tests:    Vitest + Playwright E2E
  ✓ Git:      Auto-push with changelog
  ✓ Security: Aikido scan before PR

  "Anything you'd change? If not, let's start..."

→ Flows directly into shipwright-project interview
```

**Key UX rules:**
- Only 2 interactions before starting: describe + autonomy
- Everything else inferred from description with smart defaults
- Defaults shown transparently, user can override
- Seamless transition into shipwright-project interview

### 3.3 Inference Rules

| User describes | Agent infers |
|---------------|-------------|
| "SaaS app with Supabase" | Scope: Full App, Profile: supabase-nextjs |
| "Add Stripe billing to my app" | Scope: Extension, reads CLAUDE.md for stack |
| custom | Scope: Custom, User-defined profile |

### 3.4 Scope-Driven Flows

#### Full Application

```
shipwright-project (full interview, multi-split)
  → FOR EACH SPLIT:
      shipwright-plan (full planning, external LLM review)
        → FOR EACH SECTION:
            shipwright-build (TDD, code review)
            → commit → push → auto-deploy DEV
            → shipwright-test (Playwright against DEV URL if UI section)
            → auto-fix if failed → redeploy → retest
        → Aikido security scan
        → shipwright-changelog (per split)
        → PR creation
        → Report: "Split done. DEV live. PR ready."
  → Final: shipwright-changelog (release) → User decides PROD deploy
  → PROD deploy: snapshot → deploy → smoke test → rollback on failure (see 13.4)
  → PROD migrations: dry-run → user confirms → apply (see 5.1)
```

#### App Extension

```
shipwright-project (reads existing CLAUDE.md + agent_docs, shorter interview)
  → Usually single split, fewer sections
  → Same loop as Full Application but smaller scope
  → Knows existing code structure from CLAUDE.md
```

### 3.5 The Build-Test-Deploy Loop (per Section)

```
FOR EACH SECTION:
  ┌─────────────────────────────────────────┐
  │ shipwright-build: TDD Implementation    │
  │   Skeleton → Tests → Implementation    │
  │   Max 3 retries on failure              │
  │                                         │
  │ Unit Tests (Vitest or pytest)            │
  │   Must pass before continuing           │
  │                                         │
  │ Code Review Subagent (adversarial)       │
  │   Auto-fix findings (or ask at          │
  │   milestones for critical ones)         │
  │                                         │
  │ Commit (Conventional Commits)            │
  │ Push to feature branch                   │
  │                                         │
  │ IF section has migrations:               │
  │   DEV: supabase db push (automatic)     │
  │   PROD: dry-run first, user confirms    │
  │   Destructive changes → ALWAYS ask user │
  │                                         │
  │ ┌─ IF profile has deploy target ───────┐ │
  │ │ Auto-deploy to DEV environment       │ │
  │ │ Wait for deploy (smoke: HTTP 200)    │ │
  │ │ Smoke FAIL? → Rollback to last green │ │
  │ │   commit → Log in decision_log.md    │ │
  │ │ IF section has UI:                   │ │
  │ │   Playwright E2E against DEV URL     │ │
  │ │   Fail? → Healer Agent → Redeploy   │ │
  │ │   Max 3 attempts                     │ │
  │ └──────────────────────────────────────┘ │
  │                                         │
  │ Decision log update                      │
  │ Session handoff update                   │
  │ → auto-compact                           │
  └─────────────────────────────────────────┘

AFTER ALL SECTIONS OF A SPLIT:
  Full test suite (Playwright or pytest)
  Aikido security scan
  shipwright-changelog
  PR creation
  Report to user
```

---

## 4. Autonomy Levels

### Level 1: "Let me drive" (Full Auto)

- User gives initial description only
- shipwright-project interview: Claude answers questions itself based on best practices
- Shows summary: "Here's what I understood: ..." → user confirms or corrects
- All code review findings: auto-fix
- Only asks when truly blocked (missing API key, genuinely ambiguous requirement)
- **Best for**: prototypes, MVPs, well-understood patterns

### Level 2: "Co-pilot" (Milestones, Recommended)

- User answers shipwright-project interview
- Agent PROPOSES answers, user confirms or adjusts
  - "I'd use Supabase Auth with Email + Google OAuth. Sound good?"
  - Instead of: "Which auth method do you want?"
- After each split plan: brief summary + "continue?"
- Code review: only critical/security findings shown to user
- Deploy: auto to DEV, manual to PROD
- **Best for**: production projects, balanced quality + speed

### Level 3: "Full control"

- User reviews every plan, every section, every code review finding
- Traditional question-by-question interview
- Most control, slowest
- **Best for**: learning, sensitive projects, compliance requirements

---

## 5. Stack Profiles

### 5.1 supabase-nextjs (Primary App Profile)

```
Frontend:       Next.js 15 (App Router, Server Components)
Backend:        Supabase Edge Functions (Deno/TypeScript)
Database:       Supabase (Postgres + Row Level Security)
Auth:           Supabase Auth (Email, OAuth)
Storage:        Supabase Storage
Realtime:       Supabase Realtime (WebSockets)
Styling:        Tailwind CSS + shadcn/ui
State:          React Server Components + Zustand (client-side)
Testing:        Vitest (unit) + Playwright (E2E)
Security:       Aikido (SAST, SCA, secret detection)
Error Tracking: Sentry (free tier)
Package Mgr:    npm
Linting:        ESLint + Prettier
Deploy:         Jelastic (Node.js environment, output: 'standalone')
CI:             GitHub Actions (test + lint on PR)
```

**Folder Structure:**
```
src/
  app/            # Next.js App Router pages
  components/     # React components
  lib/            # Utility functions
  hooks/          # Custom React hooks
supabase/
  migrations/     # SQL migrations (managed by shipwright-build)
  functions/      # Edge Functions
tests/            # Vitest unit tests
e2e/              # Playwright E2E tests
public/           # Static assets
```

**Jelastic Notes:**
- Use `output: 'standalone'` in `next.config.js`
- Use Supabase Edge Functions for serverless logic (not Next.js API routes)
- Optional: Cloudflare CDN for caching + image optimization
- No ISR available (use SSR or client-side fetch instead)

**Environment Variables:**
```
.env.local          → Local development (not committed)
.env.example        → Template with all required vars (committed)
Jelastic Dashboard  → DEV/PROD secrets (SUPABASE_URL, SUPABASE_KEY, etc.)
```

**UX Patterns (profile abstracts design decisions for non-designers):**
```
Auth Flow:      Login/Signup page with social OAuth buttons (shadcn/ui)
Dashboard:      Sidebar navigation + header + content area
Settings:       Tab-based settings page
Lists:          Data tables with sorting, filtering, pagination (shadcn/ui)
Forms:          Multi-step forms with validation (react-hook-form + zod)
Empty States:   Illustrated empty state with CTA
Error Pages:    404/500 with navigation back
Visual Guide:   Existing visual guidelines from shared/templates/
```

Profiles replace most Architecture Decision Records (ADRs). The profile IS the decision -- stack, auth pattern, DB strategy, folder structure, and UX patterns are pre-decided. Only project-specific decisions (e.g., "use JWT refresh tokens at 7 days") go into `agent_docs/decision_log.md`.

At Autonomy Level 1 ("Let me drive"), shipwright-project and shipwright-plan make UX decisions automatically based on these patterns. Users who can't do design get professional defaults.

**Database Migrations:**
```
shipwright-build creates migration files in supabase/migrations/

DEV:
  supabase db push (automatic after deploy)

PROD:
  supabase db push --dry-run (validation first, shows planned changes)
  User reviews dry-run output
  supabase db push (manual, after explicit confirmation)

Rollback Migrations:
  Every migration file gets a corresponding down.sql (best-effort)
  Agent generates down.sql alongside the up migration
  Used for manual rollback if migration causes issues in PROD

Destructive Change Protection:
  DROP TABLE, DROP COLUMN, ALTER TYPE (lossy) → Agent warns explicitly
  Autonomy level irrelevant -- user MUST confirm destructive DB changes
  Warning includes: what data will be lost, suggested backup step
```

### 5.2 Profile Determines Deploy + Test Strategy

| Profile | Deploy Target | Unit Tests | E2E Tests | Security |
|---------|--------------|-----------|-----------|----------|
| supabase-nextjs | Jelastic DEV (auto) | Vitest | Playwright against DEV URL | Aikido on PR |
| custom | User-defined | User-defined | User-defined | User-defined |

### 5.3 Architecture Rules (per Profile)

Each profile includes architecture rules that the Code Review Subagent enforces automatically:

```json
{
  "profile": "supabase-nextjs",
  "architecture_rules": [
    "Feature modules must not import from other feature modules",
    "All Supabase calls go through lib/supabase/ -- no direct client usage in components",
    "All API calls go through lib/api/ -- no fetch() in components",
    "Server Components by default -- 'use client' only when needed",
    "No business logic in API routes -- use Edge Functions",
    "All database changes via migrations in supabase/migrations/"
  ]
}
```

Rules are checked during code review (Layer 2) and violations are auto-fixed or flagged depending on autonomy level.

### 5.4 Profile Finalization

Stack profiles are starting points. In Task 01, we research best practices and finalize exact versions, additional libraries, and conventions.

---

## 6. Skill Specifications

### 6.1 shipwright-project (Decomposition)

**Fork of**: deep-project v0.2.1

**Purpose**: Decompose user requirements into splits and specs.

**Enhancements over upstream:**
- CLAUDE.md + agent_docs/ generation after interview
- Scope-aware interview depth (Full App = deep, Extension = light)
- Profile-aware folder structure and conventions
- Generates `shipwright_project_config.json` for state tracking

**Output**: `planning/splits/NN-name/spec.md` (always)

**Flow**: spec → plan → sections → build → test → deploy

### 6.2 shipwright-plan (Planning)

**Fork of**: deep-plan v0.3.2

**Purpose**: Plan implementation for a single split.

**Upstream dependencies (inherited):**
- `google-genai >= 1.0.0` -- for external LLM review via Gemini
- `openai >= 1.0.0` -- for external LLM review via OpenAI
- External LLM config via `config.json` (retry logic: 3x, timeout 120s)

**Upstream subagents (inherited):**
- `agents/explore/` -- codebase research
- `agents/web-search-researcher/` -- web research
- `agents/section-writer/` -- parallel section generation

**Enhancements over upstream:**
- Optional Playwright E2E test plan generation
- Optional external LLM review (for quality gate)
- Updates `agent_docs/current_sprint.md`
- Generates `shipwright_plan_config.json` for state tracking

### 6.3 shipwright-build (Implementation)

**Fork of**: deep-implement v0.2.1

**Purpose**: Implement sections via TDD loop with code review.

**Enhancements over upstream:**
- Conventional Commits format
- Decision log writing after interviews
- Session handoff generation before context limits
- Auto-push after commit (configurable)
- Deploy trigger after push (profile-dependent)
- Generates `shipwright_build_config.json` with commit hashes

### 6.4 shipwright-test (Testing)

**Purpose**: Run all test layers and report results.

**Standalone commands:**
```
/shipwright-test              Run all tests (unit + E2E), report results
/shipwright-test --fix        Run tests + auto-fix failures (includes Self-Healing CI)
/shipwright-test --security   Run Aikido security scan
/shipwright-test --ci-heal    Analyze CI failure logs, diagnose root cause, propose or auto-apply fix
```

**Test Layers:**
1. Unit Tests (Vitest or pytest)
2. Smoke Test (HTTP 200 on DEV URL)
3. Playwright E2E (against real DEV environment)
4. Aikido Security (SAST, SCA, secret detection)

**Self-Healing CI:**

When CI fails, `shipwright-test --fix` or `--ci-heal` reads the failure logs with full codebase context, diagnoses the root cause, and either auto-fixes or proposes a fix as PR comment.

```
CI pipeline fails
  → shipwright-test reads GitHub Actions logs
  → Analyzes error with codebase context (CLAUDE.md, agent_docs/)
  → Identifies root cause (test failure, lint error, type error, dependency issue)
  → Auto-fix: commits fix to same branch → CI re-runs
  → Or: posts diagnosis + suggested fix as PR comment
  → Max 3 auto-fix attempts before escalating to user
```

Integrates with GitHub Actions via webhook or manual trigger. Works standalone outside of shipwright-run for any CI failure in any project.

### 6.5 shipwright-changelog (Git Sync + Changelog)

**Purpose**: Generate changelog from git history, create tags, PRs.

**Standalone commands:**
```
/shipwright-changelog         Generate changelog from git history, create tag + push
```

**Features:**
- Conventional Commits parsing
- Keep-a-Changelog format
- Automatic version bumping (semver)
- PR creation with changelog summary
- GitHub Release creation (optional)

### 6.6 shipwright-deploy (Deployment)

**Purpose**: Deploy to configured targets. Extensible via flavors.

**Flavor concept**: shipwright-deploy supports multiple deployment targets through flavors. Jelastic is the first flavor. Additional flavors (Vercel, Railway, Docker, etc.) can be added later.

**Standalone commands:**
```
/shipwright-deploy --env dev          Deploy to DEV (Jelastic flavor)
/shipwright-deploy --env prod         Deploy to PROD (Jelastic flavor, with confirmation)
/shipwright-deploy --flavor jelastic  Explicitly select Jelastic flavor
```

**Features:**
- Jelastic REST API integration (first flavor)
- Smoke test after deploy
- Wait-for-ready with timeout
- Multi-environment support (DEV, PROD)
- Extensible flavor system for future deploy targets

---

## 7. Iteration Mode

After the initial build, iteration is the daily workflow.

### Simple Change

```
> /shipwright-run --iterate "Dashboard should show weekly instead of monthly"

1. Reads existing CLAUDE.md + agent_docs (knows the project)
2. shipwright-project (light): 1-2 questions max, creates 1 split with 1-2 sections
3. shipwright-plan (light): quick plan, no external LLM review
4. shipwright-build: implement → test → commit → push → deploy DEV
5. shipwright-test: Playwright against DEV (if UI change)
6. "Change live on DEV. Look good?"
```

### Bigger Change

```
> /shipwright-run --iterate "Add Stripe billing with subscription management"

1. Reads existing project context
2. shipwright-project: fuller interview (pricing tiers? trial? invoices?)
3. shipwright-plan: full planning (possibly multi-section)
4. shipwright-build: full TDD loop
5. Deploy + test + Aikido
6. Changelog + PR
```

### What --iterate Does Differently

- Reads existing CLAUDE.md and agent_docs (context-aware)
- Does NOT regenerate architecture/conventions
- Focuses on what's NEW or CHANGED
- Creates sections that MODIFY existing code (not just new files)
- Uses existing `shipwright_run_config.json` (no re-configuration)

---

## 8. Context Management

### 8.1 Auto-Compact (NOT manual /clear)

The agent handles context automatically:

1. Before context gets full → writes `session_handoff.md`
2. Claude Code auto-compacts (compresses older messages)
3. After compaction → reads `session_handoff.md` + config files to recover state
4. User never needs to `/clear` manually
5. If context is truly exhausted → agent writes handoff, tells user to `/clear`, user restarts `/shipwright-run` which auto-resumes from last checkpoint

### 8.2 State Files (filesystem = single source of truth)

```
shipwright_run_config.json           # Scope, profile, autonomy, deploy config, inferred settings
shipwright_project_config.json       # Split state (which splits completed)
shipwright_plan_config.json          # Per-split planning state
shipwright_build_config.json         # Per-section implementation state (commit hashes)
agent_docs/session_handoff.md       # Human-readable recovery context
agent_docs/decision_log.md          # All decisions with rationale
```

### 8.3 Environment Variables

Shipwright renames the upstream Deep Trilogy environment variables to avoid conflicts:

```
SHIPWRIGHT_SESSION_ID          # Unified session ID across all shipwright-* plugins
                               # (upstream: DEEP_SESSION_ID)
                               # Set by SessionStart hook, shared across all skills

SHIPWRIGHT_PLUGIN_ROOT         # Absolute path to the active plugin directory
                               # (upstream: DEEP_PLUGIN_ROOT)
                               # Injected via context, replaces slow `find` commands

CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS   # Set to 1 to enable Agent Teams mode (optional)
```

**Renaming rule**: Every `DEEP_` prefix in upstream code becomes `SHIPWRIGHT_` during fork. This applies to environment variables, config file prefixes (`deep_*_config.json` → `shipwright_*_config.json`), and internal references.

### 8.4 Task Management

Shipwright uses **native Claude Code Tasks** (not the legacy TodoWrite system) for tracking progress within sessions. This aligns with deep-plan v0.2.0+ which removed TodoWrite in favor of native Tasks with dependency tracking.

---

## 9. Agent Teams (Optional Enhancement)

When `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set, shipwright-run automatically uses teams.

### 9.1 During Planning (shipwright-plan)

```
Lead Agent:       Coordinates, interviews user
Research Agent 1: Codebase exploration
Research Agent 2: Web research
Research Agent 3: Competitor/alternative analysis
→ Lead synthesizes into claude-research.md
```

### 9.2 During Implementation (shipwright-build)

```
Lead Agent:       Coordinates, commits, deploys
Worker Agent 1:   Section A (exclusive file scope)
Worker Agent 2:   Section B (exclusive file scope)
Review Agent:     Adversarial code review (read-only)
→ Sections without dependencies run in parallel
→ ~40-60% faster for 3+ sections
```

### 9.3 Always Optional

- All skills work without Agent Teams (single-agent mode)
- Agent Teams is an acceleration, not a requirement
- Detected automatically from environment variable

---

## 10. Security: Aikido Integration

### 10.1 When Aikido Runs

```
DURING BUILD LOOP:     No (too frequent for free tier)
AFTER SPLIT COMPLETE:  Yes, automatic (1x per split) ← fits free tier
STANDALONE:            /shipwright-test --security (whenever user wants)
IN CI (later):         On PR to main (GitHub Actions)
```

### 10.2 What Aikido Covers (complementary to code review)

```
Code Review Subagent covers:     Aikido covers:
  Logical security issues          SAST (code vulnerabilities)
  Missing auth checks              SCA (dependency CVEs)
  Architecture concerns            Secret detection
  Business logic flaws             DAST (runtime vulnerabilities)
                                   Container scanning
```

### 10.3 Aikido in the Flow

```
All sections of split done
  → Full test suite (Playwright or pytest)
  → Aikido security scan
  → Critical findings? → shipwright-build auto-fixes → re-scan
  → Medium findings? → User decides (at milestone level)
  → Low findings? → Documented in decision_log.md
  → shipwright-changelog
  → PR creation (Aikido report attached)
```

---

## 11. Test Layers

```
Layer 1: Unit Tests (Vitest/pytest)
  → Per section, during shipwright-build TDD loop
  → Tests individual functions with mocked dependencies

Layer 2: Code Review (adversarial subagent)
  → Per section, catches logical issues
  → Security, architecture, business logic

Layer 3: Smoke Test (HTTP 200)
  → After each deploy to DEV
  → Verifies app starts and responds

Layer 4: Playwright E2E (against real DEV)
  → Full user flows in real browser
  → Real Supabase, real auth, real API calls
  → THIS IS the integration test

Layer 5: Aikido Security
  → After split complete, before PR
  → SAST, SCA, secret detection, DAST
```

No separate "integration test" layer needed -- Playwright against DEV covers it.

---

## 11.5. Quality Gate Hooks

Shipwright uses Claude Code Hooks as automated quality gates throughout the SDLC pipeline. Hooks fire on lifecycle events and can block actions if conditions aren't met.

### 11.5.1 Hook Types Used

| Type | Speed | Use Case |
|------|-------|----------|
| **Command** | ~100ms | Fast file checks (exists? pattern match? timestamp?) |
| **Prompt** | ~2-5s | Medium complexity (commit message format, naming conventions) |
| **Agent** | ~5-15s | Complex validation (documentation completeness, test coverage) |

### 11.5.2 Shipwright Hooks

```
Hook 1: Documentation Completeness (Stop event)
  Type:    Agent
  Fires:   When Claude finishes responding
  Checks:  1) agent_docs/decision_log.md updated if decisions were made
           2) agent_docs/session_handoff.md exists and is current
           3) All shipwright_*_config.json files are consistent
  Action:  Blocks stop, feeds missing items back to Claude

Hook 2: Migration Safety Gate (PostToolUse event, matcher: Write|Edit)
  Type:    Command
  Fires:   After writing/editing files in supabase/migrations/
  Checks:  Scans for DROP TABLE, DROP COLUMN, ALTER TYPE (lossy)
  Action:  Blocks and warns -- destructive changes require explicit user confirmation

Hook 3: Dangerous Command Guard (PreToolUse event, matcher: Bash)
  Type:    Command
  Fires:   Before executing shell commands
  Checks:  Blocks git push --force, rm -rf, supabase db push without --dry-run on PROD
  Action:  Blocks execution, stderr message fed back to Claude

Hook 4: Section Quality Gate (TaskCompleted event, Agent Teams only)
  Type:    Agent
  Fires:   When a task is marked complete in Agent Teams mode
  Checks:  Tests pass, code review done, Conventional Commits format, decision_log updated
  Action:  Blocks task completion until all criteria met
```

### 11.5.3 Hook Location

Hooks are bundled per plugin in `hooks/hooks.json` and reference scripts via `$SHIPWRIGHT_PLUGIN_ROOT`:

```
plugins/shipwright-build/
  hooks/
    hooks.json                          # Hook definitions
  scripts/
    hooks/
      check-destructive-migration.sh    # Migration safety gate
      validate-command.sh               # Dangerous command guard
```

### 11.5.4 Performance Budget

- **Command hooks** on every tool call: acceptable (~100ms overhead)
- **Agent hooks** only on `Stop` and `TaskCompleted`: acceptable (runs once, not per tool call)
- **Never** use agent hooks on `PreToolUse` or `PostToolUse` -- too frequent, too expensive

---

## 12. CI/CD: GitHub Actions

### 12.1 Why Needed

Jelastic Git-Push-Deploy doesn't run tests. GitHub Actions is the safety net.

### 12.2 Pipeline

```yaml
# .github/workflows/ci.yml
on:
  push:
    branches: [develop, feature/*]
  pull_request:
    branches: [main]

jobs:
  test:
    - Lint (ESLint/Prettier or ruff)
    - Type check (TypeScript or mypy)
    - Unit tests (Vitest or pytest)
    - Aikido security scan (on PR only)

  deploy-dev:
    needs: test
    if: github.ref == 'refs/heads/develop'
    - Trigger Jelastic DEV deploy

  deploy-prod:
    needs: test
    if: github.ref == 'refs/heads/main'
    - Trigger Jelastic PROD deploy
```

### 12.3 Who Creates This

shipwright-build generates `.github/workflows/ci.yml` as part of the first section (foundation/setup). It's part of the stack profile convention.

---

## 13. Deployment Strategy

### 13.1 Environments

```
Jelastic DEV    ← Auto-deploy from feature/* and develop branches
Jelastic PROD   ← Manual deploy (user merges PR to main, or /shipwright-deploy --env prod)
```

### 13.2 Branch Strategy

```
main            → PROD (protected, PRs only)
develop         → DEV (auto-deploy)
feature/{name}  → DEV (auto-deploy, created by shipwright-build)
```

### 13.3 Cost Estimate

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Jelastic DEV | CHF 5-10 | Minimal |
| Jelastic PROD | CHF 10-30 | Auto-scaling |
| Supabase | CHF 0-25 | Free tier or Pro |
| Sentry | CHF 0 | Free tier |
| Aikido | CHF 0 | Free tier |
| **Total** | **CHF 15-65/month** | Fully Swiss-hosted |

### 13.4 Rollback Strategy

```
DEV Environment:
  Deploy fails (smoke test ≠ HTTP 200)
    → Redeploy last successful commit (git-based)
    → Automatic, no user interaction needed
    → Log rollback event in decision_log.md

PROD Environment:
  Pre-deploy:
    → Jelastic environment snapshot (automatic before deploy)
  Deploy fails (smoke test ≠ HTTP 200):
    → Restore Jelastic snapshot (automatic)
    → Max 1 auto-rollback attempt
    → If rollback also fails → escalate to user immediately
    → Log rollback event + root cause in decision_log.md

  User-triggered rollback:
    → /shipwright-deploy --rollback (restores last snapshot)
    → Always requires user confirmation
```

**Key rule**: Rollback is always to a known-good state, never to "previous code that might also be broken." DEV uses git history (last green commit), PROD uses infrastructure snapshots.

---

## 14. Best Practices: CLAUDE.md + agent_docs/

### 14.1 CLAUDE.md Template (generated by shipwright-project)

```markdown
# {Project Name}

## WHAT
- **Stack**: {inferred from profile}
- **Structure**: {folder structure from profile}
- **Key Files**: {main entry points}

## WHY
- **Purpose**: {from user description}
- **Architecture**: {from shipwright-project interview}
- **Decisions**: See agent_docs/decision_log.md

## HOW
- **Build**: {from profile: npm run build / pytest}
- **Test**: {from profile: npm test / pytest}
- **Deploy DEV**: git push (auto)
- **Deploy PROD**: /shipwright-deploy --env prod

## Context
- **Agent Docs**: agent_docs/
- **Planning**: planning/
- **Shipwright Config**: shipwright_run_config.json
```

### 14.2 agent_docs/ Directory

```
agent_docs/
  architecture.md         # System architecture (shipwright-project creates)
  decision_log.md         # Every decision with rationale (shipwright-build maintains)
  conventions.md          # Code conventions from profile (shipwright-project creates)
  current_sprint.md       # Active tasks (shipwright-plan updates)
  session_handoff.md      # Context for recovery (auto-updated)
```

### 14.3 Decision Log Format (ADR-style)

Only decisions NOT already covered by the stack profile go here. Profile-level decisions (stack, auth pattern, DB strategy, folder structure, UX patterns) are implicit -- the profile IS the ADR for those.

```markdown
## ADR-012 | 2026-02-14 | Section 03: Auth System | Commit abc1234

### Status: Accepted

### Context
Code review found session-based auth, plan specified JWT.
Profile defines Supabase Auth, but token refresh strategy is project-specific.

### Decision
Keep JWT, refresh token set to 7 days.

### Consequences
- Stateless for horizontal scaling on Jelastic
- All API routes need middleware
- Alternatives rejected: Session cookies (scaling), OAuth-only (complexity)
```

---

## 15. Monorepo Structure

```
shipwright/
  README.md
  CLAUDE.md
  LICENSE

  plugins/
    shipwright-run/                     # Orchestrator
      .claude-plugin/plugin.json
      skills/shipwright-run/SKILL.md
      scripts/

    shipwright-project/                 # Fork of deep-project
      .claude-plugin/plugin.json
      skills/shipwright-project/SKILL.md
      scripts/
      tests/

    shipwright-plan/                    # Fork of deep-plan
      .claude-plugin/plugin.json
      agents/
      skills/shipwright-plan/SKILL.md
      scripts/
      tests/

    shipwright-build/                   # Fork of deep-implement
      .claude-plugin/plugin.json
      agents/
      skills/shipwright-build/SKILL.md
      scripts/
      tests/

    shipwright-test/                    # NEW
      .claude-plugin/plugin.json
      skills/shipwright-test/SKILL.md
      scripts/

    shipwright-changelog/               # NEW
      .claude-plugin/plugin.json
      skills/shipwright-changelog/SKILL.md
      scripts/
      tests/

    shipwright-deploy/                  # NEW
      .claude-plugin/plugin.json
      skills/shipwright-deploy/SKILL.md
      scripts/
      tests/

  shared/
    profiles/                     # Stack profile definitions
      supabase-nextjs.json
    templates/                    # CLAUDE.md, agent_docs templates
    scripts/                      # Shared Python utilities

  integration-tests/
  docs/
```

---

## 16. Standalone Skill Usage

Every skill works independently outside of shipwright-run:

```
/shipwright-run "Build a time tracking app"
  → Full orchestrated flow

/shipwright-run --iterate "Change dashboard to weekly view"
  → Quick iteration on existing project

/shipwright-project "Build a time tracking app"
  → Decomposition only (standalone)

/shipwright-plan @planning/splits/01-auth/spec.md
  → Plan a single split

/shipwright-build @planning/splits/01-auth/sections/.
  → Implement sections from a plan

/shipwright-test
  → Run all tests (unit + E2E), report results
/shipwright-test --fix
  → Run tests + auto-fix failures
/shipwright-test --security
  → Run Aikido security scan

/shipwright-changelog
  → Generate changelog from git history, create tag + push

/shipwright-deploy --env dev
  → Deploy to DEV (Jelastic flavor)
/shipwright-deploy --env prod
  → Deploy to PROD (Jelastic flavor, with confirmation)
/shipwright-deploy --flavor jelastic
  → Explicitly select Jelastic flavor
```

---

## 17. Metrics & KPIs

Shipwright tracks build metrics automatically. These feed into Shipwright Agent Backend dashboards and provide ROI evidence for enterprise adoption.

**Per-Build Metrics (tracked in shipwright_build_config.json):**
- Build duration per section (wall clock)
- Test pass rate (unit + E2E)
- Code review finding count (by severity)
- Auto-fix success rate
- Deploy success/failure
- Estimated tokens used (total tokens per section)
- Estimated API calls (number of LLM calls per section)

**Per-Project Metrics (aggregated in Agent Backend):**
- Time from requirements to first deploy
- Total test coverage generated
- Security findings caught before PR
- Compliance evidence artifacts generated
- Number of auto-healed CI failures
- Aggregated token usage and API call count per project (cost transparency)

**Onboarding Value:**
Every Shipwright project generates comprehensive `agent_docs/` -- not just for AI, but for every new team member. CLAUDE.md, architecture.md, conventions.md, and decision_log.md serve as living onboarding documentation that stays current with the codebase.

---

## 18. Open Questions for Later

- Should shipwright-run support `--resume` to pick up after a crash?
- Should we add `/shipwright-status` to show project progress?
- ~~How exactly to handle Supabase migrations in the build loop (supabase db push vs migration files)?~~ → Resolved in v3.2 (Section 5.1: dry-run + destructive change protection)
- BrowserStack for final cross-browser testing before PROD?
- PostHog/Plausible analytics integration?
- Feature Flags (V2): Integration of a feature flagging service (LaunchDarkly, Unleash, or custom Supabase-based solution) for staged rollouts and environment parity beyond env vars
- Skill Versioning (V2): SemVer for skills, `shipwright_run_config.json` pins skill versions used during build for reproducibility. Breaking changes in skills need a migration path

---

## 19. Source Material

| Document | Purpose |
|----------|---------|
| `deep-trilogy-evolution-brief.md` | Original brief (3 dimensions) |
| `deep-trilogy-evolution-v2.md` | Extended to 6 dimensions (superseded by this doc) |
| `deep-trilogy-evolution-v3-decisions.md` | All design decisions (source of this spec) |
| `jelastic-cloud-deployment.md` | Jelastic research |

**Upstream repos (analyzed in design sessions):**
- [deep-project](https://github.com/piercelamb/deep-project) v0.2.1
- [deep-plan](https://github.com/piercelamb/deep-plan) v0.3.2
- [deep-implement](https://github.com/piercelamb/deep-implement) v0.2.1
