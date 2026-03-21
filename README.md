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
┌─────────────────┐
│ shipwright-run   │  Infer scope, profile, autonomy → dispatch
└────────┬────────┘
         ▼
┌─────────────────┐
│shipwright-project│  Interview → Split → IREB Specs → CLAUDE.md + agent_docs
└────────┬────────┘
         ▼  (per split)
┌─────────────────┐
│ shipwright-plan  │  Research → Interview → Plan → External LLM Review → Sections
└────────┬────────┘
         ▼  (per section)
┌─────────────────┐
│ shipwright-build │  TDD → Code Review → Conventional Commit → Feature Branch
└────────┬────────┘
         ▼
┌─────────────────┐
│ shipwright-test  │  Unit (Vitest) → Smoke → Playwright E2E → Security
└────────┬────────┘
         ▼
┌─────────────────┐
│shipwright-deploy │  Jelastic (Infomaniak) → Smoke Test → Rollback on Failure
└────────┬────────┘
         ▼
┌─────────────────┐
│shipwright-       │  Parse Commits → Changelog → Version Tag → PR
│    changelog     │
└─────────────────┘
```

## Skills

| Skill | Purpose | Key Features |
|-------|---------|-------------|
| `shipwright-run` | Orchestrator | Inference engine, scope detection, pipeline state machine |
| `shipwright-project` | Requirements | IREB-aligned specs, scope detection (Full App / Extension), chat + file + inline input |
| `shipwright-plan` | Planning | External LLM review (Gemini + OpenAI), section-writer subagent, E2E test plan |
| `shipwright-build` | Implementation | TDD loop, code-reviewer subagent, Conventional Commits, migration safety |
| `shipwright-test` | Testing | Profile-aware (Vitest/Playwright), smoke test, `--fix` auto-repair |
| `shipwright-deploy` | Deployment | Jelastic (Infomaniak, Switzerland), DEV auto / PROD manual, clone-based rollback |
| `shipwright-changelog` | Release | Keep-a-Changelog format, semver bump suggestion, PR creation |

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
│   ├── shipwright-deploy/            # Deployment
│   └── shipwright-changelog/         # Changelog + PR
├── shared/                           # Shared across plugins
│   ├── profiles/                     # Stack profile definitions (JSON)
│   ├── templates/                    # CLAUDE.md, agent_docs templates
│   └── scripts/                      # Shared utilities (smoke_test.py, etc.)
├── integration-tests/                # Cross-plugin integration tests
└── Spec/                             # Design specifications
```

Each plugin follows the [Claude Code plugin structure](https://docs.anthropic.com/en/docs/claude-code):
```
plugins/shipwright-{name}/
├── .claude-plugin/plugin.json        # Plugin metadata
├── hooks/hooks.json                  # Claude Code hooks
├── agents/                           # Subagent definitions
├── skills/shipwright-{name}/
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

## Quality Gates

Shipwright enforces quality at multiple levels:

| Hook | Trigger | Action |
|------|---------|--------|
| `PreToolUse` | Bash commands | Block `git push --force`, `rm -rf /` |
| `PostToolUse` | Write/Edit SQL | Detect `DROP TABLE`, `DROP COLUMN` → warn |
| `Stop` | Session end | Check decision_log.md and session_handoff.md |
| Code Review | After implementation | Subagent reviews diff against spec |
| External Review | After planning | Gemini + OpenAI review plan in parallel |

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
