# Shipwright -- The AI-Powered SDLC for Claude Code

## 1. What is Shipwright?

### The Problem

AI-assisted coding promises speed, but speed without structure produces fragile, untested, undocumented software. "Vibe coding" -- asking an AI to write code from a loose description -- skips requirements analysis, testing, security review, and deployment planning. The result works on the happy path and breaks everywhere else.

### The Solution

Shipwright is a structured Software Delivery Lifecycle (SDLC) pipeline built on Claude Code. Instead of generating code from a prompt and hoping for the best, Shipwright runs your project through eight distinct phases -- from requirements decomposition to deployment -- in a single command:

```
/shipwright-run "A SaaS time tracking app with Supabase and Next.js"
```

Shipwright infers your stack, interviews you about requirements, designs the UI, plans the implementation, builds with TDD, runs tests, scans for vulnerabilities, deploys, and generates a changelog. You stay in control; the pipeline does the heavy lifting.

### What You Get

- **IREB-aligned specs** from a structured requirements interview - testable acceptance criteria from day one
- **HTML design mockups** with visual guidelines, design tokens, and a browser-based review viewer
- **Test-Driven Development** with automated unit, integration (real DB), pgTAP (RLS), smoke, E2E, and design fidelity testing
- **Design fidelity verification** - code-level comparison of implementation vs mockup HTML catches UI drift automatically
- **Compliance documentation** generated automatically: traceability matrix, test evidence, change history, SBOM
- **Architecture docs** (`architecture.md`, `conventions.md`, `decision_log.md`) kept in sync by every phase
- **A constitution** with mechanical enforcement - hooks block dangerous actions, not advisory prose
- **Full artifact traceability** - every requirement traces to build events, test results, and commits
- **Daily iteration** with `/shipwright-iterate` - complexity-adaptive changes that keep all artifacts in sync

### How It Works

```
User Description
      |
      v
  SHIPWRIGHT-RUN ........... Infer scope, profile, autonomy --> dispatch
      |
      v
  SHIPWRIGHT-PROJECT ....... Interview --> Split --> IREB Specs --> CLAUDE.md
      |
      v
  SHIPWRIGHT-DESIGN ........ Specs --> HTML Mockups --> Review Viewer --> Feedback Loop
      |
      v  (per split)
  SHIPWRIGHT-PLAN .......... Research --> Plan --> External LLM Review --> Sections
      |
      v  (per section)
  SHIPWRIGHT-BUILD ......... TDD --> Code Review --> Conventional Commit
      |                        ↑
      |              /shipwright-preview (local browser preview, available after first split)
      v
  SHIPWRIGHT-TEST .......... Unit --> Integration (real DB) --> pgTAP --> Smoke --> E2E --> Visual
      |
      v
  SHIPWRIGHT-SECURITY ...... Scan (OSS/Aikido) --> Classify --> Remediation Loop
      |
      v
  SHIPWRIGHT-DEPLOY ........ Jelastic (Infomaniak) --> Smoke Test --> Rollback on Failure
      |
      v
  SHIPWRIGHT-CHANGELOG ..... Parse Commits --> Changelog --> Version Tag --> PR
      |
      v
  SHIPWRIGHT-COMPLIANCE .... Traceability Matrix --> Test Evidence --> SBOM

  After initial build, ongoing changes use /shipwright-iterate:
  SHIPWRIGHT-ITERATE ....... Classify Intent --> Assess Complexity --> Adaptive Pipeline
```

Each phase is a standalone Claude Code plugin. The orchestrator (`shipwright-run`) chains them together, but you can also invoke any skill individually.

### Design Principles

Shipwright follows nine design principles that shape every decision in the pipeline:

1. **Describe, don't configure.** You describe what you want to build in plain language. Shipwright infers the stack profile, scope, and settings automatically.
2. **DEV auto, PROD manual.** Development deploys happen automatically for fast feedback. Production deploys always require explicit confirmation.
3. **Every skill works standalone.** The orchestrator coordinates the pipeline, but each skill (project, plan, build, test, etc.) can be invoked independently.
4. **Test-first.** Shipwright follows TDD with IREB acceptance criteria, producing testable specifications from day one.
5. **All work is tracked uniformly.** Build sections and iterate changes are events in the same append-only log (`shipwright_events.jsonl`). The initial build is just the first batch of events. `/shipwright-iterate` is designed for daily workflow after the initial build -- quick changes with minimal overhead.
6. **Resume anywhere.** All pipeline state is file-based. The event log is the single source of truth for what happened, when, and with what test results. You can interrupt a run, close your session, and resume exactly where you left off.
7. **Migration safety.** Destructive database changes (DROP TABLE, DROP COLUMN) always require explicit confirmation before execution.
8. **Linters over instructions.** Mechanical enforcement through hooks beats advisory prose. Hooks block dangerous actions deterministically rather than relying on the agent to follow written rules.
9. **Progressive disclosure.** CLAUDE.md stays lean (around 200 lines). Detailed architecture docs, conventions, and decision logs live in `agent_docs/`.

### Integrated Learnings

Shipwright's architecture and quality practices were shaped by three external sources.

#### Claude Code Source Code Leak

When Claude Code's source code was exposed, it revealed the internal rules Anthropic uses to govern their own AI coding agent. Shipwright adopted the most impactful ones into its constitution.

**Rules added from the leak:**

- **Never claim "all tests pass" when output shows failures.** Report actual numbers honestly. This was learned the hard way during real Shipwright builds.
- **Re-read files before editing in long sessions.** After 10+ messages or context compaction, cached file content may be stale. Always re-read before modifying.
- **State explicitly when search results may be truncated.** Tool results can be silently cut off. Never work with incomplete data without flagging it.
- **Verification after edits should include linting and type-checking**, not just tests. Run `tsc --noEmit`, `npm run lint`, or equivalent project tools before reporting success.
- **Quality calibration.** When the user asks for production-grade work, ask: "What would a senior, perfectionist developer reject in code review?" -- and fix all of it.

**Rules Shipwright already enforced before the leak:**

- "Run tests before committing" -- Shipwright's constitution required this from day one.
- "Keep files under 300 lines" -- covers Claude Code's file read strategy (2,000-line cap) indirectly.
- "Fix the code, not the test" -- aligns with Claude Code's quality calibration philosophy.

#### Addy Osmani's Agent Skills

Shipwright integrated patterns from Osmani's [agent-skills](https://github.com/addyosmani/agent-skills) repository into its review and build infrastructure:

- **5-axis code review framework** -- correctness, readability, architecture, security, performance. Adopted into the code-reviewer subagent and the self-review checklist that runs on every section.
- **Anti-rationalization tables** -- structured prompts that prevent agents from explaining away test failures or rationalizing skipped checks. Applied to code review, self-review, and test result interpretation.
- **Performance and simplification patterns** -- reference docs for the build phase covering Core Web Vitals, bundle optimization, and code simplification heuristics.

#### Anthropic Claude Architect Certification

Aligned with the five domains of Anthropic's [Claude Certified Architect](https://www.anthropic.com/certification) exam guide:

- **Constitution-driven boundaries** -- the ALWAYS / ASK FIRST / NEVER tiers that govern agent behavior (see Chapter 7.5).
- **Structured error propagation** -- errors classified into 4 severity categories with specific recovery strategies.
- **Compliance enforcement hooks** -- `PreToolUse` hooks that soft-block (exit code 2) when RTM coverage drops or security scans are stale. Overrides are logged to `compliance_overrides.log`.
- **Path-specific rules** -- `.claude/rules/` templates for tests, API routes, migrations, components, and config files, so the agent gets context-appropriate guidance per file type.
- **Few-shot examples in subagent definitions** -- code-reviewer, section-writer, and opus-plan-reviewer include worked examples so agents produce consistent output.
- **Progressive disclosure** -- CLAUDE.md stays lean (~200 lines), detailed docs live in `agent_docs/`.

---

## 2. Prerequisites and Installation

### Required Tools

