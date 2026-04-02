# Shipwright SDLC

AI-powered software delivery lifecycle framework built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code). From user description to deployed, tested, secured application — in one command.

## What is Shipwright?

Shipwright wraps the [Deep Trilogy](https://github.com/piercelamb/deep-project) (deep-project, deep-plan, deep-implement) into a full SDLC pipeline. Instead of running 3 separate skills manually, you invoke one command and the agent handles everything:

```
/shipwright-run "A SaaS time tracking app with Supabase and Next.js"
```

Shipwright infers your stack, deploys to DEV automatically, runs tests, creates changelogs, and opens PRs — while you focus on what matters.

## Pipeline

```
User Description
  │
  ▼
┌────────────────────────────┐
│ shipwright-run             │  Infer scope, profile, autonomy → dispatch
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-project         │  Interview → Split → IREB Specs → CLAUDE.md + agent_docs
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-design          │  Specs → Interview → HTML Mockups → Review Viewer → Feedback Loop
└─────────────┬──────────────┘
              ▼  (per split)
┌────────────────────────────┐
│ shipwright-plan            │  Research → Interview → Plan → External LLM Review → Sections
└─────────────┬──────────────┘
              ▼  (per section)
┌────────────────────────────┐
│ shipwright-build           │  TDD → Code Review → Conventional Commit → Feature Branch
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-test            │  Unit (Vitest) → Smoke → Playwright E2E
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-security        │  Aikido API → Classify → Remediation Loop → Report
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-deploy          │  Jelastic (Infomaniak) → Smoke Test → Rollback on Failure
└─────────────┬──────────────┘
              ▼
┌────────────────────────────┐
│ shipwright-changelog       │  Parse Commits → Changelog → Version Tag → PR
└────────────────────────────┘
```

## Skills

| Skill | Purpose | Key Features |
|-------|---------|-------------|
| `shipwright-run` | Orchestrator | Inference engine, scope detection, pipeline state machine |
| `shipwright-project` | Requirements | IREB-aligned specs, scope detection (Full App / Extension), chat + file + inline input |
| `shipwright-design` | UI Design | [Snippet-assembled HTML mockups](#design-phase), [review viewer](#design-review-workflow) with feedback panel, [design system flavors](#design-system-flavors), spec backflow, session handoff |
| `shipwright-plan` | Planning | External LLM review (Gemini + OpenAI), section-writer subagent, E2E test plan |
| `shipwright-build` | Implementation | TDD loop, code-reviewer subagent, Conventional Commits, migration safety |
| `shipwright-test` | Testing | Profile-aware (Vitest/Playwright), smoke test, `--fix` auto-repair |
| `shipwright-security` | Security | Aikido API scanning, finding classification, remediation loop, security-fixer subagent |
| `shipwright-deploy` | Deployment | [Deployment flavors](#deployment-flavors), DEV auto / PROD manual, clone-based rollback |
| `shipwright-changelog` | Release | Keep-a-Changelog format, semver bump suggestion, PR creation |
| `shipwright-compliance` | Compliance | IREB traceability, RTM, SBOM, test evidence, change history reports |

## Modes

### Full Application
New project from scratch. Deep interview, multi-split decomposition, full pipeline.
```
/shipwright-run "Build a SaaS time tracker with Supabase and Next.js"
```

### Extension
Add features to an existing project. Reads existing `CLAUDE.md`, light interview.
```
/shipwright-run "Add team management with invite flow"
```

### Iteration
Quick change to existing project. Minimal questions, fast pipeline.
```
/shipwright-run --iterate "Add dark mode toggle"
```

## Design Phase

`shipwright-design` turns IREB specs into interactive HTML mockups before a single line of code is written. The phase bridges requirements (from `shipwright-project`) and implementation planning (from `shipwright-plan`).

### Snippet Assembly System

Screens are assembled from **pre-built HTML/CSS building blocks** rather than written from scratch. This makes generation 2-3x faster while keeping full visual flexibility.

```
snippets-variables.md     →  CSS :root block (flavor × character)
         ↓
snippets-layout.md        →  Page Shell + Layout (Sidebar / Top Nav / Centered Card)
         ↓
snippets-components.md    →  Components (Table, Form, Cards, Stats, Modal, Tabs, ...)
         ↓
Assembled Screen           →  designs/screens/NN-name.html
```

All visual properties (colors, fonts, shadows, radii) are controlled by CSS custom properties — set once per project based on the design interview. The snippets define **structure and layout**, not visual style.

### Design Review Workflow

After generation, `shipwright-design` produces an integrated review viewer (`designs/index.html`) that runs in the browser:

- **Grid View** — All screens as thumbnail cards with live iframe previews, grouped by split
- **Viewer Mode** — Full-size iframe with prev/next navigation, keyboard shortcuts
- **Feedback Panel** — 340px right side panel with status buttons (Approved / Changes / Rejected), free-text comments, auto-save to localStorage, previous round history
- **Export** — Generates `design-feedback-roundN.md` via save dialog

The review viewer uses the project's own design tokens — it feels native to the app being designed.

### Feedback Loop

After generation, the skill enters a review loop:

```
Generate screens + index.html
  │
  ├── Print review instructions
  ├── AskUserQuestion (stays open while user reviews in browser)
  │
  ├─[A] All approved  → Spec Backflow (full) → Session Handoff → /shipwright-plan
  ├─[B] Feedback ready → Read feedback file → Revise screens → Loop back
  └─[C] Pause          → Save state → Resume later
```

**Spec Backflow** keeps upstream artifacts in sync with design decisions:
- Updates `planning/*/spec.md` with screen references per FR
- Logs design decisions to `agent_docs/decision_log.md` (ADR format)
- Writes `designs/design-handoff.md` at finalization for `/shipwright-plan`

## Design System Flavors

`shipwright-design` generates HTML mockups based on a selectable design system flavor. The flavor is chosen during the design interview and determines the visual language (components, spacing, colors, typography) for all generated screens.

| Flavor | Design System | Best For |
|--------|--------------|----------|
| `untitled-ui` | [Untitled UI](https://www.untitledui.com/) | SaaS dashboards, admin panels, B2B apps (default) |
| `material-design` | [Material Design 3](https://m3.material.io/) | Consumer apps, Android-first, Google ecosystem |
| `custom` | User-provided | Upload your own brand guidelines to `designs/uploads/` |

## Deployment Flavors

`shipwright-deploy` uses a flavor pattern for deployment targets. Each flavor implements the same interface but talks to a different platform.

| Flavor | Platform | Region | Status |
|--------|----------|--------|--------|
| `jelastic` | [Jelastic](https://jelastic.com/) (Infomaniak) | Switzerland | Implemented |

Additional flavors (e.g., Vercel, Fly.io) can be added by implementing the deploy client interface. See `plugins/shipwright-deploy/skills/deploy/references/deploy-flavors.md`.

## Stack Profiles

Profiles define the entire stack: versions, folder structure, deploy target, test strategy, linting, CI, UX patterns, and architecture rules.

| Profile | Stack | Deploy |
|---------|-------|--------|
| `supabase-nextjs` | Next.js 16 · Supabase · Tailwind 4 · shadcn/ui · Zustand · Vitest · Playwright | Jelastic (Infomaniak) |

## Architecture

```
shipwright/
├── plugins/                          # Claude Code plugins (one per SDLC phase)
│   ├── shipwright-run/               # Orchestrator
│   ├── shipwright-project/           # Requirements decomposition
│   ├── shipwright-plan/              # Deep planning
│   ├── shipwright-build/             # TDD implementation
│   ├── shipwright-test/              # Test runner
│   ├── shipwright-security/          # Security scanning (Aikido)
│   ├── shipwright-deploy/            # Deployment
│   └── shipwright-changelog/         # Changelog + PR
├── shared/                           # Shared across plugins
│   ├── profiles/                     # Stack profile definitions (JSON)
│   ├── templates/                    # CLAUDE.md, agent_docs, CI/CD, rules templates
│   └── scripts/                      # Shared utilities (errors, validation_loop, etc.)
├── integration-tests/                # Cross-plugin integration tests
└── Spec/                             # Design specifications
```

Each plugin follows the [Claude Code plugin structure](https://docs.anthropic.com/en/docs/claude-code):
```
plugins/shipwright-{name}/
├── .claude-plugin/plugin.json        # Plugin metadata
├── hooks/hooks.json                  # Claude Code hooks
├── agents/                           # Subagent definitions
├── skills/{name}/
│   ├── SKILL.md                      # Main skill definition
│   └── references/                   # Lazy-loaded protocol docs
├── scripts/                          # Python scripts
├── tests/                            # Plugin-specific tests
└── pyproject.toml
```

## Design Principles

1. **Describe, don't configure** — user describes what they want, agent infers settings
2. **DEV auto, PROD manual** — fast feedback loop, safe production
3. **Every skill works standalone** — `shipwright-run` orchestrates, but each skill works independently
4. **Test-first** — TDD with IREB acceptance criteria → testable specs from day one
5. **Iteration is first-class** — `--iterate` is the daily workflow after initial build
6. **Resume anywhere** — file-based state allows interrupting and resuming at any point
7. **Migration safety** — destructive SQL changes always require confirmation
8. **Linters over instructions** — mechanical enforcement (hooks) beats advisory prose (CLAUDE.md rules)
9. **Progressive disclosure** — CLAUDE.md stays lean (~200 lines), details live in `@agent_docs/`

## Constitution

All Shipwright agents follow the **Constitution** (`shared/constitution.md`) — a declarative set of behavioral boundaries organized as ALWAYS / ASK FIRST / NEVER rules. Several rules are derived from agent reliability patterns identified in the Claude Code source code leak (March 2026) — verification after edits, context window awareness, and honest test reporting.

### ALWAYS (do without asking)
- Run tests before committing — tests must pass
- Generate rollback SQL for every migration
- Use Conventional Commits and parameterized queries
- Run self-review checklist before committing
- Keep files under 300 lines
- Fix the code, not the test — never weaken assertions
- Diagnose test failures before skipping — attempt autonomous fix, escalate after 2 attempts
- Verify after non-trivial edits — run type-checker or linter before reporting success
- Re-read files before editing in long sessions — do not trust cached content after auto-compaction
- State explicitly when search results may be truncated

### ASK FIRST (require confirmation)
- Destructive database operations, PROD deployments, rollback decisions
- Skipping test layers, overriding validation gates
- Continuing after 3 failed fix attempts

### NEVER (hard stops)
- `rm -rf` on root, `git push --force` to main, `git reset --hard`
- Skip or weaken tests, add features beyond spec (YAGNI)
- Hardcode secrets or commit `.env` files
- Retry blindly without root-cause analysis
- Claim "all tests pass" when output shows failures

See `shared/constitution.md` for the full document including escalation thresholds, test layer boundaries, and programmatic enforcement mapping.

## Claude Architect Best Practices

Shipwright implements best practices from the [Anthropic Claude Certified Architect](https://www.anthropic.com/certification) exam guide across all 5 certification domains:

| Domain | Best Practice | Implementation |
|--------|--------------|----------------|
| Agentic Architecture (27%) | Hooks > Prompts for compliance | Compliance enforcement hooks (soft-block with override) |
| Tool Design & MCP (18%) | Structured errors with categories | `shared/scripts/lib/errors.py` — `transient`, `validation`, `business`, `permission` |
| Claude Code Config (20%) | Path-specific `.claude/rules/` | Rule templates auto-generated per profile (tests, API, migrations, components, config) |
| Prompt Engineering (20%) | Few-shot examples > prose instructions | 2-3 input→output example pairs in every subagent definition |
| Context & Reliability (15%) | Specific error feedback, not "try again" | Validation loop with retriable vs terminal error distinction |

Additional patterns: independent CI/CD review sessions (`claude -p --output-format json`), override logging for compliance, configurable enforcement thresholds per project, secret scanning, file size guards, and CLAUDE.md drift detection.

## Quality Gates

Shipwright enforces quality at multiple levels through **mechanical enforcement** — hooks that block or warn deterministically, not advisory prose that agents may ignore. This approach follows the "Linters over Instructions" principle: automated enforcement beats documentation.

### Enforcement Hooks

| Hook | Trigger | Action | Exit |
|------|---------|--------|------|
| Dangerous Command Guard | `PreToolUse` (Bash) | Block `git push --force`, `rm -rf /`, `DROP DATABASE` | 2 (block) |
| RTM Coverage Check | `PreToolUse` (`git commit`) | Soft-block if RTM coverage < threshold | 2 (overridable) |
| Security Findings Check | `PreToolUse` (deploy) | Soft-block if unresolved critical findings | 2 (overridable) |
| **Secret Scanning** | `PostToolUse` (Write/Edit) | Detect API keys, tokens, passwords, private keys | 2 (block) |
| **File Size Guard** | `PostToolUse` (Write/Edit) | Warn when files exceed 300 lines (configurable) | 2 (block) |
| Destructive Migration Scan | `PostToolUse` (Write/Edit SQL) | Detect `DROP TABLE`, `DROP COLUMN`, `TRUNCATE` | 2 (block) |
| **CLAUDE.md Drift Detection** | `SessionStart` | Warn when source changed but CLAUDE.md didn't | 0 (warn) |
| Documentation Check | `Stop` (session end) | Verify decision_log.md + session_handoff.md | 0 (warn) |

### In-Band Quality Gates

| Gate | When | Action |
|------|------|--------|
| Code Review | After each section | Subagent reviews diff against spec |
| External LLM Review | After planning | Gemini + OpenAI review plan in parallel |

### Secret Scanning

The secret scanner detects common credential patterns in written/edited files:
- AWS Access Keys (`AKIA...`)
- API keys (`sk-...`, `ghp_...`, `gho_...`, `glpat-...`)
- Slack tokens (`xoxb-...`, `xoxp-...`)
- PEM private keys
- Hardcoded passwords/secrets in assignments
- Connection strings with embedded credentials

Automatically skips `.env.example`, test fixtures, lock files, and vendor directories.

### File Size Guard

Large files degrade AI agent performance by consuming excessive context window space. The guard warns when source files exceed **300 lines** (configurable via `shipwright_build_config.json → enforcement.max_file_lines`). Automatically skips config files (JSON, YAML, TOML), documentation (Markdown), lock files, generated code, and SQL migrations.

### CLAUDE.md Drift Detection

At session start, compares modification timestamps of key project files (`package.json`, `pyproject.toml`, `src/`, etc.) against `CLAUDE.md`. If source files changed more recently, warns the agent that documentation may be outdated. This prevents agents from working with stale architectural context — a common failure mode identified by [Anthropic's Best Practices](https://code.claude.com/docs/en/best-practices).

### Override & Audit

Compliance hooks use **exit code 2 (soft-block)**: the user can say "Continue anyway" — the override gets logged to `agent_docs/compliance_overrides.log` and flagged again at the next checkpoint.

## Getting Started

See the **[Setup Guide](docs/setup-guide.md)** for step-by-step installation instructions.

**Quick version:**
```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
~/shipwright/scripts/install.sh
```

### Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI (Pro or Max subscription)
- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Git
- Optional: `OPENROUTER_API_KEY` for external plan review (recommended)
- Optional: `JELASTIC_TOKEN` for deployment (Infomaniak)
- Optional: Aikido Security account + API credentials for security scanning
- Optional: Node.js 22.x for supabase-nextjs profile

## Development

```bash
# Install dependencies
uv sync

# Run tests for a specific plugin
uv run pytest plugins/shipwright-project/tests/ -v

# Run all integration tests
uv run pytest integration-tests/ -v
```

## Upstream

Shipwright builds on the [Deep Trilogy](https://github.com/piercelamb) by Pierce Lamb:
- [deep-project](https://github.com/piercelamb/deep-project) v0.2.1 → `shipwright-project`
- [deep-plan](https://github.com/piercelamb/deep-plan) v0.3.2 → `shipwright-plan`
- [deep-implement](https://github.com/piercelamb/deep-implement) v0.2.1 → `shipwright-build`

The remaining plugins (`shipwright-run`, `shipwright-test`, `shipwright-deploy`, `shipwright-changelog`) are original work.

## License

[MIT](LICENSE)

---

Built by [svenroth.ai](https://github.com/svenroth-ai). Powered by Claude Code.
