# Architecture — Shipwright Command Center

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (React)                           │
│                                                                  │
│  ── Kanban Dashboard (default) ──────────────────────────────    │
│  ┌──────────┬────────────────────────────────────────────────┐   │
│  │ Sidebar  │  [Project Tabs]  [Filters]  [View] [+New Issue]│   │
│  │  Nav     ├────────────┬───────────┬──────────┬────────────┤   │
│  │ 200px    │ Backlog    │In Progress│In Review │ Done       │   │
│  │          │  (cards)   │  (cards)  │  (cards) │  (cards)   │   │
│  └──────────┴────────────┴───────────┴──────────┴────────────┘   │
│                                                                  │
│  ── Task Detail (on card click) ─────────────────────────────    │
│  ┌──────────┬──────────────────────────┬─────────────────────┐   │
│  │ Sidebar  │ Chat  (~60%)             │ Smart Viewer (~40%) │   │
│  │  Nav     │ streaming messages       │ tabbed file view    │   │
│  │ 200px    │ tool-call cards          │ + Explorer slide-in │   │
│  │          │ AskUser cards            │                     │   │
│  │          │ [input + toolbar]        │                     │   │
│  └──────────┴──────────────────────────┴─────────────────────┘   │
│          │ TanStack Query             │ EventSource (SSE)        │
└──────────┼────────────────────────────┼──────────────────────────┘
           │ REST API                   │ SSE /api/events
┌─────────┼─────────────────────────┼─────────────────────────┐
│         ▼                         ▼                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Hono Server (port 3847)                │    │
│  │                                                     │    │
│  │  Routes ──► Core Managers ──► Bridge                │    │
│  │  /api/*     task-manager      config-reader         │    │
│  │             inbox-manager     event-reader           │    │
│  │             project-manager   pipeline-state         │    │
│  │             chat-store        doc-index              │    │
│  │             sse-manager       intent-classifier      │    │
│  │             process-governor                         │    │
│  │             heartbeat                                │    │
│  └───────┬─────────────────┬───────────────────────────┘    │
│          │                 │                                 │
│    ┌─────▼──────┐   ┌─────▼──────────────────────┐         │
│    │ Claude CLI │   │ Project Filesystem          │         │
│    │ Subprocess │   │ shipwright_events.jsonl      │         │
│    │ (per proj) │   │ shipwright_*_config.json     │         │
│    │ --stream   │   │ planning/, designs/, src/    │         │
│    └────────────┘   └────────────────────────────┘         │
│                                                             │
│  ~/.shipwright-webui/                                       │
│    projects.json (global registry)                          │
│    settings.json (global settings)                          │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Task Lifecycle
```
User clicks "New Task"
  → POST /api/projects/:id/tasks (description, intent)
  → task_created event → events.jsonl
  → Spawn Claude CLI subprocess
  → NDJSON stream parsed → SSE to frontend
  → Chat messages rendered in real-time
  → If AskUserQuestion → Inbox item created → SSE notification
  → User answers → stdin to Claude → stream continues
  → work_completed event → events.jsonl
  → Task status: done
```

### State Reconstruction (on server start)
```
1. Read ~/.shipwright-webui/projects.json → project list
2. For each project:
   a. Read shipwright_events.jsonl → replay events
   b. Build in-memory task state (done/failed from events)
   c. Check for orphaned processes (task_created without work_completed)
   d. Read shipwright_*_config.json → pipeline state
3. Start heartbeat scheduler (30s)
4. Start file watchers (chokidar) on events + configs
```

### SSE Event Types
```
project:updated    — Project state changed
task:created       — New task started
task:updated       — Task status changed (running → waiting → done)
inbox:new          — New question needs user attention
inbox:answered     — Question answered
chat:message       — New chat message (streamed)
pipeline:updated   — Pipeline phase status changed
```

## Key Patterns

### Claude CLI Adapter
- One subprocess per active task (not per project)
- `claude --output-format stream-json --session-id {id} --plugin-dir {p1} --plugin-dir {p2} ...`
- Parse NDJSON: each line is `{type, ...}` where type ∈ {assistant, tool_use, tool_result, result}
- AskUserQuestion detected from tool_use with name "AskUserQuestion"
- Process blocks on stdin until user responds

### Event Deduplication
- Deploy and Changelog phases emit phase_completed events WITH --detail (URL, PR)
- Orchestrator also emits phase_completed WITHOUT detail
- WebUI deduplicates: group by (type, phase, timestamp within 60s), prefer event with detail field

### Process Governor
- Semaphore with configurable max (default 3)
- Queue: if max reached, new tasks wait
- Heartbeat (30s): check if processes are alive, clean up dead ones
- Startup: kill orphaned Claude processes (PID file tracking)

### Build Dashboard
- `agent_docs/build_dashboard.md` is auto-generated by `update_build_dashboard.py`
- Tracks per-section build progress, pipeline phase status, session history
- Updated at each build step checkpoint and on context-pressure pause
- Read-only — do not edit manually
