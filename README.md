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

| Skill | Purpose |
|-------|---------|
| `shipwright-run` | Orchestrator — inference engine, scope detection, pipeline state machine |
| `shipwright-project` | Requirements — IREB-aligned specs, scope detection, chat + file + inline input |
| `shipwright-design` | UI Design — snippet-assembled HTML mockups, review viewer, design system flavors |
| `shipwright-plan` | Planning — external LLM review, section-writer subagent, E2E test plan |
| `shipwright-build` | Implementation — TDD loop, code-reviewer subagent, Conventional Commits |
| `shipwright-test` | Testing — profile-aware (Vitest/Playwright), smoke test, `--fix` auto-repair |
| `shipwright-security` | Security — Aikido API scanning, finding classification, remediation loop |
| `shipwright-deploy` | Deployment — deployment flavors, DEV auto / PROD manual, clone-based rollback |
| `shipwright-changelog` | Release — Keep-a-Changelog format, semver bump suggestion, PR creation |
| `shipwright-preview` | Preview — local dev server, browser URL, profile-driven (available after first build split) |
| `shipwright-compliance` | Compliance — IREB traceability, RTM, SBOM, test evidence, change history reports |

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

For the complete documentation — including phase-by-phase details, configuration, troubleshooting, and the full constitution — see **[docs/guide.md](docs/guide.md)**.

## Quality & Safety

Shipwright enforces quality through mechanical hooks — not advisory prose. Hooks fire on Claude Code events and block dangerous actions deterministically.

| Hook | What it prevents |
|------|-----------------|
| Dangerous Command Guard | `git push --force` to main, `rm -rf /`, `DROP DATABASE` |
| Secret Scanning | API keys, tokens, passwords, PEM keys in source code |
| Destructive Migration Scan | `DROP TABLE` / `DROP COLUMN` without rollback SQL |
| File Size Guard | Source files exceeding 300 lines |
| Drift Detection | Stale CLAUDE.md when source files changed |

All hooks use exit code 2 (soft-block): you can override, but the override is logged. See the [full documentation](docs/guide.md) for details on the constitution, TDD workflow, code review, and migration safety.

## Getting Started

```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync
```

Then type `/shipwright-run` in Claude Code. For the complete setup guide (deployment, external review, security scanning, platform notes), see **[docs/guide.md](docs/guide.md)**.

### Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Pro or Max subscription)
- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Git

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
