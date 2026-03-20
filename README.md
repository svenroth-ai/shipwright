# Shipwright SDLC

AI-powered software delivery lifecycle framework built on [Claude Code](https://docs.anthropic.com/en/docs/claude-code). From user description to deployed, tested, secured application — in one command.

## What is Shipwright?

Shipwright wraps the [Deep Trilogy](https://github.com/piercelamb/deep-project) (deep-project, deep-plan, deep-implement) into a full SDLC pipeline. Instead of running 3 separate skills manually, you invoke one command and the agent handles everything:

```
/shipwright-run "A SaaS time tracking app with Supabase and Next.js"
```

Shipwright infers your stack, deploys to DEV automatically, runs tests, creates changelogs, and opens PRs — while you focus on what matters.

## Skills

| Skill | Purpose |
|-------|---------|
| `shipwright-run` | Orchestrator — entry point for everything |
| `shipwright-project` | Requirements decomposition into splits + specs |
| `shipwright-plan` | Planning with research, interview, and external LLM review |
| `shipwright-build` | TDD implementation with code review |
| `shipwright-test` | Unit tests, E2E, smoke tests, security scans |
| `shipwright-changelog` | Conventional Commits → changelog → PR |
| `shipwright-deploy` | Deployment with smoke test + rollback (Jelastic first) |

## Stack Profiles

Profiles define everything: stack versions, folder structure, deploy target, test strategy, linting, CI, UX patterns, and architecture rules.

**Available profiles:**
- `supabase-nextjs` — Next.js 16 + Supabase + Tailwind 4 + shadcn/ui → Jelastic

## Design Principles

1. **Describe, don't configure** — user describes what they want, agent infers settings
2. **DEV auto, PROD manual** — fast feedback loop, safe production
3. **Every skill works standalone** — `shipwright-run` orchestrates, but each skill works independently
4. **5-layer testing** — Unit → Code Review → Smoke → Playwright E2E → Aikido Security
5. **Iteration is first-class** — `--iterate` is the daily workflow after initial build

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Git

## License

[MIT](LICENSE)

---

Built by [dinovo GmbH](https://github.com/svenroth-ai). Powered by Claude Code.
