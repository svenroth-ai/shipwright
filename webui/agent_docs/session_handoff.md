# Session Handoff — Split 01-core Complete

Generated: 2026-04-11 00:42 UTC

## Current State

- **Split**: 01-core (10/10 sections complete)
- **Status**: Split complete, 2 more splits remaining (02-ui-shell, 03-features)
- **Branch**: main
- **Tests**: 145 passing across 26 test files

## What Was Built

### Server Backend (Hono + Node.js)
All core server modules for the Shipwright Command Center:

| Section | Module | Tests |
|---------|--------|-------|
| 01 | Hono server, config, error handler, logger | 15 |
| 02 | Shared TypeScript types (10 type files) | tsc |
| 03 | Event reader/writer, EventStore with replay | 16 |
| 04 | TaskManager with Kanban status derivation | 15 |
| 05 | Claude CLI adapter, NDJSON parser | 18 |
| 06 | ProcessGovernor (semaphore, heartbeat, PIDs) | 9 |
| 07 | ProjectManager, ConfigReader, FileWatcher | 20 |
| 08 | InboxManager, ChatStore | 16 |
| 09 | SSEManager with broadcast + route | 13 |
| 10 | All REST API routes + wired index.ts | 27 |

### Key Architecture
- **In-memory state from events** — no DB, events.jsonl is source of truth
- **Injectable deps** — all modules use DI interfaces for testability
- **Process governor** — max 3 concurrent Claude CLIs, queue overflow, PID tracking
- **SSE via ReadableStream** — broadcast to all connected clients
- **Path traversal protection** on docs endpoint

## Files Created

```
server/
  package.json, tsconfig.json, vitest.config.ts
  src/
    index.ts              — Main entry, full manager initialization + graceful shutdown
    config.ts             — Centralized config (port, maxConcurrent, registryDir)
    middleware/
      error-handler.ts    — AppError class + Hono error handler
      logger.ts           — Structured JSON request logger
    core/
      event-store.ts      — In-memory event store with replay + dedup
      task-manager.ts     — Kanban status derivation from pipeline phases
      ndjson-parser.ts    — NDJSON line parser + AskUserQuestion detection
      claude-adapter.ts   — Claude CLI spawn, stdin, lifecycle tracking
      process-governor.ts — Concurrency semaphore + PID persistence
      heartbeat.ts        — 30s health check scheduler
      project-manager.ts  — Project CRUD + discovery + persistence
      file-watcher.ts     — Chokidar watcher with 300ms debounce
      inbox-manager.ts    — AskUserQuestion aggregation + answer delivery
      chat-store.ts       — JSONL chat history per task
      sse-manager.ts      — Multi-client SSE broadcast
    bridge/
      event-reader.ts     — Tolerant JSONL parser
      event-writer.ts     — Lockfile-based event appender
      config-reader.ts    — Reads shipwright_*_config.json files
      pipeline-state.ts   — Merges event + config pipeline state
      doc-index.ts        — File tree builder + safe content reader
      intent-classifier.ts — Shell-out to classify_intent/complexity.py
    routes/
      projects.ts         — GET/POST/PATCH/DELETE /api/projects
      tasks.ts            — GET/POST tasks, PATCH status
      inbox.ts            — GET /api/inbox, POST answer
      chat.ts             — GET history, POST message
      pipeline.ts         — GET /api/projects/:id/pipeline
      docs.ts             — GET file tree + content
      classify.ts         — POST classify (shell-out)
      settings.ts         — GET/PUT /api/settings
      sse.ts              — GET /api/events (SSE stream)
client/
  tsconfig.json
  src/types/              — 10 shared type definition files
```

## How to Resume

1. Next split is **02-ui-shell** (React frontend)
2. Section files: `planning/02-ui-shell/sections/`
3. Run: `/shipwright-build @webui/planning/02-ui-shell/sections/01-...`
4. Or run `/shipwright-test` to test split 01-core first

## Known Issues

- `.gitignore` in webui/ ignores `agent_docs/`, `planning/`, and configs — these need to be un-ignored for the WebUI project specifically
- Commits for sections 02-04 landed on `main` instead of the feature branch (branch was created for 01 but subsequent commits continued on main after a divergence)
- `node-cron` and `proper-lockfile` lack `@types/*` packages — may need DefinitelyTyped or local declarations for strict TS
