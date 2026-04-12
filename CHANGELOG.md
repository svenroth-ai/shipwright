# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-12

Initial release of the Shipwright SDLC Framework — an AI-powered development
pipeline built on Claude Code, from project description to deployed application.

### Added

#### Pipeline Plugins
- **shipwright-run** — Orchestrator entry point with phase routing, auto-triggering, and standalone mode
- **shipwright-project** — Requirements decomposition with IREB-aligned specs, chat and inline input modes
- **shipwright-design** — UI mockup generation from IREB specs as standalone HTML
- **shipwright-plan** — Planning with E2E test plans, sprint tracking, and section-based breakdown
- **shipwright-build** — TDD implementation with code review, Conventional Commits, and feature branches
- **shipwright-test** — Unit, E2E (Playwright), and security testing with self-healing for missing artifacts
- **shipwright-changelog** — Git history analysis, Keep-a-Changelog generation, version tagging, and PRs
- **shipwright-deploy** — Jelastic (Infomaniak) deployment with smoke tests and rollback
- **shipwright-compliance** — IREB traceability, RTM, SBOM, and audit-ready reports
- **shipwright-iterate** — Lightweight SDLC for ongoing changes in completed projects
- **shipwright-preview** — Local dev server preview for built applications

#### Shared Infrastructure
- Monorepo scaffolding with stack profiles (Next.js + Supabase, custom)
- Project templates (CLAUDE.md, agent_docs, CI configs)
- Shared Python utilities (config, state, handoff, hooks)
- Constitution with ALWAYS / ASK FIRST / NEVER boundaries
- Plugin marketplace.json for Claude Code discovery
- Setup guide with installation scripts and OpenRouter support

#### Command Center (WebUI)
- **Kanban Board** — Multi-project board with columns, cards, filters, list/card view toggle, and sorting
- **Task Management** — Create, edit, close, delete tasks; New Issue modal with background auto-classification
- **Claude CLI Bridge** — Subprocess spawning (node.exe + cli.js), NDJSON stream parsing, SSE broadcast
- **Chat Rendering** — Typed message persistence (assistant, tool_use, tool_result, thinking, system, result)
- **ThinkingBlock** — Collapsible purple block with character count for Claude's thinking
- **ToolCallCard** — Tool-specific icons (Bash, Read, Write, Edit, Grep, Glob, Agent), error states with red tinting
- **Real-time Streaming** — useStreamingSSE hook for live tool calls and text as they arrive
- **Task Detail** — Resizable two-panel layout with chat engine and Smart File Viewer
- **Smart Viewer** — Tab management with renderers for code, HTML, JSON, Markdown, and diff overlays
- **File Explorer** — Directory tree with git status indicators
- **Settings** — Global + per-project settings, phase-to-status mapping, autonomy modes
- **Model Selector** — Claude Opus 4.6 / Sonnet 4.6 / Haiku 4.5 with context window display
- **Permission Modes** — Default / Plan / Auto-accept with descriptions
- **Inbox** — AskUserQuestion aggregation across projects with option buttons and free-form answers
- **Project Wizard** — 4-step modal with stack profile selection
- **Windows Auto-start** — Install script for system startup

#### Testing
- Server: 185 unit tests
- Client: 161 unit tests
- 5 E2E tests (Playwright)
- Integration tests across pipeline plugins

### Fixed
- SSE named events not received by client (onmessage → addEventListener)
- Legacy JSON-blob chat messages auto-migrated on load
- Bridge cross-platform stability (Windows cmd.exe shim bypass, PID recycling protection)
- Kanban board scroll overflow handling
- Task creation ENOENT and project directory initialization

[0.1.0]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.0
