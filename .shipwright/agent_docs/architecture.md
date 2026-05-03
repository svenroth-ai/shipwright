# Architecture — shipwright

## System Overview

+----------------------------------------------------------+
| Claude Code (host)                                       |
|   loads plugins from ~/.claude/plugins/cache/shipwright/ |
+----------------------------------------------------------+
        |
        v
+---------------------+    +--------------------------------+
| plugins/            |    | shared/                        |
|   shipwright-run    |--->|   scripts/  (lib, tools, hooks)|
|   shipwright-project|--->|   profiles/ (stack + deploy)   |
|   shipwright-plan   |--->|   templates/                   |
|   shipwright-design |--->|   prompts/  (review prompts)   |
|   shipwright-build  |--->|   config/   (defaults)         |
|   shipwright-test   |    +--------------------------------+
|   shipwright-security|              ^
|   shipwright-deploy |               | reads/writes
|   shipwright-changelog              |
|   shipwright-compliance ------------+
|   shipwright-iterate |
|   shipwright-preview |
|   shipwright-adopt   |
+---------------------+
        |
        | writes/reads in target project
        v
+----------------------------------------------------------+
| Target project                                           |
|   CLAUDE.md                                              |
|   shipwright_*_config.json (run, project, plan, build,   |
|                             compliance, sync, ...)       |
|   shipwright_events.jsonl                                |
|   .shipwright/                                           |
|     agent_docs/  planning/  compliance/  designs/        |
|     adopt/  reviews/                                     |
+----------------------------------------------------------+

## Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | — | — |
| Backend | — | — |
| Database | — | — |
| Auth | — | — |
| Runtime | python | — |

## Layers Detected

- **docs**: `docs`
- **infrastructure**: `scripts`
- **tests**: `Spec`, `integration-tests`


## Key Architecture Decisions

See `decision_log.md` for detailed ADRs. Profile-level decisions (stack, auth pattern, DB strategy, folder structure) are defined by the stack profile (`python-plugin-monorepo`).

## Data Flow

Each SDLC phase is its own Claude Code plugin under plugins/<phase>/, with the standard Claude Code plugin layout: .claude-plugin/plugin.json, hooks/hooks.json, skills/<phase>/SKILL.md, scripts/ (checks, hooks, lib, tools), tests/, and pyproject.toml. Cross-plugin code lives under shared/ (scripts, profiles, templates, prompts, config). Plugins communicate via a unified session id (SHIPWRIGHT_SESSION_ID), shared shipwright_*_config.json files written into the target project, and an append-only shipwright_events.jsonl event log. Hooks defined in hooks.json are the single source of truth for between-phase actions and quality gates; behavior is documented in docs/hooks-and-pipeline.md. Memory and decision history is captured in .shipwright/agent_docs/decision_log.md (canonical H3 ADR format) and per-iterate or per-phase artifacts under .shipwright/planning/ and .shipwright/compliance/. A separate plugin cache at ~/.claude/plugins/cache/shipwright/ is used by Claude Code at runtime; updates require running scripts/update-marketplace.sh after pushing plugin-side changes.

Secrets live exclusively in `<project_root>/.env.local`, scaffolded by `/shipwright-adopt` (Step E.5, ADR-021) and read at runtime by `shared/scripts/lib/env.py::load_shipwright_env`. Every adopted repo carries the framework-level external-review keys (OPENROUTER_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY) plus the active profile's `required_env_vars`. The file is git-ignored before write — a `.gitignore` enforcement failure aborts the scaffold rather than risking a tracked secrets file.

## See also

_Existing user-facing documentation discovered by /shipwright-adopt._

- [`README.md`](../../README.md)
- [`docs/guide.md`](../../docs/guide.md)

## Architecture Updates

- **ADR-021** (2026-05-03): Adopt scaffolds .env.local with profile + framework keys (Layer-3 SSoT)
- **ADR-024** (2026-05-03): Boundary Tests Foundation — `touches_io_boundary` risk flag + Boundary Probe sub-step in iterate Build TDD (Sub-Iterate A of campaign iterate-skill-hardening). New helper `is_io_boundary_change(changed_files)` in `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`; new reference docs `references/boundary-probes.md` (8 edge-case categories) and `references/round-trip-tests.md` (producer→file→consumer test pattern). 7th Self-Review item ("Affected Boundaries") added.