| Tool | Version | Purpose | Install |
|------|---------|---------|---------|
| Claude Code | Latest | AI agent runtime (CLI or VSCode Extension) | [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code) -- requires Pro or Max subscription |
| Python | 3.11+ | Plugin scripts | Managed by uv (installed automatically) |
| uv | Latest | Python package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (macOS/Linux) or `winget install astral-sh.uv` (Windows) |
| Git | 2.x+ | Version control | [git-scm.com](https://git-scm.com) |

### Optional Tools

| Tool | Needed For | Install |
|------|-----------|---------|
| GitHub CLI (`gh`) | PR creation, changelog | `brew install gh` or `winget install GitHub.cli` |
| Node.js 22.x | supabase-nextjs profile | [nodejs.org](https://nodejs.org) or `nvm install 22` |
| Supabase CLI | Database migrations | `npm install -g supabase` |
| Mermaid Preview (VSCode) | Rendering compliance Mermaid diagrams | VSCode Extensions: "Markdown Preview Mermaid Support" |

### Installation Option A: Marketplace (Recommended)

The marketplace approach works in both the VSCode Extension and the CLI. Add the following to `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "shipwright": {
      "source": {
        "source": "github",
        "repo": "svenroth-ai/shipwright"
      }
    }
  },
  "enabledPlugins": {
    "shipwright-run@shipwright": true,
    "shipwright-project@shipwright": true,
    "shipwright-design@shipwright": true,
    "shipwright-plan@shipwright": true,
    "shipwright-build@shipwright": true,
    "shipwright-test@shipwright": true,
    "shipwright-security@shipwright": true,
    "shipwright-deploy@shipwright": true,
    "shipwright-changelog@shipwright": true,
    "shipwright-compliance@shipwright": true,
    "shipwright-iterate@shipwright": true,
    "shipwright-preview@shipwright": true
  }
}
```

If you already have content in `settings.json`, merge these two keys into your existing file. Alternatively, in the VSCode Extension, type `/plugins`, open the Marketplaces tab, and add `svenroth-ai/shipwright`.

Then clone and install Python dependencies:

```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync
```

### Installation Option B: Shell Alias (CLI Only)

If you prefer not to register a marketplace, define a shell alias that loads all plugins.

**bash / zsh** -- add to `~/.bashrc` or `~/.zshrc`:

```bash
shipwright() {
  claude \
    --plugin-dir ~/shipwright/plugins/shipwright-run \
    --plugin-dir ~/shipwright/plugins/shipwright-project \
    --plugin-dir ~/shipwright/plugins/shipwright-plan \
    --plugin-dir ~/shipwright/plugins/shipwright-build \
    --plugin-dir ~/shipwright/plugins/shipwright-test \
    --plugin-dir ~/shipwright/plugins/shipwright-deploy \
    --plugin-dir ~/shipwright/plugins/shipwright-changelog \
    "$@"
}
```

**PowerShell** -- add to `$PROFILE`:

```powershell
function shipwright {
  claude `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-run `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-project `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-plan `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-build `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-test `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-deploy `
    --plugin-dir $env:USERPROFILE\shipwright\plugins\shipwright-changelog `
    @args
}
```

### Platform Notes

**Windows:** Claude Code uses bash (Git Bash). Ensure [Git for Windows](https://gitforwindows.org/) is installed. Use the PowerShell alias or run from Git Bash. uv works natively: `winget install astral-sh.uv`.

**macOS:** Install prerequisites via Homebrew: `brew install git gh node uv`. Xcode Command Line Tools needed: `xcode-select --install`.

**Linux:** Most straightforward setup. All tools available via package managers. Ensure Python 3.11+ (some distros ship older versions).

**WSL:** Alternative to native Windows. All Unix commands work natively in WSL2. Recommended if you prefer a Linux workflow on Windows.

### Verification

Open Claude Code and type:

```
/shipwright-run
```

You should see the SHIPWRIGHT-RUN banner. If you get "Plugin not found", check that your shell alias is loaded (`type shipwright`) or that your `settings.json` paths are correct.

---

## 3. Your First Project

### Step by Step

Create a new project directory, initialize Git, and launch Shipwright:

```bash
mkdir ~/my-first-app && cd ~/my-first-app
git init
```

If you installed via marketplace, open Claude Code in this directory and type:

```
/shipwright-run "A simple todo list app with Supabase and Next.js"
```

If you installed via shell alias, start with `shipwright` and then type the command above.

### What to Expect

The pipeline runs through these phases in sequence:

1. **SHIPWRIGHT-RUN** -- The orchestrator infers your stack (`supabase-nextjs`), scope (`Full Application`), and autonomy level (`guided`). You confirm or adjust before proceeding.
2. **SHIPWRIGHT-PROJECT** -- Asks 5-10 questions about your requirements, then decomposes them into splits (logical work units) with IREB-aligned specifications and acceptance criteria.
3. **SHIPWRIGHT-DESIGN** -- Generates interactive HTML mockups from your specs. You review them in a browser-based viewer and provide feedback until satisfied.
4. **SHIPWRIGHT-PLAN** -- Creates a detailed implementation plan for each split. Optionally sends the plan to external LLMs (Gemini, OpenAI) for independent review.
5. **SHIPWRIGHT-BUILD** -- Implements each section using TDD: writes tests first, then code, then runs a code review subagent. Each section gets a Conventional Commit on a feature branch.
6. **SHIPWRIGHT-TEST** -- Runs the full test suite: unit tests (Vitest), integration tests (real DB), pgTAP (RLS), smoke tests, and Playwright E2E tests.
7. **SHIPWRIGHT-DEPLOY** -- Deploys to Jelastic DEV (if configured). Runs a smoke test against the live environment and rolls back on failure.
8. **SHIPWRIGHT-CHANGELOG** -- Parses Conventional Commits, generates a changelog entry, suggests a semver bump, and opens a pull request.

Estimated time for a small app: 15-30 minutes.

### Guided vs Autonomous Mode

Shipwright defaults to **guided mode**. At each phase transition, you are asked whether to continue, review artifacts first, or stop. This gives you full control over the process.

In **autonomous mode**, the pipeline runs without pausing between phases. The interactive phases (requirements interview, design review) still require your input, but build, test, and changelog run unattended. Production deployment always requires confirmation regardless of mode.

You choose your mode during the settings confirmation step at the start of each run.

### Alternative Invocations

You are not limited to a single command. Shipwright supports several input methods:

```bash
# Start from a requirements file instead of a description
/shipwright-run @requirements.md

# Quick iteration on an existing project (minimal questions, fast pipeline)
/shipwright-iterate "Add dark mode toggle"

# Use individual skills directly
/shipwright-project "Build a dashboard"
/shipwright-plan @01-auth/spec.md
/shipwright-build @sections/01-models.md
/shipwright-test
/shipwright-changelog
```

Every skill works standalone. You can run `/shipwright-test` without having used the rest of the pipeline, or invoke `/shipwright-plan` on a spec you wrote manually. The orchestrator is convenient, not mandatory.
## 4. The Pipeline: Phase by Phase

Shipwright's pipeline consists of 10 phases, each handling a distinct step in the software delivery lifecycle. The phases run in sequence when you invoke the full pipeline via `/shipwright-run`, but every phase can also run as a standalone command. This chapter covers the first five phases: Orchestration, Project Decomposition, UI Design, Planning, and Implementation.

---

### 4.1 Orchestration -- /shipwright-run

**Purpose.** The orchestrator is your single entry point. It takes a project description (or an existing project) and drives it through the entire pipeline -- from requirements through deployment -- managing state, transitions, and context pressure along the way.

**Command and Arguments**

```
/shipwright-run "Build a SaaS time tracker with Supabase"
/shipwright-run                          (interactive -- asks what to build)
/shipwright-run @requirements.md         (from a file)
```

| Flag / Argument | Description |
|-----------------|-------------|
| `"description"` | Inline project description |
| `@file.md` | Path to a requirements file |
| *(no argument)* | Interactive mode -- Shipwright asks you what to build |

**What it needs.** Nothing beyond a project idea. For ongoing changes to existing projects, use `/shipwright-iterate` instead.

**What it produces**

- `shipwright_run_config.json` -- pipeline state (scope, profile, autonomy, current step, completed steps)
- Orchestration of all downstream phases and their artifacts
- Completion summary with deploy URL, test results, and PR link

**How it works**

- Detects your input (file, inline text, or interactive chat) and asks 1-3 clarifying questions if the description is vague
- Infers settings automatically: scope (new project vs. extension), technology profile (e.g., `supabase-nextjs`), and autonomy level (guided or autonomous)
- Presents inferred settings for your confirmation before starting
- Writes `shipwright_run_config.json` and dispatches to each phase in sequence: Project, Design, Plan, Build (looping per split), Test, Changelog, Deploy
- Between phases, validates artifacts, updates the delivery dashboard, and checks for context pressure
- In guided mode, asks you before each major transition; in autonomous mode, continues without prompting (except for production deploys)

**Standalone usage.** `/shipwright-run` is inherently standalone -- it is the top-level command. You typically only use individual phase commands when you want to re-run or debug a specific step.

**Resume support.** If the pipeline is interrupted (context limit, error, or manual stop), re-invoking `/shipwright-run` reads `shipwright_run_config.json` and resumes from the last incomplete step. No work is lost.

---

### 4.2 Project Decomposition -- /shipwright-project

**Purpose.** Transforms your project requirements into well-scoped planning units called "splits." Each split gets its own spec file that downstream phases consume. For new projects, this phase also scaffolds `CLAUDE.md` and the `agent_docs/` directory.

**Command and Arguments**

```
/shipwright-project @path/to/requirements.md   (from file)
/shipwright-project "Build a SaaS app..."       (inline description)
/shipwright-project                              (interactive chat)
```

| Input Mode | Description |
|------------|-------------|
| `@file.md` | Reads and summarizes the file, then interviews you to fill gaps |
| `"description"` | Uses the text as starting context for the interview |
| *(no argument)* | Full interactive interview from scratch |

**What it needs.** A project idea -- either as a file, an inline description, or nothing at all (the interview will discover everything). For extensions to existing projects, it reads the existing `CLAUDE.md` and `agent_docs/architecture.md` for context.

**What it produces**

- `planning/` directory with numbered split subdirectories (`01-auth/`, `02-dashboard/`, etc.)
- `spec.md` inside each split directory -- an IREB-style specification with functional requirements, non-functional requirements, and scope boundaries
- `planning/project-manifest.md` -- execution order, dependencies between splits, and overview
- `planning/requirements.md` -- consolidated requirements (generated for inline/chat modes)
- `planning/shipwright_project_interview.md` -- full interview transcript
- `CLAUDE.md` and `agent_docs/` (architecture, conventions, decision log, sprint, handoff) for new projects
- `.claude/rules/*.md` -- path-specific rules derived from the technology profile

**How it works**

- Detects scope: new project (no `CLAUDE.md`) triggers full decomposition; existing project triggers a lighter extension flow
- Conducts an adaptive interview (5-15 questions for new projects, 1-3 for extensions) to surface your mental model
- Analyzes the interview to determine whether the project needs multiple splits or is a single unit
- Writes `project-manifest.md` with the proposed structure and presents it for your approval
- Creates split directories and generates `spec.md` for each split
- For new projects: detects the technology profile, scaffolds `CLAUDE.md`, `agent_docs/`, and path-specific Claude rules
- Logs all project-level decisions (auth strategy, third-party services, naming conventions) to `agent_docs/decision_log.md`

**Standalone usage.** Yes. Run `/shipwright-project` independently whenever you want to decompose requirements without running the full pipeline. The output feeds directly into `/shipwright-plan`.

---

### 4.3 UI Design -- /shipwright-design

**Purpose.** Generates interactive HTML mockups from your specs before a single line of production code is written. This lets you validate the look, feel, and user flows early -- when changes are cheap.

**Command and Arguments**

```
/shipwright-design                                       (analyze all specs, generate all screens)
/shipwright-design @designs/screens/02-dashboard.html    (iterate on one screen)
/shipwright-design @designs/design-feedback-round2.md    (process exported feedback)
/shipwright-design --upload                              (integrate uploaded designs)
```

| Flag / Argument | Description |
|-----------------|-------------|
| *(no argument)* | Full generation from specs |
| `@screen.html` | Iterate on a single existing screen |
| `@feedback.md` | Process a feedback file exported from the review viewer |
| `--upload` | Integrate existing designs from `designs/uploads/` |

**What it needs.** Completed specs from `/shipwright-project`: `shipwright_project_config.json`, `planning/project-manifest.md`, and `planning/*/spec.md`. Optionally, existing designs or brand guidelines in `designs/uploads/`.

**What it produces**

- `designs/screens/*.html` -- standalone HTML mockups for each screen (self-contained, responsive, realistic data)
- `designs/flows/*.html` -- multi-screen user flow mockups (e.g., auth flow, CRUD flow)
- `designs/index.html` -- a review viewer with grid view, fullscreen mode, keyboard navigation, and an integrated feedback panel
- `designs/design-manifest.md` -- screen registry mapping each screen to its functional requirements
- `designs/visual-guidelines.md` -- design tokens (colors, fonts, spacing, radii) for the build phase to consume

**How it works**

- Reads all specs and maps functional requirements to screen types (auth, dashboard, list, form, settings, detail, etc.)
- If you have an existing website, extracts brand tokens (fonts, colors, card style) automatically
- Conducts a short design interview (3-5 questions): design system flavor (Untitled UI or Material Design 3), brand character (warm, clean, or bold), layout preference, and special UX needs
- Generates 3 preview screens first for you to validate the palette and style before committing to all screens
- Assembles screens from a snippet library (layouts, components, CSS variables) for consistency and speed
- Generates multi-screen user flows and a review viewer (`designs/index.html`) with built-in feedback collection
- Enters a review loop: you review in the browser, export feedback, and Shipwright applies changes iteratively until you finalize

**Standalone usage.** Yes. `/shipwright-design` works independently as long as specs exist. You can also iterate on individual screens or process feedback files at any time. The review viewer at `designs/index.html` is your primary tool for reviewing and providing feedback.

---

### 4.4 Planning -- /shipwright-plan

**Purpose.** Creates a detailed, section-based implementation plan from a single spec file. The plan follows a TDD approach (tests defined before code) and can optionally be reviewed by external LLMs (Gemini and OpenAI) for blind-spot detection.

**Command and Arguments**

```
/shipwright-plan @path/to/01-auth/spec.md
```

| Argument | Description |
|----------|-------------|
| `@spec.md` | Path to a spec file from `/shipwright-project` (required) |

**What it needs.** A `spec.md` file generated by `/shipwright-project`. Optionally: `GEMINI_API_KEY` and `OPENAI_API_KEY` for external LLM review.

**What it produces**

- `plan.md` -- the implementation plan with a `SECTION_MANIFEST` block that lists all sections in dependency order
- `sections/01-name.md`, `sections/02-name.md`, etc. -- self-contained section files, each describing one unit of work for `/shipwright-build`
- `shipwright_plan_interview.md` -- interview transcript with architecture and design decisions
- `claude-plan-e2e.md` -- Playwright E2E test plan (optional, if enabled in config)

**How it works**

- Reads the spec file and researches the codebase (existing patterns, structure, dependencies) or best practices for new projects
- Conducts an adaptive interview about architecture, data model, and UX preferences -- clarifying ambiguities from the spec
- Checks context pressure and summarizes research if the context window is growing large
- Writes `plan.md` with a TDD-oriented approach: for each section, it defines goals, implementation steps, and the test strategy
- Optionally sends the plan to Gemini and OpenAI in parallel for external review; presents findings for you to accept or reject
- Splits the plan into individual section files under `sections/`, each containing everything `/shipwright-build` needs to implement that unit
- Validates that every functional requirement from the spec is covered by at least one section, and that section dependencies are correctly ordered
- Logs all planning decisions to `agent_docs/decision_log.md`

**Standalone usage.** Yes. Run `/shipwright-plan @path/to/spec.md` for any spec file. This is useful when you want to re-plan a single split without re-running the entire pipeline. The output section files feed directly into `/shipwright-build`.

---

### 4.5 Implementation -- /shipwright-build

**Purpose.** Implements code from a single plan section using test-driven development. Each section goes through a full cycle: write failing tests, implement until they pass, review the code, commit with Conventional Commits, and update the project documentation.

**Command and Arguments**

```
/shipwright-build @sections/01-auth.md
```

| Argument | Description |
|----------|-------------|
| `@section.md` | Path to a section file from `/shipwright-plan` (required) |

**What it needs.** A section file generated by `/shipwright-plan`. The project must be a git repository. Environment variables required by the technology profile should be configured in `.env.local` (the phase validates this and prompts you if anything is missing).

**What it produces**

- Production code and test files as specified in the section plan
- A git commit on a feature branch (`{project-slug}/NN-name`) using Conventional Commits format
- A `work_completed` event in `shipwright_events.jsonl` (commit hash, test results, affected FRs, review data)
- Updated `agent_docs/decision_log.md` with implementation decisions
- Updated `agent_docs/build_dashboard.md` with progress tracking
- `agent_docs/session_handoff.md` (generated on context pressure or phase completion)
- Updated `agent_docs/conventions.md` with implementation learnings (when new patterns or gotchas discovered)
- SQL migration files with both `up.sql` and `down.sql` (when applicable)

**How it works**

- Reads the section spec and identifies prerequisites, files to create or modify, and the test strategy
- Creates a feature branch (or checks out an existing one for resumed sessions)
- Validates environment variables against the technology profile and prompts you to fill in any missing values
- Installs dependencies listed in the section spec
- Writes tests first (TDD red phase) -- tests should fail for the right reasons
- Implements code until all tests pass (green phase), running tests after each significant change
- For UI projects, performs a design fidelity check:
  - **Code-level fidelity** -- runs `design_fidelity_check.py` to extract structural summaries from mockup HTML and implementation TSX, then compares layout structure, component hierarchy, component types, card patterns, and shadcn/ui rules
  - Auto-checks provide quick pass/fail signals; screens that fail auto-checks get deeper agent analysis where the agent reads both source files side-by-side
- Design fidelity results are tracked in `design-fidelity-report.json` -- this artifact feeds into the test phase for regression detection
- Optionally refactors for cleanliness without changing behavior
- Runs a two-tier code review: a quick self-review checklist (always), plus a full subagent-based review for large diffs, high-risk sections, or security-sensitive files
- Applies accepted review fixes, re-runs tests to confirm no regressions
- Commits with Conventional Commits format (e.g., `feat(auth): implement magic link authentication`)
- Logs decisions, updates the build dashboard, and checks context pressure -- if the context window is getting full, it saves progress and stops cleanly so you can resume in a fresh session

**Standalone usage.** Yes. Run `/shipwright-build @sections/01-auth.md` for any section file. When used standalone, you manage the section order yourself. When used within the pipeline, the orchestrator feeds sections in dependency order and handles split transitions automatically.
### 4.6 Testing -- /shipwright-test

**Purpose:** Runs your project's full test suite across multiple layers -- unit tests, integration tests (real DB), pgTAP database tests, smoke tests, end-to-end (E2E) browser tests, cross-page UI consistency checks, and design fidelity verification -- to catch bugs before deployment. It is profile-aware, meaning it automatically picks the right test runners and URLs based on your stack.

**Command & Arguments:**

```
/shipwright-test
/shipwright-test --fix          # auto-fix failures (max 3 retries per test)
/shipwright-test --e2e-only     # only run Playwright E2E tests
```

**What it needs:**

- `shipwright_project_config.json` in the project root (for profile detection)
- A unit test setup matching your profile (e.g., Vitest for Next.js, pytest for Python)
- For smoke tests: a running dev server or a configured `SHIPWRIGHT_DEV_URL`
- For E2E: Playwright installed and a `playwright.config.ts` in the project

**What it produces:**

- Unit test results (pass/fail counts, duration)
- Integration test results (real DB CRUD + RLS verification, pass/fail counts)
- pgTAP test results (schema-level RLS/constraint verification)
- Smoke test result (HTTP status against your dev URL)
- E2E test results (pass/fail/skip counts)
- Auto-generated E2E specs in `e2e/flows/` and `e2e/pages/` if test plans exist but specs do not
- `playwright-report/index.html` -- interactive HTML report with screenshots, linked from compliance reports
- Design fidelity verification results (code-level comparison of implementation vs mockup HTML)
- Design fidelity triage results in `shipwright_test_results.json` (regressions, persistent failures, resolved screens)
- Updated `agent_docs/conventions.md` with test learnings (when flaky patterns or infra quirks discovered)
- A summary report printed to the terminal

**How it works:**

1. Detects your stack profile and determines which test runners and URLs to use.
2. Runs unit tests (e.g., `npx vitest run`). In autonomous mode, failures trigger auto-fix automatically; in guided mode, you need the `--fix` flag.
3. Runs integration tests against a real (localhost) Supabase instance (`npx vitest run --config vitest.integration.config.ts`). These verify CRUD operations, RLS policies, and complex queries with no mocks. Uses cascade-delete cleanup via test users. Fast-fails on infrastructure errors (ECONNREFUSED). Skipped if profile has no `testing.integration` config or `tests/integration/` directory does not exist.
4. Runs pgTAP database tests (`supabase test db`) if `supabase/tests/database/` exists. These verify RLS policies and constraints at the schema level.
5. Runs a smoke test against your dev URL (checking for HTTP 200 on `/api/health`). If the server is not running, it attempts to diagnose and fix the issue before skipping.
4. If E2E test plans exist from `/shipwright-plan` but no `.spec.ts` files have been written yet, it generates Playwright specs from the plans using the Page Object Model pattern.
5. Runs Playwright E2E tests (starts and stops the dev server automatically). Failed tests can be debugged with a browser-fixer subagent that reads screenshots and error messages.
6. Runs design fidelity verification as a **regressions-only safety net**. Reads `design-fidelity-report.json` (what the build phase already verified) and triages each screen: regressions (was passing in build, now failing), persistent failures (build gave up), and unchecked screens (never verified). Only fixes regressions and persistent failures -- resolved screens are skipped. Uses code-level structural comparison (no screenshots) with agent deep analysis for flagged screens.
7. Runs an E2E results verification step: compares `shipwright_test_results.json` against Playwright's authoritative `e2e-results.json` to catch count discrepancies (e.g., setup project tests being counted as E2E tests). If numbers diverge, the pipeline corrects `shipwright_test_results.json` and documents the reason.
8. Produces a structured results summary with explicit status for every layer.

**The seven test layers and enforcement rules** are central to how the pipeline decides whether to continue:

| Layer | On Failure | Rationale |
|-------|-----------|-----------|
| Unit tests | Pipeline stops (blocking) | Unit tests are deterministic -- failure means a real bug |
| Integration tests | Autofix (3 retries, fast-fail for infra errors), then blocking | Deterministic against real DB -- failure means a real schema/RLS bug |
| pgTAP DB tests | Autofix (3 retries), then blocking | Schema-level RLS/constraint verification |
| Smoke test | Pipeline stops (blocking) | If the app is not running, deployment is pointless |
| E2E tests | Warning only (non-blocking) | E2E tests can be flaky; failures are logged but do not block |
| Cross-page consistency | Warning only (advisory) | Cross-page UI inconsistencies are logged but do not block deployment |
| Design fidelity | Warning only (advisory) | Fidelity mismatches are logged but do not block deployment |

Every layer must report an explicit result (`pass`, `fail`, or `skipped: {reason}`) before the phase is considered complete. If any layer has no result, the phase stays in `incomplete` status.

**Standalone usage:** Yes. You can run `/shipwright-test` at any time against any project with a recognized profile. It works independently of the orchestrator. The `--fix` flag and `--e2e-only` flag give you targeted control outside the pipeline.

---

### 4.7 Security Scanning -- /shipwright-security

**Purpose:** Scans your project for security vulnerabilities -- static analysis (SAST), dependency vulnerabilities (SCA), and leaked secrets. Supports two scanner backends: **OSS** (local CLI tools) and **Aikido** (cloud SaaS). In pipeline mode, findings are automatically routed to a subagent for remediation.

**Scanner Backends:**

| Backend | Tools | Runs where | Cost |
|---------|-------|-----------|------|
| **OSS** (default) | Semgrep + Trivy + Gitleaks | Local (CLI binaries) | Free |
| **Aikido** | Aikido Security API | Cloud (SaaS) | Commercial |

**Command & Arguments:**

```
/shipwright-security                          # full scan (pipeline or standalone)
/shipwright-security issues --repo owner/repo # list open issues (Aikido only)
/shipwright-security summary                  # severity dashboard (Aikido only)
/shipwright-security report --repo owner/repo # generate Markdown report (Aikido only)
```

**What it needs (OSS backend):**

- At least one of: `semgrep`, `trivy`, `gitleaks` installed and on PATH
- See `references/oss-scanners.md` for installation instructions
- No account or API key required

**What it needs (Aikido backend):**

- An Aikido Security account with API credentials (`AIKIDO_CLIENT_ID` and `AIKIDO_CLIENT_SECRET` in your environment)
- Your GitHub repository connected in Aikido's dashboard

**Backend selection:** Auto-detected. Aikido is preferred when credentials are set; otherwise OSS tools are used. Override with `SHIPWRIGHT_SCANNER_BACKEND=oss|aikido` or the profile's `testing.security.provider` field.

**What it produces:**

- A table of findings with severity, type, rule, file, and line number
- A classification summary (auto-fixable / agent-fixable / needs-review / informational)
- A Markdown security report written to the project root
- `shipwright_security_config.json` with scan results (consumed by `/shipwright-compliance`)

**How it works:**

1. Detects and selects the scanner backend (OSS or Aikido). If neither is configured, prints setup instructions and stops.
2. Runs the scan -- locally via CLI tools (OSS) or via API call (Aikido).
3. In pipeline mode, classifies each finding into four categories: auto-fixable (e.g., dependency updates with known patches), agent-fixable (e.g., hardcoded credentials), needs-review (architecture issues), and informational (low-severity best practices).
4. Auto-fixable issues are patched directly, then tests are re-run to verify the fix.
5. Agent-fixable issues are handed to a `security-fixer` subagent with full context (file, line, CWE, remediation hint). Each finding gets up to 3 fix attempts.
6. Needs-review findings are presented to you with options to fix, decline, or defer.
7. Generates a Markdown report summarizing all findings and their remediation status (fixed, declined, deferred, open).

**Standalone usage:** Yes -- the phase runs when any scanner backend is available. With OSS tools installed, it works without any cloud account. With Aikido, the standalone commands (`issues`, `summary`, `report`, `repos`) work against any connected repository.

---

### 4.8 Release Management -- /shipwright-changelog

**Purpose:** Analyzes your git history, generates a structured changelog from Conventional Commits, determines the appropriate version bump, creates a git tag, and optionally opens a pull request. It turns your commit discipline into a publish-ready release artifact.

**Command & Arguments:**

```
/shipwright-changelog
/shipwright-changelog --from v0.1.0   # analyze commits starting from a specific tag
```

**What it needs:**

- A git repository with commits following the Conventional Commits format (e.g., `feat:`, `fix:`, `refactor:`)
- The `gh` CLI installed (for PR creation)
- A remote repository configured (for pushing tags and PRs)

**What it produces:**

- An updated `CHANGELOG.md` in Keep-a-Changelog format
- A semver git tag (e.g., `v0.2.0`)
- A pull request on GitHub (if you are on a feature branch)
- Tags and main branch pushed to origin

**How it works:**

1. Runs a setup script that detects the last version tag and collects all commits since then. If there are no unreleased changes, it stops early.
2. Parses each commit message into type and scope using Conventional Commits conventions. Types map to changelog sections: `feat` becomes "Added", `fix` becomes "Fixed", `refactor` becomes "Changed", and so on.
3. Determines the version bump: any `BREAKING CHANGE` triggers a major bump, any `feat` triggers a minor bump, and everything else triggers a patch bump. If no previous tag exists, it suggests `v0.1.0`.
4. Generates the changelog entry and prepends it to `CHANGELOG.md` (creating the file if needed).
5. In guided mode, shows you the entry for review with options to accept, edit, or cancel. In autonomous mode, it proceeds without prompting.
6. Commits the changelog, creates an annotated git tag, and pushes both to origin.
7. If you are on a feature branch, it creates a GitHub PR with the changelog as the body. In autonomous mode, the PR is merged immediately; in guided mode, it stays open for your review.

**Standalone usage:** Yes. You can run `/shipwright-changelog` on any git repository with Conventional Commits, whether or not it was built with Shipwright. It is a self-contained release tool.

---

### 4.9 Deployment -- /shipwright-deploy

**Purpose:** Deploys your application to Jelastic Cloud (hosted by Infomaniak in Switzerland) with automatic smoke test verification and rollback support. It also handles Supabase database migrations when applicable.

**Command & Arguments:**

```
/shipwright-deploy                  # deploy to DEV (automatic, no confirmation)
/shipwright-deploy --prod           # deploy to PROD (requires confirmation)
/shipwright-deploy --rollback       # restore PROD from last backup clone
```

**What it needs:**

- `JELASTIC_TOKEN` environment variable (Jelastic API access)
- Optionally: `SUPABASE_ACCESS_TOKEN` (if your project uses Supabase migrations)
- A git repository with a configured remote
- Stack profile environment variables validated by the deploy phase

**What it produces:**

- A deployed application at `dev-{project}.jpc.infomaniak.com` (DEV) or `{project}.jpc.infomaniak.com` (PROD)
- Smoke test verification confirming the deployment is live
- For PROD: a backup clone of the environment before deployment (rollback point)
- Applied database migrations (if Supabase migration files exist)
- Updated `agent_docs/conventions.md` with deployment learnings (when infra gotchas or config quirks discovered)

**How it works:**

1. Validates credentials and required environment variables. Missing variables are flagged, and you are prompted to set them before continuing.
2. If Supabase migration files exist in `supabase/migrations/`, they are applied. For DEV, this happens automatically. For PROD, a dry-run is shown first and you must explicitly confirm before applying. Destructive changes always require confirmation regardless of target.
3. For PROD deployments, a full clone of the production environment is created as a safety net before any changes are made. You must confirm the deployment explicitly.
4. Deploys via the Jelastic VCS Update API, pulling the latest code from your git remote.
5. Runs a smoke test against the deployed URL (polling for up to 60 seconds).
6. If the smoke test passes, the phase is marked complete. If it fails, automatic rollback kicks in.

**DEV vs. PROD -- the key difference:** DEV deployments are fully automatic with no confirmation required and use git-based rollback on failure (reverting to the last known good tag). PROD deployments require explicit user confirmation, create a backup clone beforehand, and restore from that clone if anything goes wrong. You can also trigger a manual rollback at any time with `--rollback`, which lists available backup clones and lets you choose which one to restore.

**Standalone usage:** Yes. You can run `/shipwright-deploy` independently to deploy any project configured for Jelastic. It validates its own prerequisites and does not depend on prior pipeline phases, though it works best after testing has passed.

---

### 4.10 Compliance -- /shipwright-compliance

**Purpose:** Aggregates data from all previous pipeline phases into audit-ready compliance documentation. It produces five standardized reports that trace requirements through implementation, testing, and deployment -- useful for regulated industries, enterprise customers, or internal governance.

**Command & Arguments:**

```
/shipwright-compliance
```

No flags or arguments. It reads existing pipeline data and generates (or updates) all reports automatically.

**What it needs:**

- `shipwright_events.jsonl` -- The unified event log is the primary data source for all compliance reports. Each build section, iterate change, test run, and phase transition is a JSON event.
- A git repository (for change history and commit data)
- Dependency manifests (`package.json` or `pyproject.toml`) for SBOM generation
- Planning specs (`planning/*/spec.md`) for requirement extraction

**What it produces:**

- `compliance/dashboard.md` -- The starting point. Quality indicators, project velocity, and links to all compliance artifacts.
- `compliance/traceability-matrix.md` -- Maps every requirement to the work events (build sections and iterate changes) that verify it, with a "Last Verified" column showing when each requirement was last tested.
- `compliance/test-evidence.md` -- Collects test results across all layers (unit, integration, pgTAP, smoke, E2E, consistency, visual) with pass/fail counts and skip reasons. Provides evidence that the software was tested.
- `compliance/change-history.md` -- Documents all commits, decisions (from `agent_docs/decision_log.md`), and version tags. Shows who changed what and why.
- `compliance/sbom.md` -- Software Bill of Materials listing all dependencies with versions and license types. Flags copyleft licenses that may have legal implications.

**How it works:**

1. Runs a setup script that inventories all available data sources (config files, git history, dependency manifests, decision logs). If no pipeline data exists at all, it stops with a message to run the pipeline first.
2. Shows you which data sources were found and whether this is a first run ("new") or an update to existing reports.
3. Calls the full report generator, which reads all available data, produces all five reports, and writes them to the `compliance/` directory.
4. Writes `shipwright_compliance_config.json` with metadata about the generation run.
5. Prints a summary showing counts of splits, sections, tests, commits, decisions, and packages (including copyleft license warnings).

**Incremental mode:** When running inside the orchestrator (`/shipwright-run`), compliance reports are updated silently after each phase completes. Only the reports affected by that phase are regenerated. For example, completing the build phase updates the traceability matrix, test evidence, change history, and dashboard -- but not the SBOM. This means your compliance documentation is always current without you needing to run it manually.

**Standalone usage:** Yes. You can run `/shipwright-compliance` at any point during or after the pipeline. It works with whatever data is available -- if only project and plan data exist, it generates partial reports. As more phases complete, subsequent runs fill in the gaps. This makes it useful both as a final deliverable and as a progress tracker during development.
## 5. Stack Profiles

A **stack profile** is a JSON file that defines everything about your technology stack in one place: runtime versions, frontend and backend libraries, UI component library, testing frameworks, deployment target, folder structure, CI pipeline, and architecture rules. Profiles are stored in `~/shipwright/shared/profiles/`.

When you run `/shipwright-run`, Shipwright infers the correct profile from your project description (or asks you to confirm). Every downstream skill -- project decomposition, planning, build, test, deploy -- reads the profile to make consistent decisions without you repeating configuration.

### The supabase-nextjs Profile

The default profile ships a modern full-stack setup:

| Layer | Technology | Version |
|-------|-----------|---------|
| Runtime | Node.js, TypeScript | 22.x, ^5.9.3 |
| Frontend | Next.js (App Router), React, Tailwind CSS | ^16.2.0, ^19.2.4, ^4.2.0 |
| State | Zustand | ^5.0.12 |
| UI Components | shadcn/ui (react-hook-form + zod for forms) | ^4.0.0 |
| Backend | Supabase (JS client, CLI, Edge Functions) | ^2.99.3, ^2.82.0 |
| Auth | Supabase Auth (email + OAuth) | Built-in |
| Storage / Realtime | Supabase Storage, Supabase Realtime | Built-in |
| Design System | Untitled UI (for mockups) | -- |
| Unit Testing | Vitest | ^4.1.0 |
| E2E Testing | Playwright | ^1.58.2 |
| Security Scanning | OSS (Semgrep, Trivy, Gitleaks) or Aikido | Local CLI or Cloud API |
| Linting | ESLint (flat config), Prettier | ^10.0.3, ^3.8.1 |
| Error Tracking | Sentry | ^10.45.0 (free tier) |
| CI | GitHub Actions | On push + PR |
| Deploy | Jelastic (Infomaniak), standalone output | -- |

### Project Folder Structure

```
src/app/                    Next.js App Router pages
src/components/             React components
src/lib/                    Utility functions
src/hooks/                  Custom React hooks
supabase/migrations/        SQL forward migrations
supabase/migrations/_rollback/  SQL rollback migrations (down.sql)
supabase/functions/         Edge Functions
tests/                      Vitest unit tests
e2e/                        Playwright E2E tests
public/                     Static assets
```

### Key Architecture Rules

The profile enforces these conventions across all pipeline phases:

- Feature modules must not import from other feature modules.
- All Supabase calls go through `lib/supabase/` -- no direct client usage in components.
- All API calls go through `lib/api/` -- no `fetch()` in components.
- Server Components by default -- `'use client'` only when needed.
- No business logic in API routes -- use Edge Functions.
- All database changes via migrations in `supabase/migrations/`.

### Required Environment Variables

| Variable | Purpose | Required For |
|----------|---------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Build |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key | Build |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (admin ops) | Build |
| `JELASTIC_TOKEN` | Infomaniak Jelastic API token | Deploy |
| `SUPABASE_ACCESS_TOKEN` | Supabase CLI token for migrations | Deploy (optional) |
| `OPENROUTER_API_KEY` | OpenRouter key for external plan review | Plugin (optional) |
| `GEMINI_API_KEY` | Google Gemini key (alternative to OpenRouter) | Plugin (optional) |
| `OPENAI_API_KEY` | OpenAI key (alternative to OpenRouter) | Plugin (optional) |
| `AIKIDO_CLIENT_ID` | Aikido Security API client ID | Plugin (optional) |
| `AIKIDO_CLIENT_SECRET` | Aikido Security API client secret | Plugin (optional) |

---

## 6. Configuration

Shipwright works out of the box for the core cycle (project, plan, build). Configuration is only needed for optional features: deployment, external plan review, and security scanning.

### Environment Variables (.env.local)

All environment variables go in your **project's** `.env.local` file. This file is never committed to version control. Variables already set in your OS environment take precedence.

To generate a template with all required and optional variables:

```bash
uv run shared/scripts/validate_env.py --project-root /path/to/your-project --phase all --init
```

This creates `.env.local` with placeholders for build, deploy, and plugin variables. Fill in only the values you need.

### Deployment Setup (Jelastic)

Required for `/shipwright-deploy`. Obtain your token from the Infomaniak Jelastic Dashboard under Settings > Access Tokens, then add to `.env.local`:

```
JELASTIC_TOKEN=your-jelastic-api-token
```

The profile configures two deployment environments: **DEV** (auto-deploy on push to `develop` or `feature/*` branches) and **PROD** (manual deploy from `main`, requires confirmation and pre-deploy snapshot).

### External Plan Review

Shipwright can send your implementation plan to external LLMs for an independent second opinion. Three options:

**Option A -- OpenRouter (recommended):** One key covers both review models (Gemini and OpenAI routed through OpenRouter).

```
OPENROUTER_API_KEY=sk-or-your-key
```

**Option B -- Direct API Keys:** Use Google and OpenAI APIs directly.

```
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=sk-your-key
```

**Option C -- No external review:** Simply leave the keys unset. The pipeline continues without the second-opinion check.

### Security Scanning

The security phase supports two backends. Choose one (or both):

**Option A -- OSS Backend (local, free):** Install one or more CLI tools on your machine:

- **Semgrep** (SAST): `pip install semgrep` or `brew install semgrep`
- **Trivy** (SCA): `brew install trivy` or download from [GitHub releases](https://github.com/aquasecurity/trivy/releases)
- **Gitleaks** (Secrets): `brew install gitleaks` or download from [GitHub releases](https://github.com/gitleaks/gitleaks/releases)

Each tool is optional -- install at least one to enable the OSS backend. Semgrep and Trivy auto-update their rules/vulnerability databases on every scan.

**Option B -- Aikido Backend (cloud SaaS):** Add your API credentials:

```
AIKIDO_CLIENT_ID=your-client-id
AIKIDO_CLIENT_SECRET=your-client-secret
```

**Backend selection** is automatic: Aikido is used when credentials are set, otherwise OSS tools are detected. Override with `SHIPWRIGHT_SCANNER_BACKEND=oss|aikido` in your environment.

The security phase (`/shipwright-security`) is conditional -- it only runs when at least one backend is available.

### Validating Your Setup

Run the verification script to check that prerequisites and configuration are correct:

```bash
~/shipwright/scripts/verify-setup.sh
```

For per-phase validation (checking only the variables needed for a specific phase):

```bash
uv run shared/scripts/validate_env.py --project-root . --phase build
uv run shared/scripts/validate_env.py --project-root . --phase deploy
uv run shared/scripts/validate_env.py --project-root . --phase all
```

---

## 7. Working with Shipwright

### 7.1 Multi-Split Projects

Large projects are automatically decomposed into **splits** -- independent, shippable chunks of functionality. The `/shipwright-project` phase interviews you about requirements, then groups related features into splits. Each split gets its own spec, plan, and build cycle.

The pipeline loops through splits sequentially: plan split 1, build all its sections, then plan split 2, build its sections, and so on. Testing, changelog, deployment, and compliance only run after all splits are complete.

For example, a SaaS app might decompose into:
- **Split 1:** Authentication and user management
- **Split 2:** Core domain features (dashboard, CRUD)
- **Split 3:** Billing and subscription management

Each split is further divided into **sections** -- the smallest unit of implementation. A section maps to a single Conventional Commit.

### 7.2 Iteration Mode

Once your project exists, use `/shipwright-iterate` for fast changes:

```
/shipwright-iterate "Add dark mode toggle"
```

`/shipwright-iterate` reads your existing `CLAUDE.md` and project structure, auto-detects intent (feature, change, or bug), assesses complexity and risk, then runs an adaptive pipeline -- from a quick fix for trivial changes to a structured mini-SDLC with planning, external review, and full testing for medium-complexity work. Large changes get an escape hatch to the full pipeline. This is the intended daily workflow after the initial build. See [Chapter 8](#8-ongoing-development-with-shipwright-iterate) for details.

### 7.3 Using Skills Individually

Every skill works standalone -- you do not always need the full pipeline:

| Command | Use Case |
|---------|----------|
| `/shipwright-project "Build a dashboard"` | Just decompose requirements into specs |
| `/shipwright-plan @spec.md` | Just plan one split from a spec file |
| `/shipwright-build @sections/01-models.md` | Just implement one section |
| `/shipwright-test` | Just run the test suite |
| `/shipwright-preview` | Start local dev server and open in browser |
| `/shipwright-test --design-fidelity` | Run design fidelity check only (code-level mockup vs implementation) |
| `/shipwright-deploy` | Just deploy to Jelastic |
| `/shipwright-changelog` | Just generate changelog and create a PR |
| `/shipwright-compliance` | Just generate compliance reports |

When using skills individually, provide the input artifact (spec file, section file) as an argument. The skill reads what it needs from the project's config files.

**Local Preview.** `/shipwright-preview` starts the development server and shows the URL (e.g., `http://localhost:3000`). Available after at least one build split is complete. The preview uses the `dev_server` configuration from the stack profile -- new stack profiles must define `dev_server.command`, `dev_server.port`, and `dev_server.ready_path` in their profile JSON.

### 7.4 Session Recovery and Handoff

Claude Code has a finite context window. During long builds, Shipwright monitors context pressure and, when the window is filling up, automatically generates a **session handoff** document (`agent_docs/session_handoff.md`) containing the current phase, split, section, completed work, and next steps.

To resume after a pause or context limit:

1. Start a new Claude Code session (or type `/clear`).
2. Shipwright reads `shipwright_run_config.json` and `agent_docs/session_handoff.md`.
3. The pipeline resumes from where it left off.

All state is file-based -- nothing lives only in memory. You can interrupt at any point, close your editor, and come back later.

### 7.5 The Constitution

The **constitution** (`shared/constitution.md`) defines behavioral boundaries for all Shipwright agents and subagents. It is organized into three tiers:

**ALWAYS (do without asking):**
- Run tests before committing -- tests must pass.
- Generate `down.sql` rollback for every migration.
- Use Conventional Commits (`feat:`, `fix:`, `refactor:`, etc.).
- Use parameterized queries -- never interpolate user input into SQL.
- Validate input at system boundaries.
- Run the self-review checklist before committing.
- Log deviating decisions in `agent_docs/decision_log.md`.
- Keep files under 300 lines -- split if larger.
- Fix the code, not the test -- never weaken assertions to pass.

**ASK FIRST (require user confirmation):**
- Destructive database operations (`DROP TABLE`, `DROP COLUMN`, `TRUNCATE`).
- Production deployments (always confirm + backup).
- Skipping test layers (must provide a valid reason).
- Overriding phase validation gates (`--force`).
- Continuing after 3 failed fix attempts.

**NEVER (hard stops):**
- `rm -rf` on root or home directories.
- `git push --force` to main/master.
- `git reset --hard`.
- `--no-verify` to bypass pre-commit hooks.
- `DROP DATABASE`.
- Skip or weaken tests to make them pass.
- Add features beyond spec (YAGNI).
- Hardcode secrets in source code.
- Commit `.env` files.

The most critical rules are also enforced programmatically by hooks (see Chapter 9).

---

## 8. Ongoing Development with /shipwright-iterate

After the initial pipeline completes, ongoing changes use `/shipwright-iterate` -- a complexity-adaptive process that scales from quick fix to structured mini-SDLC, keeping all artifacts in sync.

### Trigger

- **Automatic:** A `UserPromptSubmit` hook detects change intent from user messages and suggests `/shipwright-iterate`
- **Manual:** User calls `/shipwright-iterate` directly with `--type feature|change|bug`

### Complexity-Adaptive Phases

Unlike v0.2's fixed process, `/shipwright-iterate` v0.3 assesses each change's complexity and runs only the phases that change needs. This happens in two stages:

1. **Quick Estimate** -- A classifier script analyzes your prompt for scope keywords and risk signals, producing an initial estimate with confidence score.
2. **Repo Scout** -- The agent scans the repository (affected files, FRs, split boundaries) to confirm or upgrade the estimate. After this, complexity is locked.

The result is one of four levels:

| Complexity | Criteria | What Runs |
|------------|----------|-----------|
| **Trivial** | 1 FR, 1-2 files, no risk flags | spec update → build → self-review → unit test (`--related`) → finalize |
| **Small** | 1-2 FRs, 3-5 files, or risk flags present | + confirmation question, design text (if UI), mini-plan (features), conditional full review |
| **Medium** | 2-4 FRs, 5-10 files, or cross-split | + scoping interview (2-3 Qs), iterate spec file, mini-plan with work breakdown, user approval gate, external LLM review, full code review, full test suite, E2E update |
| **Large** | 4+ FRs, 10+ files, cross-split + risk flags | **Escape hatch** -- recommends switching to the full pipeline |

Users can override complexity (`--complexity medium`) and adjust phases before execution ("skip design", "make it small"). However, safety floors enforced by risk flags cannot be bypassed without explicit acknowledgment.

### Risk Taxonomy

Eight canonical risk flags trigger safety minimums regardless of complexity level:

| Risk Flag | Example Trigger Paths | Enforces |
|-----------|----------------------|----------|
| `touches_auth` | `src/middleware.ts`, `**/auth/**` | mandatory code review |
| `touches_rls` | `supabase/migrations/*rls*` | mandatory code review |
| `touches_middleware` | `src/middleware.ts`, `next.config.*` | mandatory code review |
| `touches_migrations` | `supabase/migrations/` | mandatory review + down.sql |
| `touches_billing` | `**/stripe/**`, `**/payment*/**` | mandatory code review |
| `touches_shared_infra` | `src/lib/`, `src/components/ui/` | full test suite |
| `cross_split` | changes span 2+ planning splits | full review + full test suite |
| `touches_public_api` | API route handlers, exported types | mandatory code review |

### Context Loading

Before assessing intent or complexity, iterate reads all project context upfront: `CLAUDE.md`, coding conventions, the complete decision log (ADRs), architecture overview, all spec files across all planning splits, file-to-FR mappings, last test results, and the 20 most recent git commits. This ensures the agent knows what was already built, what decisions were made, and what was recently changed -- preventing regressions and duplicate work.

### Planned Run Summary

Before execution begins, iterate prints a summary of what will run:

```
SHIPWRIGHT-ITERATE: Session Plan
  Run ID:      iterate-20260405-course-search
  Intent:      FEATURE
  Complexity:  Small (1 FR, ~4 files, risk: touches_migrations)
  Phases:      spec → design text → build (TDD) → self-review → scoped test → finalize
  Skipping:    iterate spec (small), mini-plan (small), full review (no risk flags)
  Safety floor: DB migration → mandatory down.sql
```

You can adjust before proceeding -- "make it medium", "skip design", "add review".

### Interview & Approval

Iterate replaces manual Plan Mode by building scoping questions directly into the workflow:

- **Small changes:** One confirmation question -- "Do I understand correctly: [restated intent]. Shall I proceed with this?" If you correct, iterate adjusts scope and may re-assess complexity.
- **Medium changes:** 2-3 scoping questions for features (what, out-of-scope, UI behavior) or 1-2 for changes (what changes, boundaries). Answers feed directly into the iterate spec and mini-plan. After the mini-plan is written, iterate presents a summary and waits for your approval before building.
- **Trivial and bugs:** No interview. Trivial changes proceed directly; bugs go through a structured debugging protocol (reproduce → localize → root cause → failing test).

This means you never need to manually trigger `/plan` -- iterate handles the right amount of upfront scoping automatically based on complexity.

### 3 Intent Paths

The three intent types still define the workflow shape, but each is now complexity-gated:

| Intent | Flow (brackets = complexity-dependent) | Key Difference |
|--------|---------------------------------------|----------------|
| **Feature** | [interview] → [spec] → [plan] → [approval] → [review] → [design] → build → test → finalize | Appends new FR to spec |
| **Change** | [interview] → [spec] → [plan] → [approval] → [review] → [design] → build → test → finalize | Updates existing FR in spec |
| **Bug** | [spec] → reproduce → [plan] → fix → test → finalize | Reproduces via failing test first, no interview |

Each path runs tests automatically, creates a conventional commit with FR references and a `Run-ID` trailer, records a `work_completed` event in the event log, and triggers incremental compliance report updates.

### Override Classes

Not all phases can be skipped. Iterate defines three categories:

| Category | Includes | User Can Skip? |
|----------|----------|----------------|
| **Mandatory** | Self-review, unit test, commit, ADR, compliance, test results JSON | Never |
| **Safety-enforced** | Full review (when risk flags), full test suite (when shared infra), down.sql (when migrations) | Only with explicit risk acknowledgment |
| **Advisory** | Design check, mini-plan, design fidelity, E2E update, external LLM review | Freely skippable |

### Escape Hatch and Escalation

**Large scope:** When the Repo Scout determines complexity is large, iterate prints a recommendation with two options: (1) hand off to `/shipwright-project --extend` via a structured handoff file, or (2) continue with iterate under mandatory full review and full test suite.

**Mid-flight escalation:** If scope grows during implementation (more files than estimated, cascading test failures), iterate can upgrade complexity dynamically. For example, small → medium triggers retroactive creation of an iterate spec and mini-plan, plus external LLM review before further code changes.

### Finalization

Every iterate run -- regardless of complexity -- ends with 12 mandatory finalization steps:

1. **Drift check** -- verify specs match implementation
2. **Architecture update** -- update `architecture.md` if structural changes were made
3. **ADR** -- record the decision in `decision_log.md`
4. **Reflection** -- capture learnings (patterns, gotchas, corrections) in `conventions.md` and/or Claude Code Memory
5. **CHANGELOG** -- add entry to `[Unreleased]` section
6. **Test results JSON** -- write structured test results to `shipwright_test_results.json`
7. **Conventional commit** -- with `Run-ID` trailer and FR references
8. **Record event** -- append `work_completed` to `shipwright_events.jsonl`
9. **Update compliance** -- regenerate traceability and reports
10. **Update build dashboard** -- refresh `build_dashboard.md`
11. **Update iterate_history** -- append to `shipwright_run_config.json` (last 50 entries retained)
12. **Merge, push & verify** -- merge branch to main, push, verify event was recorded, regenerate session handoff

### Degraded Mode

When metadata is incomplete, iterate degrades gracefully rather than failing:

- **No sync config:** defaults to medium complexity, runs full test suite
- **No visual-guidelines.md:** skips design check, notes in ADR
- **External review unavailable:** skips, notes as "external-review-skipped"
- **Code reviewer unavailable:** self-review only, flagged as "review-limited"
- **Browser verify fails:** falls back to test-only verification

All degraded conditions are recorded in `shipwright_test_results.json` and noted in the final summary.

### Drift Check

Use `/shipwright-sync --check` to verify all artifacts are in sync. This is a read-only diagnostic -- it reports drift but doesn't auto-fix.

### vs. /shipwright-run

| | /shipwright-run | /shipwright-iterate |
|---|---|---|
| **When** | New project or major extension | Daily changes, bug fixes, features of any size |
| **Pipeline** | Full 8-phase SDLC | Complexity-adaptive (trivial → medium, or escape to full pipeline) |
| **Complexity** | Always full | Auto-assessed: trivial, small, medium, large |
| **Duration** | Hours | Minutes (trivial/small) to ~1 hour (medium) |
| **Risk detection** | Implicit in phase structure | Explicit: 8 canonical risk flags with safety floors |
| **Artifacts** | All created from scratch | Same event log, incrementally |

---

## 9. Quality and Safety

Shipwright enforces quality through **mechanical enforcement** -- hooks that block or warn deterministically, not advisory prose that agents may ignore. This follows the "linters over instructions" principle.

### The Hooks System

Hooks are Python and shell scripts that fire on specific Claude Code events. The build phase has the most hooks:

| Hook | Trigger | What It Prevents |
|------|---------|-----------------|
| `validate_command.sh` | Before any Bash command | Blocks `git push --force` to main, `rm -rf /`, `DROP DATABASE` |
| `check_secrets.sh` | After Write/Edit | Detects API keys (`sk-...`, `AKIA...`, `ghp_...`), PEM keys, passwords, connection strings |
| `check_destructive_migration.sh` | After Write/Edit on .sql | Warns on `DROP TABLE`, `DROP COLUMN`, `TRUNCATE` without a matching `down.sql` |
| `check_file_size.sh` | After Write/Edit | Warns when source files exceed 300 lines |
| `track_tool_calls.py` | After Write/Edit | Counts tool calls for context pressure detection |
| `check_drift.py` | Session start | Detects uncommitted changes from prior sessions |
| `check_documentation.py` | Session end | Verifies decision log and handoff documents are current |

Hooks use **exit code 2 (soft-block)**: you can say "Continue anyway," but the override is logged to `agent_docs/compliance_overrides.log` and flagged at the next checkpoint.

### TDD Workflow

Shipwright follows a strict test-first approach:

1. **Red** -- Write a failing test based on the spec's acceptance criteria.
2. **Green** -- Write the minimum code to make the test pass.
3. **Refactor** -- Clean up while keeping tests green.

Tests must pass before every commit. The constitution rule "fix the code, not the test" means assertions are never weakened to make failing tests pass.

### Code Review

Every section goes through a two-stage review:

1. **Self-review checklist** -- The building agent checks spec compliance, error handling, security, test quality, and naming before committing.
2. **Subagent code review** -- A dedicated code-reviewer subagent examines the diff against the spec and flags issues.

### Migration Safety

Database migrations receive special protection:

- Every `up.sql` migration automatically gets a corresponding `down.sql` in `supabase/migrations/_rollback/`.
- Destructive patterns (`DROP TABLE`, `DROP COLUMN`, `ALTER TYPE`) trigger a hook warning and require user confirmation.
- Production migrations always run `--dry-run` first, with explicit user approval before applying.

### Secret Scanning

The secret scanner runs on every file write or edit and detects:

- AWS Access Keys (`AKIA...`)
- API keys (`sk-...`, `ghp_...`, `gho_...`, `glpat-...`)
- Slack tokens (`xoxb-...`, `xoxp-...`)
- PEM private keys
- Hardcoded passwords and connection strings with embedded credentials

It automatically skips `.env.example`, test fixtures, lock files, and vendor directories.

---

## 10. Generated Documentation

Shipwright generates and maintains documentation throughout the pipeline. You do not write these files manually -- they are created and updated as a side effect of each phase.

### agent_docs/ Directory

The `agent_docs/` directory is the project's knowledge base for AI agents. Its contents:

| File | Purpose | Updated By |
|------|---------|-----------|
| `architecture.md` | System overview, stack table, data flow, security model | `/shipwright-project` |
| `conventions.md` | Code patterns, naming, git workflow, component examples | `/shipwright-project` |
| `decision_log.md` | Architecture Decision Records (ADR format) | All phases |
| `session_handoff.md` | Recovery document: last events, git state, resume instructions | Auto-generated on context pressure or session end |
| `build_dashboard.md` | Project activity: recent changes, test status, pipeline, build history | Updated after every phase and iterate |
| `compliance_overrides.log` | Audit log of hook overrides | Hooks (when user says "Continue anyway") |

### CLAUDE.md

The project master document, generated during `/shipwright-project`. It stays lean (approximately 200 lines) and follows a progressive disclosure pattern:

- **WHAT** -- Stack and purpose (2-3 lines).
- **HOW** -- Build, test, lint, deploy commands.
- **Structure** -- Folder layout.
- **Key Files** -- Important files with one-line descriptions.
- **Gotchas** -- Project-specific pitfalls.
- **Context** -- References to `@agent_docs/` files, loaded on demand.

### Decision Log (ADR Format)

Each decision record follows the ADR template: Status, Context, Decision, Consequences (including rejected alternatives). Profile-level decisions (stack, auth pattern, folder structure) are implicit in the stack profile. Only project-specific decisions go in the log.

### Event Log

`shipwright_events.jsonl` is an append-only JSONL file in the project root. Every build section, iterate change, test run, and phase transition is recorded as a JSON event. This is the single source of truth for all compliance reports and the activity dashboard. Events are never edited -- corrections use `event_amended` entries that reference the original event's ID.

### Project Activity Dashboard

`agent_docs/build_dashboard.md` shows the project's current state, derived from the event log. The most recent changes appear at the top (newest first), followed by test status, pipeline progress, and build history grouped by split. This is the first file an agent reads to understand what has happened and what to do next.

### Compliance Reports

The `/shipwright-compliance` skill generates audit-ready documentation from the event log:

| Report | Contents |
|--------|----------|
| **Compliance Dashboard** | Quality indicators from events, project velocity, links to all artifacts |
| **Requirements Traceability Matrix (RTM)** | Maps every requirement to work events that verify it, with "Last Verified" timestamps |
| **Test Evidence** | Test progression timeline showing how the test suite evolved over time |
| **Change History** | Conventional Commits mapped to requirements, with commit hashes and timestamps |
| **SBOM (Software Bill of Materials)** | Dependencies with versions, extracted from `package.json` / `package-lock.json` |

Compliance is updated incrementally after each pipeline phase, so reports reflect current state at any point during the build.

---

## 11. Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Plugin not found" when typing `/shipwright-run` | Shell alias not loaded, or plugin paths wrong | Run `type shipwright` to check alias. Verify `~/shipwright/plugins/shipwright-run/.claude-plugin/plugin.json` exists. |
| `uv: command not found` | uv not in PATH after installation | Restart terminal, or add: `export PATH="$HOME/.cargo/bin:$PATH"` |
| "Python version too old" | System Python is below 3.11 | Run `uv python install 3.11` -- uv manages Python versions for you. |
| Hooks fail with "permission denied" | Python/shell scripts not executable | Run `chmod +x ~/shipwright/plugins/*/scripts/**/*.py ~/shipwright/plugins/*/scripts/**/*.sh` |
| Context window exceeded during large project | Project too large for a single session | Type `/clear` in Claude Code. Shipwright saves state to config files and resumes from the handoff document. |
| External review skipped silently | No API keys set for OpenRouter, Gemini, or OpenAI | Run `validate_env.py --init --phase all`, then add `OPENROUTER_API_KEY` to `.env.local`. |
| Git operations fail (PR creation, changelog) | GitHub CLI not authenticated | Run `gh auth login` and follow the prompts. |
| Deploy fails with auth error | Jelastic token expired or invalid | Generate a new token in the Infomaniak Jelastic Dashboard under Settings > Access Tokens. |
| Security phase skipped | No scanner backend available | Install OSS tools (semgrep, trivy, gitleaks) or add Aikido credentials (`AIKIDO_CLIENT_ID`, `AIKIDO_CLIENT_SECRET`) to `.env.local`. |
| Build hangs after multiple fix attempts | Agent stuck in a debugging loop | The constitution limits retries to 3 attempts, then escalates. If it still loops, type "stop" and review the error manually. |
| Invalid JSON in `shipwright_events.jsonl` | Interrupted write or manual editing | Run `uv run shared/scripts/tools/validate_event_log.py --project-root .` -- the reader skips corrupt lines automatically, but the validator will identify them. |
| Commit exists but no event recorded | Agent crashed after commit but before event recording | Run `validate_event_log.py` -- it checks git history against events and reports unmatched commits. |
| Compliance reports empty after update | Event log missing or no events | Ensure `shipwright_events.jsonl` exists. For existing projects, run `uv run shared/scripts/tools/convert_configs_to_events.py --project-root .` to migrate from config files. |

---

## 12. Updating Shipwright

### Marketplace Installation (Recommended)

Run the update script from the Shipwright repo:

```bash
bash scripts/update-marketplace.sh
```

This fetches the latest code from GitHub (`claude plugin marketplace update`) and refreshes each plugin's local cache (`claude plugin update`). Restart your Claude Code session afterward.

**Manual alternative** (update individual plugins):

```bash
claude plugin marketplace update shipwright
claude plugin update shipwright-iterate@shipwright
claude plugin update shipwright-build@shipwright
# ... repeat for other installed plugins
```

### Shell Alias Installation

If you installed via shell alias instead of marketplace:

```bash
cd ~/shipwright && git pull && uv sync
```

`uv sync` re-installs Python dependencies if they changed. If nothing changed, it completes in under a second.

### What Takes Effect When

| Change Type | When It Takes Effect |
|-------------|---------------------|
| SKILL.md changes | After session restart |
| Python script changes | Immediately (scripts are loaded fresh each run via `uv run`) |
| Hook changes | Immediately (hooks are re-read each session) |
| Marketplace plugin updates | After `claude plugin update` + session restart |
| New plugins added | After updating your shell alias or marketplace config to include them |
| Profile changes | On next `/shipwright-run` (profile is read at pipeline start) |

### Checking What Changed

```bash
cd ~/shipwright && git log --oneline -10
```

Or read `CHANGELOG.md` in the repository root for release notes.

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Split** | A shippable chunk of functionality within a larger project. Shipwright decomposes projects into splits during the project phase. Each split gets its own spec, plan, and build cycle. |
| **Section** | The smallest unit of implementation within a split. Each section maps to a single Conventional Commit and produces a `work_completed` event in the event log. Sections are defined during the plan phase and built sequentially. |
| **Event Log** | An append-only JSONL file (`shipwright_events.jsonl`) recording every significant action in the project: section completions, iterate changes, test runs, and phase transitions. All compliance reports and the activity dashboard are derived from this log. |
| **Work Event** | A `work_completed` entry in the event log. Represents any unit of verified work -- whether a build section or an iterate change. Contains the commit hash, test results, affected requirements, and review data. |
| **Event Amendment** | A correction entry (`event_amended`) that references a previous event's ID and provides corrected field values. Preserves log immutability while allowing data fixes. |
| **Stack Profile** | A JSON file defining the complete technology stack: runtime versions, libraries, folder structure, deployment target, CI pipeline, and architecture rules. Stored in `shared/profiles/`. |
| **Hook** | A Python or shell script that fires on Claude Code events (session start, before/after tool use, session end). Hooks enforce safety rules programmatically -- blocking dangerous commands, scanning for secrets, detecting destructive migrations. |
| **Constitution** | The governing document (`shared/constitution.md`) defining ALWAYS, ASK FIRST, and NEVER rules for all Shipwright agents. Hooks enforce a subset; the constitution covers the complete set. |
| **Phase Validator** | A function that runs before marking a pipeline phase complete. Checks that required artifacts exist (specs, section files, test results). Returns issues with severity ASK (blocks until user confirms) or INFORM (logs and continues). |
| **RTM (Requirements Traceability Matrix)** | A compliance report mapping every requirement to work events that verify it, with "Last Verified" timestamps. Proves that all requirements were implemented and tested. |
| **SBOM (Software Bill of Materials)** | A compliance report listing all project dependencies with their versions, extracted from `package.json` and `package-lock.json`. Used for supply chain auditing. |
| **ADR (Architecture Decision Record)** | A structured log entry documenting an architecture decision: status, context, decision, and consequences (including rejected alternatives). Stored in `agent_docs/decision_log.md`. |
| **Conventional Commits** | A commit message format (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`) that enables automated changelog generation and semantic versioning. |
| **IREB** | International Requirements Engineering Board. Shipwright aligns its requirements specs with IREB practices: structured requirements with acceptance criteria that map directly to tests. |
| **Agent Docs** | The `agent_docs/` directory containing architecture, conventions, decision log, sprint status, and session handoff documents. These files provide context for AI agents working on the project. |
| **Feature Branch** | A Git branch (`feature/{name}`) created during the build phase. Each split is built on its own feature branch, merged to `main` via PR during the changelog phase. |
| **Context Pressure** | A measure of how full Claude Code's context window is. Shipwright monitors tool call counts and estimates remaining capacity. When pressure is high, it triggers a session handoff. |
| **Session Handoff** | An auto-generated document (`agent_docs/session_handoff.md`) containing current state, completed work, and next steps. Written before context compaction so a new session can resume seamlessly. |

---

## 11. Command Center (WebUI)

The Shipwright Command Center is a local web application for managing multiple Shipwright projects in parallel. It provides a visual Kanban board, task management, real-time progress tracking, and an inbox for Claude's questions.

### Quick Start

```bash
cd webui
npm install          # First time only
npm run dev          # Starts server (port 3847) + client (port 5173)
```

Open **http://localhost:5173** in your browser.

### Creating a Project

1. Click **Create Project** (top-right on Projects page, or in the sidebar)
2. Enter project name and directory path (use Browse to select)
3. Choose stack profile (Next.js + Supabase or Custom)
4. Review and confirm

### Creating a Task

1. Click **New Task** (top-right on Task Board) or press **Ctrl+N** / **Cmd+N**
2. Enter a task title and optional description
3. Select a project (if not already filtered)
4. Check/uncheck "Start immediately" — when checked, Claude CLI starts right away
5. Click **Create Task**

The task appears in the **Backlog** column. If "Start immediately" was checked, it moves to **In Progress** as Claude works on it. Backlog tasks show a **Start** button to launch them manually.

### Task Board

The Kanban board has four columns: **Backlog**, **In Progress**, **In Review**, and **Done**. Tasks move between columns automatically based on their pipeline phase. The phase-to-column mapping is configurable in Settings.

- **Project dropdown** (top-left) filters tasks by project or shows all
- **Phase / Priority filters** narrow visible tasks
- **Board / List** toggle switches between Kanban and table view
- Cards show: title, phase tag, priority, time-ago, and intent/complexity badges

### Inbox

When Claude needs your input during a task, the question appears in the **Inbox**. Answer by selecting an option or typing a response. The answer is delivered to Claude's running process via stdin.

### Settings

Four tabs:

| Tab | Purpose |
|-----|---------|
| **Global** | Max concurrent tasks, default autonomy (Guided/Autonomous), heartbeat interval |
| **Phase Mapping** | Configure which pipeline phases map to which Kanban columns |
| **Project** | View per-project settings (profile, status, path) |
| **About** | Version info, environment details |

### Architecture

- **Backend**: Hono (Node.js) on port 3847 — REST API + SSE for real-time updates
- **Frontend**: React 19 + Vite + TailwindCSS 4 + Radix UI
- **No database**: Event log (JSONL) + JSON files only
- **No auth**: Single-user local application

Data is stored in:
- `~/.shipwright-webui/` — project registry, process PIDs, global settings
- `{projectDir}/shipwright_events.jsonl` — task events
- `{projectDir}/.shipwright-webui/` — chat history, inbox items

---

## Appendix B: Command Reference

| Command | Arguments | Flags | Purpose |
|---------|-----------|-------|---------|
| `/shipwright-run` | `"description"` or `@requirements.md` | -- | Orchestrate the full pipeline. Infers stack profile, detects scope (Full App / Extension), dispatches to downstream skills in sequence. |
| `/shipwright-iterate` | `"description"` | `--type feature\|change\|bug`, `--complexity trivial\|small\|medium\|large`, `--review`, `--pause` | Complexity-adaptive SDLC for ongoing changes. Auto-detects intent and complexity, scales phases from quick fix to structured mini-pipeline with planning, review, and testing. |
| `/shipwright-project` | `"description"` or `@requirements.md` | -- | Decompose requirements into splits and IREB-aligned specs. Generates `CLAUDE.md`, `agent_docs/`, and project config. Interviews you about requirements. |
| `/shipwright-design` | -- | -- | Generate HTML mockups from specs. Produces screens with review viewer, feedback loop, and spec backflow. Runs after project, before plan. |
| `/shipwright-plan` | `@spec.md` | -- | Create implementation plan for one split. Researches stack, interviews for clarification, generates section files. Optionally sends plan to external LLMs (Gemini + OpenAI) for review. |
| `/shipwright-build` | `@section.md` | -- | Implement one section using TDD. Writes failing test, implements code, runs code review subagent, creates Conventional Commit on feature branch. |
| `/shipwright-test` | -- | `--fix` | Run test suite: unit tests (Vitest), integration tests (real DB), pgTAP (RLS), smoke test (HTTP), E2E (Playwright). The `--fix` flag enables auto-repair of failing tests. |
| `/shipwright-security` | -- | -- | Run security scan (OSS or Aikido backend). Classifies findings, runs remediation loop with security-fixer subagent, generates report. Runs when any scanner backend is available. |
| `/shipwright-changelog` | -- | -- | Parse Conventional Commits from git history, generate Keep-a-Changelog entries, suggest semver bump, create version tag, and open a pull request. |
| `/shipwright-deploy` | -- | `--env prod` | Deploy to Jelastic (Infomaniak). DEV deploys automatically; PROD requires `--env prod` flag and explicit confirmation. Runs smoke test after deploy, rolls back on failure. |
| `/shipwright-compliance` | -- | `--phase {name}` | Generate compliance reports: dashboard, RTM, test evidence, change history, and SBOM. The `--phase` flag updates reports incrementally for a specific phase. |
