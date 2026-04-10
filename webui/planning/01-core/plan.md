# Implementation Plan — Backend Core & Claude Adapter

## Overview

This plan covers the complete server-side implementation of the Shipwright Command Center: a Hono-based HTTP server that manages multiple Shipwright projects in parallel through Claude CLI subprocesses. The architecture follows an event-sourced pattern where `shipwright_events.jsonl` is the single source of truth for task and pipeline state, reconstructed into in-memory state on startup and kept current via chokidar file watchers and NDJSON stream parsing from running Claude processes. All real-time updates flow to the browser through Server-Sent Events (SSE).

The implementation is organized into 10 sections in strict dependency order. Sections 01-02 establish the foundation (Hono server, shared types). Sections 03-04 build the event-sourced state layer (event reader, task/kanban derivation). Sections 05-06 handle Claude subprocess management (adapter, governor). Sections 07-08 add multi-project support and user interaction (registry, inbox/chat). Section 09 provides the real-time push layer (SSE). Section 10 wires everything together with REST API routes. Each section is self-contained: it declares its file outputs, implementation steps, and test strategy so that `/shipwright-build` can implement it independently given only the prior sections' outputs.

The TDD approach for every section follows the same rhythm: define TypeScript interfaces first (or import from shared types), write unit tests for pure logic (parsers, state derivation, mapping functions), implement to green, then add integration tests where the section exposes HTTP endpoints. All core modules use dependency injection for file system operations, `child_process.spawn`, and chokidar — enabling fast, deterministic tests without real subprocesses or file I/O (QR-01.09).

## SECTION_MANIFEST
```yaml
sections:
  - id: "01"
    name: "project-setup"
    title: "Project Setup & Hono Server"
    depends_on: []
    frs: ["FR-01.01", "FR-01.02", "FR-01.03"]
  - id: "02"
    name: "shared-types"
    title: "Shared TypeScript Types"
    depends_on: ["01"]
    frs: []
  - id: "03"
    name: "event-system"
    title: "Event System — Reader, Replay & State"
    depends_on: ["02"]
    frs: ["FR-01.14", "FR-01.15", "FR-01.16", "FR-01.17", "FR-01.18"]
  - id: "04"
    name: "task-manager"
    title: "Task Manager — Kanban Status Derivation"
    depends_on: ["02", "03"]
    frs: ["FR-01.44", "FR-01.45", "FR-01.46"]
  - id: "05"
    name: "claude-adapter"
    title: "Claude CLI Adapter"
    depends_on: ["02"]
    frs: ["FR-01.07", "FR-01.08", "FR-01.09", "FR-01.10", "FR-01.11", "FR-01.12", "FR-01.13"]
  - id: "06"
    name: "process-governor"
    title: "Process Governor — Concurrency & Lifecycle"
    depends_on: ["05"]
    frs: ["FR-01.19", "FR-01.20", "FR-01.21", "FR-01.22", "FR-01.23"]
  - id: "07"
    name: "project-registry"
    title: "Multi-Project Registry & File Watcher"
    depends_on: ["02", "03"]
    frs: ["FR-01.24", "FR-01.25", "FR-01.26", "FR-01.33", "FR-01.34", "FR-01.35"]
  - id: "08"
    name: "inbox-chat"
    title: "Inbox Manager & Chat Store"
    depends_on: ["05", "07"]
    frs: ["FR-01.27", "FR-01.28", "FR-01.29", "FR-01.30", "FR-01.31", "FR-01.32"]
  - id: "09"
    name: "sse-manager"
    title: "SSE Manager — Real-Time Event Streaming"
    depends_on: ["01"]
    frs: ["FR-01.04", "FR-01.05", "FR-01.06"]
  - id: "10"
    name: "api-routes"
    title: "REST API Routes"
    depends_on: ["04", "06", "07", "08", "09"]
    frs: ["FR-01.36", "FR-01.37", "FR-01.38", "FR-01.39", "FR-01.40", "FR-01.41", "FR-01.42", "FR-01.43", "FR-01.47"]
```

## Sections

---

### Section 01: Project Setup & Hono Server
**Goal:** Establish the Node.js project structure, install all dependencies, configure TypeScript strict mode, and create a minimal Hono server with CORS, static file serving, and a health endpoint. This is the scaffold that all subsequent sections build on.

**FRs:** FR-01.01, FR-01.02, FR-01.03

**Files:**
- `server/package.json` — dependencies and scripts
- `server/tsconfig.json` — TypeScript strict configuration
- `server/src/index.ts` — Hono app entry point, middleware, server startup
- `server/src/config.ts` — centralized configuration (port, paths, defaults)
- `server/vitest.config.ts` — test runner configuration
- `server/src/middleware/error-handler.ts` — Hono error middleware returning JSON error bodies
- `server/src/middleware/logger.ts` — structured request logging middleware

**Implementation Steps:**
1. Initialize `server/package.json` with `name`, `version`, `type: "module"`, and scripts (`dev`, `build`, `start`, `test`). Add dependencies: `hono`, `@hono/node-server`, `chokidar`, `node-cron`, `proper-lockfile`, `uuid`. Add dev dependencies: `typescript`, `vitest`, `@types/node`, `tsx`.
2. Create `server/tsconfig.json` with `"strict": true`, `"target": "ES2022"`, `"module": "NodeNext"`, `"moduleResolution": "NodeNext"`, `"outDir": "./dist"`, `"rootDir": "./src"`. Add path alias `@shared/*` pointing to `../client/src/types/*` so server can import shared types.
3. Create `server/src/config.ts` exporting a `ServerConfig` object with: `port` (from `PORT` env var or 3847), `maxConcurrent` (from `SHIPWRIGHT_MAX_CONCURRENT` env var or 3), `registryDir` (resolving `~/.shipwright-webui/`), `heartbeatIntervalMs` (30000), `staticDir` (path to client build output). Use `process.env` reads with fallback defaults.
4. Create `server/src/middleware/error-handler.ts` — Hono `onError` handler that catches all unhandled errors, logs them with structured context, and returns `{ error: string, detail?: string }` with appropriate HTTP status codes (400 for validation, 404 for not found, 500 for unexpected). Use a custom `AppError` class with a `statusCode` property to distinguish error types.
5. Create `server/src/middleware/logger.ts` — middleware that logs each request with method, path, status code, and duration in milliseconds. Use `console.log` with JSON-structured output for machine parseability (QR-01.08).
6. Create `server/src/index.ts`:
   - Import Hono and `@hono/node-server` `serve()`.
   - Instantiate Hono app.
   - Register CORS middleware for `localhost:*` origins (FR-01.03). Use Hono's built-in `cors()` from `hono/cors`.
   - Register error handler middleware.
   - Register logger middleware.
   - Serve static files from `config.staticDir` at `/` using Hono's `serveStatic()` from `@hono/node-server/serve-static`.
   - Add `GET /api/health` returning `{ status: "ok", version: string, uptime: number }`.
   - Call `serve({ fetch: app.fetch, port: config.port })` and log the listening address.
7. Create `server/vitest.config.ts` with TypeScript path aliases matching tsconfig, test file pattern `**/*.test.ts`, and `threads: true`.

**Test Strategy:**
- Unit: Test `config.ts` reads environment variables and applies defaults correctly. Test `AppError` class creates proper error instances with status codes.
- Integration: Use Hono's `app.request()` test helper (no real HTTP server needed) to verify:
  - `GET /api/health` returns 200 with expected JSON shape.
  - Unknown routes return 404 with JSON error body.
  - CORS headers are present on responses for localhost origins.
  - Error handler produces correct JSON for thrown `AppError` instances.

---

### Section 02: Shared TypeScript Types
**Goal:** Define all TypeScript interfaces used by both server and client. These are the data contracts that every subsequent section depends on. Placing them in `client/src/types/` and importing via path alias ensures a single source of truth.

**FRs:** (supports all FRs — no specific FR)

**Files:**
- `client/src/types/project.ts` — Project, ProjectSettings, ProjectStatus interfaces
- `client/src/types/task.ts` — Task, KanbanStatus, TaskStatus, PhaseToStatusMapping interfaces
- `client/src/types/event.ts` — ShipwrightEvent, EventType union, specific event payloads (TaskCreatedPayload, PhaseCompletedPayload, WorkCompletedPayload)
- `client/src/types/inbox.ts` — InboxItem, InboxStatus interfaces
- `client/src/types/chat.ts` — ChatMessage, ChatMessageType union, NdjsonMessage interfaces
- `client/src/types/pipeline.ts` — PipelineRun, PipelinePhase, PhaseStatus interfaces
- `client/src/types/sse.ts` — SSEEvent, SSEEventType union
- `client/src/types/settings.ts` — GlobalSettings interface
- `client/src/types/api.ts` — ApiResponse<T>, ApiError, PaginatedResponse<T> generic wrappers
- `client/src/types/index.ts` — barrel export of all types

**Implementation Steps:**
1. Create `client/src/types/project.ts`:
   - `ProjectStatus` as const union: `"active" | "archived" | "error"`.
   - `ProjectSettings` interface: `phaseToStatusMapping?: Record<string, KanbanStatus>`, `claudePluginDirs?: string[]`.
   - `Project` interface: `id: string`, `name: string`, `path: string`, `profile: string`, `status: ProjectStatus`, `lastActive: string` (ISO timestamp), `settings?: ProjectSettings`, `createdAt: string`.
2. Create `client/src/types/task.ts`:
   - `KanbanStatus` as const union: `"backlog" | "in_progress" | "in_review" | "done" | "failed" | "cancelled"`.
   - `TaskStatus` as const union: `"pending" | "running" | "waiting" | "done" | "failed" | "orphaned" | "cancelled"`.
   - `PhaseToStatusMapping` as `Record<string, KanbanStatus>`.
   - `Task` interface: `id: string`, `projectId: string`, `description: string`, `intent?: string`, `priority?: string`, `complexity?: string`, `status: TaskStatus`, `kanbanStatus: KanbanStatus`, `currentPhase?: string`, `sessionId: string`, `pid?: number`, `exitCode?: number`, `createdAt: string`, `updatedAt: string`.
3. Create `client/src/types/event.ts`:
   - `EventType` as const union: `"task_created" | "phase_started" | "phase_completed" | "work_completed" | "work_failed" | "task_cancelled"`.
   - `ShipwrightEvent` interface: `type: EventType`, `timestamp: string`, `task_id: string`, `project_id?: string`, `phase?: string`, `detail?: string`, `source?: string`, `description?: string`, `intent?: string`, `priority?: string`, plus `[key: string]: unknown` for extensibility.
4. Create `client/src/types/inbox.ts`:
   - `InboxStatus` as const union: `"pending" | "answered"`.
   - `InboxItem` interface: `id: string`, `projectId: string`, `taskId: string`, `question: string`, `context?: string`, `options?: string[]`, `answer?: string`, `status: InboxStatus`, `createdAt: string`, `answeredAt?: string`.
5. Create `client/src/types/chat.ts`:
   - `ChatMessageType` as const union: `"assistant" | "tool_use" | "tool_result" | "result" | "user" | "system"`.
   - `ChatMessage` interface: `id: string`, `taskId: string`, `type: ChatMessageType`, `content: string`, `toolName?: string`, `toolInput?: unknown`, `toolOutput?: unknown`, `timestamp: string`.
   - `NdjsonMessage` interface: `type: string`, `message?: unknown`, `tool_name?: string`, `tool_input?: unknown`, `content?: string`, `result?: string`, `session_id?: string`, plus `[key: string]: unknown`.
6. Create `client/src/types/pipeline.ts`:
   - `PhaseStatus` as const union: `"pending" | "running" | "completed" | "failed" | "skipped"`.
   - `PipelinePhase` interface: `name: string`, `status: PhaseStatus`, `startedAt?: string`, `completedAt?: string`, `detail?: string`.
   - `PipelineRun` interface: `projectId: string`, `phases: PipelinePhase[]`, `currentPhase?: string`, `taskId?: string`.
7. Create `client/src/types/sse.ts`:
   - `SSEEventType` as const union: `"project:updated" | "task:created" | "task:updated" | "inbox:new" | "inbox:answered" | "chat:message" | "pipeline:updated"`.
   - `SSEEvent<T = unknown>` interface: `type: SSEEventType`, `payload: T`, `timestamp: string`.
8. Create `client/src/types/settings.ts`:
   - `GlobalSettings` interface: `port: number`, `maxConcurrent: number`, `heartbeatIntervalMs: number`, `claudeCliPath?: string`, `defaultProfile?: string`.
9. Create `client/src/types/api.ts`:
   - `ApiResponse<T>` interface: `data: T`.
   - `ApiError` interface: `error: string`, `detail?: string`.
   - `PaginatedResponse<T>` interface extending `ApiResponse<T[]>` with `total: number`, `offset: number`, `limit: number`.
10. Create `client/src/types/index.ts` — barrel export re-exporting all types from each file.

**Test Strategy:**
- Unit: Type-only section — no runtime logic to test. Validate that types compile cleanly with `tsc --noEmit`. Write a small type-check test file that constructs objects of each interface to ensure no type errors. This test runs as part of the TypeScript compiler check, not vitest.
- Integration: N/A.

---

### Section 03: Event System — Reader, Replay & State
**Goal:** Implement the tolerant JSONL event reader, event replay engine that reconstructs in-memory task and pipeline state from the event log, orphaned task detection, phase deduplication, and the ability to emit new events (task_created) via file append with proper-lockfile.

**FRs:** FR-01.14, FR-01.15, FR-01.16, FR-01.17, FR-01.18

**Files:**
- `server/src/bridge/event-reader.ts` — tolerant JSONL parser, file reading with lockfile
- `server/src/bridge/event-writer.ts` — append events to JSONL with proper-lockfile
- `server/src/core/event-store.ts` — in-memory event store, replay engine, state reconstruction
- `server/src/bridge/event-reader.test.ts` — unit tests for reader
- `server/src/bridge/event-writer.test.ts` — unit tests for writer
- `server/src/core/event-store.test.ts` — unit tests for replay and state derivation

**Implementation Steps:**
1. Create `server/src/bridge/event-reader.ts`:
   - Export `readEventsFromFile(filePath: string, fs?: FileSystemDeps): Promise<ShipwrightEvent[]>`.
   - Read file content as UTF-8 string. If file does not exist, return empty array (graceful).
   - Split by newlines. For each line: try `JSON.parse()`, validate it has at least `type` and `timestamp` fields, push to result array. On parse error or missing fields, skip the line and log a warning with line number (QR-01.06, FR-01.14).
   - `FileSystemDeps` interface: `{ readFile: (path: string, encoding: string) => Promise<string>, existsSync: (path: string) => boolean }` — injectable for testing (QR-01.09).
2. Create `server/src/bridge/event-writer.ts`:
   - Export `appendEvent(filePath: string, event: ShipwrightEvent, deps?: WriterDeps): Promise<void>`.
   - Use `proper-lockfile` to acquire a lock on the file before appending.
   - Serialize event as JSON, append with trailing newline.
   - Release lock in a `finally` block.
   - `WriterDeps` interface: `{ appendFile: (path: string, data: string) => Promise<void>, lock: (path: string) => Promise<() => Promise<void>> }`.
   - Export `emitTaskCreatedEvent(filePath: string, taskId: string, projectId: string, description: string, intent?: string, priority?: string): Promise<ShipwrightEvent>` — constructs a `task_created` event with `timestamp: new Date().toISOString()`, `source: "webui"`, then calls `appendEvent()` (FR-01.18).
3. Create `server/src/core/event-store.ts`:
   - Class `EventStore` with:
     - `private events: Map<string, ShipwrightEvent[]>` — keyed by projectId.
     - `private taskStates: Map<string, TaskStateEntry>` — keyed by taskId. `TaskStateEntry` holds derived status, current phase, description, timestamps.
     - `replayProject(projectId: string, events: ShipwrightEvent[]): void` — processes events in order:
       - `task_created` → create new task state entry with status `pending`.
       - `phase_started` → update task's current phase, mark task as `running`.
       - `phase_completed` → apply deduplication logic (FR-01.17): if another `phase_completed` for same `task_id` + `phase` exists within 60s window, keep the one with a `detail` field, discard the other. Update pipeline phase status to `completed`.
       - `work_completed` → mark task as `done`.
       - `work_failed` → mark task as `failed`.
       - `task_cancelled` → mark task as `cancelled`.
     - `detectOrphans(): Task[]` — scan all task states: any task with status `pending` or `running` that has a `task_created` event but no `work_completed` / `work_failed` event and no active OS process is marked as `orphaned` (FR-01.16).
     - `getTasksForProject(projectId: string): Task[]` — return derived task list.
     - `getPipelineState(projectId: string): PipelinePhase[]` — return per-phase status derived from events.
     - `addEvent(projectId: string, event: ShipwrightEvent): void` — incrementally update state without full replay.
   - Phase deduplication implementation detail (FR-01.17): maintain a `Map<string, ShipwrightEvent>` keyed by `${task_id}:${phase}`. When a second `phase_completed` arrives for the same key, compare timestamps. If within 60 seconds, keep the event that has a truthy `detail` field. If both have `detail`, keep the later one.

**Test Strategy:**
- Unit (event-reader):
  - Valid JSONL with 3 events → returns 3 parsed events.
  - JSONL with 1 corrupt line in the middle → returns 2 events, skips corrupt line.
  - Empty file → returns empty array.
  - File does not exist → returns empty array (no throw).
  - Line with valid JSON but missing `type` field → skipped.
- Unit (event-writer):
  - Appends event with trailing newline.
  - Lock is acquired before write and released after.
  - `emitTaskCreatedEvent` produces correct event shape with all fields.
- Unit (event-store):
  - Replay with task_created + work_completed → task status is `done`.
  - Replay with task_created only → task status is `pending` (orphan candidate).
  - Replay with two phase_completed for same phase within 60s → one with detail is kept.
  - Replay with two phase_completed for same phase >60s apart → both kept.
  - `detectOrphans()` returns tasks with `task_created` but no completion event.
  - `addEvent()` incrementally updates state correctly.
  - Pipeline state derived correctly: 7 phases with correct statuses.

---

### Section 04: Task Manager — Kanban Status Derivation
**Goal:** Implement the logic that maps pipeline phases to Kanban board columns, supporting both the default mapping and per-project custom mappings. The task manager sits on top of the event store and enriches task objects with their derived Kanban status.

**FRs:** FR-01.44, FR-01.45, FR-01.46

**Files:**
- `server/src/core/task-manager.ts` — Kanban status derivation, phase-to-status mapping
- `server/src/core/task-manager.test.ts` — unit tests

**Implementation Steps:**
1. Create `server/src/core/task-manager.ts`:
   - Export `DEFAULT_PHASE_TO_STATUS_MAPPING` as a `PhaseToStatusMapping`:
     ```
     project → backlog
     design  → backlog
     plan    → backlog
     build   → in_progress
     test    → in_review
     deploy  → done
     changelog → done
     done    → done
     ```
   - Export `deriveKanbanStatus(task: { currentPhase?: string; status: TaskStatus }, mapping: PhaseToStatusMapping): KanbanStatus`:
     - If `task.status` is `done` → return `done`.
     - If `task.status` is `failed` → return `failed`.
     - If `task.status` is `cancelled` → return `cancelled`.
     - If `task.status` is `orphaned` → return `backlog` (orphans surface in backlog for user action).
     - If `task.currentPhase` exists and mapping has an entry → return mapped status.
     - Fallback → `backlog`.
   - Export class `TaskManager`:
     - Constructor takes `EventStore` dependency.
     - `getTasksWithKanban(projectId: string, customMapping?: PhaseToStatusMapping): Task[]` — retrieves tasks from event store, applies Kanban status derivation using custom mapping (if provided) with fallback to default mapping for unmapped phases (FR-01.46).
     - `getTaskById(projectId: string, taskId: string): Task | undefined`.
     - `getTasksByStatus(projectId: string, kanbanStatus: KanbanStatus): Task[]` — filter tasks by Kanban column.
     - `resolveMapping(projectMapping?: PhaseToStatusMapping): PhaseToStatusMapping` — merges custom mapping over default, so unmapped phases fall through to defaults.

**Test Strategy:**
- Unit:
  - `deriveKanbanStatus` with phase `build` and default mapping → `in_progress`.
  - `deriveKanbanStatus` with phase `test` and default mapping → `in_review`.
  - `deriveKanbanStatus` with no phase and status `pending` → `backlog`.
  - `deriveKanbanStatus` with status `done` regardless of phase → `done`.
  - `deriveKanbanStatus` with status `failed` → `failed`.
  - `deriveKanbanStatus` with status `orphaned` → `backlog`.
  - Custom mapping overrides default for `build` → custom value used.
  - Custom mapping missing `test` → default fallback used for `test`.
  - `resolveMapping` merges correctly: custom keys override, default keys fill gaps.
  - `getTasksWithKanban` returns tasks with `kanbanStatus` field populated.
  - `getTasksByStatus` filters correctly.

---

### Section 05: Claude CLI Adapter
**Goal:** Implement the adapter that spawns Claude CLI as a child process with proper flags, parses the NDJSON output stream in real-time, manages sessions (new vs. resume), delivers stdin input, and tracks process lifecycle states.

**FRs:** FR-01.07, FR-01.08, FR-01.09, FR-01.10, FR-01.11, FR-01.12, FR-01.13

**Files:**
- `server/src/core/claude-adapter.ts` — Claude CLI spawn, NDJSON stream parser, session management
- `server/src/core/ndjson-parser.ts` — standalone NDJSON line parser (pure function)
- `server/src/core/claude-adapter.test.ts` — unit tests
- `server/src/core/ndjson-parser.test.ts` — unit tests

**Implementation Steps:**
1. Create `server/src/core/ndjson-parser.ts`:
   - Export `parseNdjsonLine(line: string): NdjsonMessage | null`:
     - Trim the line. If empty, return null.
     - Try `JSON.parse(line)`. If fails, log warning and return null (FR-01.13).
     - Validate result has a `type` field (string). If missing, return null.
     - Return typed `NdjsonMessage`.
   - Export `isAskUserQuestion(msg: NdjsonMessage): boolean` — returns true when `msg.type === "tool_use"` and `msg.tool_name === "AskUserQuestion"` (or check `msg.message?.tool_name`).
2. Create `server/src/core/claude-adapter.ts`:
   - Export `ProcessState` as const union: `"spawning" | "running" | "exited"`.
   - Export interface `ClaudeProcess`: `pid: number`, `taskId: string`, `projectId: string`, `sessionId: string`, `state: ProcessState`, `exitCode?: number`, `process: ChildProcess`.
   - Export interface `SpawnDeps`: `{ spawn: typeof child_process.spawn }` — injectable (QR-01.09).
   - Export interface `ClaudeSpawnOptions`: `projectDir: string`, `projectId: string`, `taskId: string`, `sessionId?: string`, `resume: boolean`, `pluginDirs: string[]`, `prompt: string`, `claudeCliPath?: string`.
   - Export class `ClaudeAdapter`:
     - Constructor takes `SpawnDeps` and an `onEvent: (taskId: string, msg: NdjsonMessage) => void` callback (for SSE forwarding, FR-01.12).
     - `spawn(options: ClaudeSpawnOptions): ClaudeProcess`:
       - Build args array: `["--output-format", "stream-json"]`.
       - For each `pluginDir` in options: add `["--plugin-dir", dir]`.
       - If `options.resume` is true: add `["--continue"]`. Else: add `["--session-id", options.sessionId]`.
       - Add `["-p", options.prompt]` for the initial prompt.
       - Spawn `claude` (or `options.claudeCliPath`) with args, `cwd: options.projectDir`, `stdio: ["pipe", "pipe", "pipe"]`.
       - Set state to `spawning`, transition to `running` on first stdout data.
       - Attach stdout line-by-line reader (split on `\n`), parse each line with `parseNdjsonLine()`, call `onEvent` callback for valid messages (FR-01.08, FR-01.12).
       - Attach stderr handler — log errors with context (QR-01.08).
       - Attach `close` handler — update state to `exited`, capture exit code (FR-01.11).
       - Return `ClaudeProcess` object.
     - `sendStdin(process: ClaudeProcess, input: string): void`:
       - If `process.state === "exited"`, throw `AppError(400, "Process has exited")`.
       - Write `input + "\n"` to `process.process.stdin` (FR-01.10).
     - `terminate(process: ClaudeProcess): void`:
       - Send SIGTERM, set state to `exited`.
     - Private `createLineReader(stream: Readable): AsyncIterable<string>` — splits stream on newline boundaries, handles partial chunks.

**Test Strategy:**
- Unit (ndjson-parser):
  - Valid assistant message JSON → parsed correctly.
  - Valid tool_use JSON with AskUserQuestion → `isAskUserQuestion` returns true.
  - Malformed JSON string → returns null (no throw).
  - Empty line → returns null.
  - JSON without `type` field → returns null.
  - Performance: parse 1000 lines in <50ms (QR-01.03).
- Unit (claude-adapter):
  - Mock `spawn` returns a fake ChildProcess with piped streams.
  - Write NDJSON lines to fake stdout → `onEvent` callback called with parsed messages.
  - Process exit → state becomes `exited`, exit code captured.
  - `sendStdin` writes to stdin pipe.
  - `sendStdin` on exited process → throws error.
  - Malformed line in stdout stream → skipped, next lines still parsed.
  - Args construction: verify `--output-format`, `--plugin-dir`, `--session-id` / `--continue` flags are correct for new vs. resume scenarios.

---

### Section 06: Process Governor — Concurrency & Lifecycle
**Goal:** Implement the concurrency semaphore that limits parallel Claude processes, PID tracking for orphan detection, orphan cleanup on startup, the heartbeat scheduler, and the task queue for overflow.

**FRs:** FR-01.19, FR-01.20, FR-01.21, FR-01.22, FR-01.23

**Files:**
- `server/src/core/process-governor.ts` — semaphore, PID tracking, queue, orphan cleanup
- `server/src/core/heartbeat.ts` — node-cron scheduler for health checks
- `server/src/core/process-governor.test.ts` — unit tests
- `server/src/core/heartbeat.test.ts` — unit tests

**Implementation Steps:**
1. Create `server/src/core/process-governor.ts`:
   - Export interface `GovernorDeps`: `{ isProcessRunning: (pid: number) => boolean, kill: (pid: number, signal?: string) => void }` — injectable for testing.
   - Export class `ProcessGovernor`:
     - Constructor takes `maxConcurrent: number`, `ClaudeAdapter` instance, `GovernorDeps`.
     - `private activeProcesses: Map<string, ClaudeProcess>` — keyed by taskId.
     - `private queue: ClaudeSpawnOptions[]` — overflow queue (FR-01.23).
     - `private pidFile: string` — path to `~/.shipwright-webui/pids.json` for PID persistence across restarts.
     - `acquire(options: ClaudeSpawnOptions): Promise<ClaudeProcess | "queued">`:
       - If `activeProcesses.size < maxConcurrent`: spawn via adapter, track PID (FR-01.20), persist to PID file, return process.
       - Else: push to queue, return `"queued"` (FR-01.23).
     - `release(taskId: string): void`:
       - Remove from `activeProcesses`, remove PID from tracking.
       - If queue is non-empty: dequeue first item, call `acquire()` (FR-01.23).
     - `getProcess(taskId: string): ClaudeProcess | undefined`.
     - `getAllActive(): ClaudeProcess[]`.
     - `cleanupOrphans(): Promise<{ killed: number; stale: number }>` (FR-01.21):
       - Read PID file from previous run.
       - For each tracked PID: check if process is running via `deps.isProcessRunning(pid)`.
       - If running but not in current `activeProcesses` → kill it (orphan).
       - If not running → remove from PID file (stale).
       - Return counts for logging.
     - `persistPids(): void` — write current active PIDs to PID file.
     - `getQueueLength(): number`.
   - Helper `isProcessRunning(pid: number): boolean` — default implementation using `process.kill(pid, 0)` in try/catch.
2. Create `server/src/core/heartbeat.ts`:
   - Export class `HeartbeatScheduler`:
     - Constructor takes `ProcessGovernor`, interval string (default `"*/30 * * * * *"` for 30s via node-cron).
     - `start(): void` — schedule cron job that:
       - Iterates all active processes from governor.
       - For each: check if process is still alive via `deps.isProcessRunning(pid)`.
       - If dead: mark task as failed, call `governor.release(taskId)` — this also triggers queue drain (FR-01.22).
       - Log health check results.
     - `stop(): void` — cancel cron job.
   - The heartbeat is the mechanism that detects hung/crashed processes between explicit exit events.

**Test Strategy:**
- Unit (process-governor):
  - Spawn 3 processes with `maxConcurrent: 3` → all active, none queued.
  - Spawn 4th process → returns `"queued"`.
  - Release one process → queued task auto-starts.
  - `cleanupOrphans` with 2 stale PIDs and 1 running orphan → kills 1, removes 2 stale.
  - PID tracking: spawn adds PID, release removes it.
  - `persistPids` writes correct JSON file.
- Unit (heartbeat):
  - Mock cron to fire callback immediately.
  - Dead process detected → `release()` called, task marked failed.
  - Healthy processes → no action taken.
  - `stop()` cancels the cron job.

---

### Section 07: Multi-Project Registry & File Watcher
**Goal:** Implement the project registry that persists to `~/.shipwright-webui/projects.json`, project discovery by scanning for Shipwright config files, and the chokidar file watcher that monitors event and config files per project.

**FRs:** FR-01.24, FR-01.25, FR-01.26, FR-01.33, FR-01.34, FR-01.35

**Files:**
- `server/src/core/project-manager.ts` — project CRUD, discovery, registry persistence
- `server/src/bridge/config-reader.ts` — reads shipwright_*_config.json files
- `server/src/core/file-watcher.ts` — chokidar watcher setup, debounce, SSE trigger
- `server/src/core/project-manager.test.ts` — unit tests
- `server/src/bridge/config-reader.test.ts` — unit tests
- `server/src/core/file-watcher.test.ts` — unit tests

**Implementation Steps:**
1. Create `server/src/core/project-manager.ts`:
   - Export interface `ProjectManagerDeps`: `{ readFile, writeFile, existsSync, mkdirSync, readdirSync }` — injectable FS operations.
   - Export class `ProjectManager`:
     - `private registryPath: string` — `~/.shipwright-webui/projects.json`.
     - `private projects: Map<string, Project>` — in-memory cache.
     - `load(): Promise<void>` — read registry file, parse JSON, populate map. If file doesn't exist, create directory and initialize empty registry (FR-01.24).
     - `getAll(): Project[]` — return all projects sorted by `lastActive` descending.
     - `getById(id: string): Project | undefined`.
     - `create(data: Omit<Project, "id" | "createdAt" | "lastActive">): Project`:
       - Validate `path` exists on disk.
       - Generate UUID, set `createdAt` and `lastActive` to now.
       - Add to map, persist to file (FR-01.24, FR-01.25).
     - `update(id: string, patch: Partial<Project>): Project`:
       - Merge patch into existing project, update `lastActive`.
       - Persist to file.
     - `delete(id: string): void` — remove from map, persist.
     - `touchLastActive(id: string): void` — update `lastActive` timestamp (FR-01.25).
     - `discover(directory: string): Project[]` (FR-01.26):
       - Scan `directory` for subdirectories containing `shipwright_run_config.json` or `shipwright_project_config.json`.
       - For each found: create a Project entry with name derived from directory name.
       - Return newly discovered projects (not yet added to registry — caller decides).
     - `private persist(): Promise<void>` — serialize map to JSON and write to registry file.
2. Create `server/src/bridge/config-reader.ts`:
   - Export `readConfigFile<T>(filePath: string, deps?: FileSystemDeps): Promise<T | null>`:
     - Read and parse JSON. If file doesn't exist, return null (graceful, FR-01.33).
   - Export `readAllConfigs(projectDir: string, deps?: FileSystemDeps): Promise<Record<string, unknown>>`:
     - Read known config files: `shipwright_run_config.json`, `shipwright_project_config.json`, `shipwright_plan_config.json`, `shipwright_build_config.json`, `shipwright_test_config.json`, `shipwright_deploy_config.json`, `shipwright_changelog_config.json`.
     - Return a map of config name → parsed content (null entries omitted).
   - Export `derivePipelineFromConfigs(configs: Record<string, unknown>): PipelinePhase[]`:
     - For each of the 7 phases, check if a corresponding config file exists.
     - If config exists and has completion markers → `completed`.
     - If config exists but no completion → `running` (or `pending` depending on phase order).
     - If no config → `pending`.
     - This provides pipeline state even without events (standalone project without orchestrator, per FR-01.33 acceptance criteria).
3. Create `server/src/core/file-watcher.ts`:
   - Export interface `FileWatcherDeps`: `{ watch: typeof chokidar.watch }` — injectable.
   - Export class `FileWatcher`:
     - `private watchers: Map<string, FSWatcher>` — keyed by projectId.
     - `watchProject(projectId: string, projectDir: string, onChange: (type: string, path: string) => void): void`:
       - Watch `${projectDir}/shipwright_events.jsonl` and `${projectDir}/shipwright_*_config.json` using chokidar.
       - Debounce events: collect changes within 300ms window, then fire `onChange` once with the most recent change type (FR-01.35).
       - `onChange` receives the change type (`"event"` or `"config"`) so the caller knows what to re-read.
     - `unwatchProject(projectId: string): void` — close watcher, remove from map.
     - `unwatchAll(): void` — close all watchers (used during shutdown).
   - Debounce implementation: use a per-project `setTimeout` that resets on each new change. After 300ms of quiet, fire the callback.

**Test Strategy:**
- Unit (project-manager):
  - `create()` assigns UUID, sets timestamps, persists to file.
  - `getAll()` returns projects sorted by `lastActive`.
  - `update()` merges patch and updates `lastActive`.
  - `delete()` removes project from list and file.
  - `load()` with non-existent file creates empty registry.
  - `load()` with existing file populates in-memory map.
  - `discover()` finds directories with Shipwright config files.
  - `discover()` ignores directories without config files.
- Unit (config-reader):
  - Valid config file → parsed JSON returned.
  - Missing config file → null returned (no throw).
  - `readAllConfigs` reads all 7 config types, omits missing ones.
  - `derivePipelineFromConfigs` with run_config + build_config → correct phase statuses.
  - Pipeline derivation without run_config (standalone) → still produces valid phases.
- Unit (file-watcher):
  - Mock chokidar: emit `change` on events file → `onChange` called with `"event"`.
  - Two rapid changes within 300ms → `onChange` called once (debounce).
  - `unwatchProject` closes the watcher.
  - `unwatchAll` closes all watchers.

---

### Section 08: Inbox Manager & Chat Store
**Goal:** Implement the inbox aggregation system that collects AskUserQuestion events from all running Claude subprocesses, delivers user answers via stdin, and provides SSE notifications. Also implement the chat store that persists and replays NDJSON messages per task.

**FRs:** FR-01.27, FR-01.28, FR-01.29, FR-01.30, FR-01.31, FR-01.32

**Files:**
- `server/src/core/inbox-manager.ts` — inbox aggregation, answer delivery, SSE notification
- `server/src/core/chat-store.ts` — chat history persistence and replay
- `server/src/core/inbox-manager.test.ts` — unit tests
- `server/src/core/chat-store.test.ts` — unit tests

**Implementation Steps:**
1. Create `server/src/core/inbox-manager.ts`:
   - Export class `InboxManager`:
     - Constructor takes `ProcessGovernor` (to find the right process for stdin delivery) and `onNotify: (item: InboxItem) => void` callback (for SSE, FR-01.30).
     - `private items: Map<string, InboxItem>` — keyed by item ID.
     - `addQuestion(projectId: string, taskId: string, question: string, context?: string, options?: string[]): InboxItem` (FR-01.27, FR-01.28):
       - Generate UUID for item ID.
       - Create `InboxItem` with status `pending`, `createdAt` timestamp.
       - Add to map.
       - Call `onNotify(item)` to trigger SSE event (FR-01.30).
       - Return item.
     - `answer(itemId: string, answerText: string): InboxItem` (FR-01.29):
       - Find item by ID. If not found, throw `AppError(404)`.
       - If already answered, throw `AppError(400, "Already answered")`.
       - Get the Claude process from governor via `item.taskId`.
       - Call `adapter.sendStdin(process, answerText)` to deliver to subprocess.
       - Update item: set `answer`, `status: "answered"`, `answeredAt`.
       - Return updated item.
     - `getAll(filter?: { status?: InboxStatus }): InboxItem[]` — return items, optionally filtered by status.
     - `getByProject(projectId: string): InboxItem[]`.
     - This class is the callback target for `ClaudeAdapter.onEvent` when `isAskUserQuestion(msg)` is true. The route handler or a coordinator wires this up.
2. Create `server/src/core/chat-store.ts`:
   - Export interface `ChatStoreDeps`: `{ readFile, appendFile, existsSync, mkdirSync }`.
   - Export class `ChatStore`:
     - `private basePath(projectDir: string): string` — returns `${projectDir}/.shipwright-webui/chat-history/`.
     - `append(projectDir: string, taskId: string, message: ChatMessage): Promise<void>` (FR-01.31):
       - Ensure chat-history directory exists (create if needed).
       - Append JSON line to `${basePath}/${taskId}.jsonl`.
     - `load(projectDir: string, taskId: string): Promise<ChatMessage[]>` (FR-01.32):
       - Read `${basePath}/${taskId}.jsonl`.
       - Parse each line (tolerant — skip malformed, same pattern as event reader).
       - Return messages sorted by `timestamp`.
     - `exists(projectDir: string, taskId: string): boolean` — check if chat file exists.
   - The adapter's `onEvent` callback should call `chatStore.append()` for every parsed NDJSON message, converting `NdjsonMessage` to `ChatMessage` with a generated ID and timestamp.

**Test Strategy:**
- Unit (inbox-manager):
  - `addQuestion` creates item with correct fields, calls `onNotify`.
  - `answer` delivers text to process stdin and marks item answered.
  - `answer` on non-existent item → 404 error.
  - `answer` on already-answered item → 400 error.
  - `getAll()` returns all items. `getAll({ status: "pending" })` filters.
  - `getByProject` filters by project ID.
- Unit (chat-store):
  - `append` creates directory if missing, appends JSON line.
  - `load` reads and parses all messages, sorted by timestamp.
  - `load` on missing file → returns empty array.
  - `load` with corrupt line → skips it, returns valid messages.
  - `exists` returns true when file exists, false otherwise.

---

### Section 09: SSE Manager — Real-Time Event Streaming
**Goal:** Implement the SSE endpoint that streams real-time events to connected browser clients, manages multiple concurrent connections, handles client disconnections, and provides a broadcast API for other modules to push events.

**FRs:** FR-01.04, FR-01.05, FR-01.06

**Files:**
- `server/src/core/sse-manager.ts` — SSE connection management, broadcast API
- `server/src/routes/sse.ts` — Hono route for GET /api/events
- `server/src/core/sse-manager.test.ts` — unit tests
- `server/src/routes/sse.test.ts` — integration tests

**Implementation Steps:**
1. Create `server/src/core/sse-manager.ts`:
   - Export class `SSEManager`:
     - `private clients: Map<string, SSEClient>` — keyed by client ID. `SSEClient` holds `id: string`, `controller: ReadableStreamDefaultController`, `connectedAt: string`.
     - `addClient(id: string, controller: ReadableStreamDefaultController): void` (FR-01.06):
       - Store client in map.
       - Log connection with client ID.
     - `removeClient(id: string): void` (FR-01.06):
       - Remove from map.
       - Log disconnection.
     - `broadcast(event: SSEEvent): void` (FR-01.05):
       - For each client: encode event as SSE format (`data: ${JSON.stringify(event)}\n\n`).
       - Write to client's controller. If write fails (client disconnected), call `removeClient`.
     - `broadcastToProject(projectId: string, event: SSEEvent): void`:
       - Broadcast to all clients (local single-user app — all clients see all events). In future, could filter by project subscription.
     - `getClientCount(): number`.
     - `closeAll(): void` — close all client controllers (used during shutdown).
   - SSE format per event: `event: ${event.type}\ndata: ${JSON.stringify(event.payload)}\n\n`.
2. Create `server/src/routes/sse.ts`:
   - Export a Hono route handler for `GET /api/events`:
     - Use Hono's `streamSSE()` helper from `hono/streaming`.
     - On connection: generate client ID, create a mechanism to push events to this client via the SSE manager.
     - Set headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`.
     - Send initial `connected` event with timestamp (FR-01.04).
     - On client disconnect (abort signal): call `sseManager.removeClient(id)`.
   - Alternative approach if `streamSSE()` is not flexible enough: use `c.body(readableStream)` with a `ReadableStream` and manual SSE formatting.

**Test Strategy:**
- Unit (sse-manager):
  - `addClient` increases client count.
  - `removeClient` decreases client count.
  - `broadcast` writes SSE-formatted data to all client controllers.
  - `broadcast` auto-removes client if write fails.
  - `closeAll` empties the client map.
  - SSE format: verify `event:` and `data:` lines with proper `\n\n` termination.
- Integration (sse route):
  - `GET /api/events` returns status 200 with `Content-Type: text/event-stream`.
  - Response is a readable stream (streaming response).

---

### Section 10: REST API Routes
**Goal:** Wire all core modules together through Hono REST API routes. Each route file imports the relevant manager/store, validates input, calls business logic, and returns JSON responses following the `{ data: T }` / `{ error: string }` convention. This section also implements the docs file tree route, classify shell-out route, settings persistence, and task status update route.

**FRs:** FR-01.36, FR-01.37, FR-01.38, FR-01.39, FR-01.40, FR-01.41, FR-01.42, FR-01.43, FR-01.47

**Files:**
- `server/src/routes/projects.ts` — project CRUD routes
- `server/src/routes/tasks.ts` — task list and create routes
- `server/src/routes/inbox.ts` — inbox list and answer routes
- `server/src/routes/chat.ts` — chat history and send routes
- `server/src/routes/pipeline.ts` — pipeline status route
- `server/src/routes/docs.ts` — file tree and content route
- `server/src/routes/classify.ts` — intent/complexity classification route
- `server/src/routes/settings.ts` — global settings routes
- `server/src/bridge/doc-index.ts` — file tree builder for docs route
- `server/src/bridge/intent-classifier.ts` — shell-out to classify_intent.py and classify_complexity.py
- `server/src/bridge/pipeline-state.ts` — combined pipeline state from events + configs
- `server/src/index.ts` — updated to mount all routes and initialize all managers
- `server/src/routes/*.test.ts` — integration tests per route file

**Implementation Steps:**
1. Create `server/src/routes/projects.ts` (FR-01.36):
   - `GET /api/projects` → `projectManager.getAll()` → `{ data: Project[] }`.
   - `POST /api/projects` → validate body (name, path required), `projectManager.create(body)` → 201 `{ data: Project }`. Start file watcher for the new project. Trigger event replay for the project.
   - `GET /api/projects/:id` → `projectManager.getById(id)` → `{ data: Project }` or 404.
   - `PATCH /api/projects/:id` → validate body, `projectManager.update(id, body)` → `{ data: Project }` or 404.
   - `DELETE /api/projects/:id` → `projectManager.delete(id)` → 204. Stop file watcher. Broadcast `project:updated` SSE.
2. Create `server/src/routes/tasks.ts` (FR-01.37, FR-01.47):
   - `GET /api/projects/:id/tasks` → `taskManager.getTasksWithKanban(id, project.settings?.phaseToStatusMapping)` → `{ data: Task[] }`.
   - `POST /api/projects/:id/tasks` → validate body (description required), emit `task_created` event via `eventWriter.emitTaskCreatedEvent()`, acquire process from governor, spawn Claude CLI via adapter → 201 `{ data: Task }`. If queued, return 202 `{ data: { taskId, status: "queued" } }`. Fire async classify call after creation (FR-01.42 acceptance criteria).
   - `PATCH /api/projects/:id/tasks/:taskId/status` (FR-01.47):
     - Validate body (`status` required, must be one of `closed`, `cancelled`).
     - Find task. If not found, return 404.
     - Emit corresponding event (`task_cancelled` for cancelled, `work_completed` with manual flag for closed) via event writer.
     - Update in-memory state via event store.
     - Broadcast `task:updated` SSE event.
     - Return `{ data: Task }`.
3. Create `server/src/routes/inbox.ts` (FR-01.38):
   - `GET /api/inbox` → `inboxManager.getAll()` → `{ data: InboxItem[] }`. Optional `?status=pending` query param.
   - `POST /api/inbox/:id/answer` → validate body (answer required), `inboxManager.answer(id, body.answer)` → `{ data: InboxItem }`. Broadcast `inbox:answered` SSE.
4. Create `server/src/routes/chat.ts` (FR-01.39):
   - `GET /api/projects/:id/chat/:taskId` → `chatStore.load(project.path, taskId)` → `{ data: ChatMessage[] }`.
   - `POST /api/projects/:id/chat` → validate body (taskId, message required). Find active process. Send message via `adapter.sendStdin()`. Append user message to chat store. Return `{ data: ChatMessage }`.
5. Create `server/src/bridge/pipeline-state.ts`:
   - Export `getPipelineState(projectId: string, eventStore: EventStore, configReader: typeof readAllConfigs, projectDir: string): Promise<PipelineRun>`:
     - Get phase statuses from events via `eventStore.getPipelineState(projectId)`.
     - Get phase statuses from configs via `configReader.derivePipelineFromConfigs()`.
     - Merge: events take priority (they are more granular), configs fill gaps (standalone projects).
     - Return `PipelineRun` with all 7 phases.
6. Create `server/src/routes/pipeline.ts` (FR-01.40):
   - `GET /api/projects/:id/pipeline` → `getPipelineState(id, eventStore, readAllConfigs, project.path)` → `{ data: PipelineRun }`.
7. Create `server/src/bridge/doc-index.ts`:
   - Export `buildFileTree(projectDir: string, deps?: FileSystemDeps): FileTreeNode[]`:
     - Recursively scan project directory.
     - Exclude: `node_modules`, `.git`, `__pycache__`, `.venv`.
     - Return tree of `{ name: string, path: string, type: "file" | "directory", children?: FileTreeNode[] }`.
   - Export `readFileContent(filePath: string, projectDir: string, deps?: FileSystemDeps): Promise<string>`:
     - Validate `filePath` is within `projectDir` (path traversal prevention).
     - Read and return file content as UTF-8 string.
8. Create `server/src/routes/docs.ts` (FR-01.41):
   - `GET /api/projects/:id/docs` → `buildFileTree(project.path)` → `{ data: FileTreeNode[] }`.
   - `GET /api/projects/:id/docs?file=path/to/file` → `readFileContent(file, project.path)` → `{ data: { content: string, path: string } }`.
9. Create `server/src/bridge/intent-classifier.ts`:
   - Export `classifyIntent(description: string, projectDir: string): Promise<{ intent: string; affected_frs?: string[] }>`:
     - Spawn `uv run classify_intent.py` with description as stdin or argument.
     - Parse JSON output.
     - If script not found or fails, return `{ intent: "unknown" }` (graceful degradation).
   - Export `classifyComplexity(description: string, projectDir: string): Promise<{ complexity: string }>`:
     - Spawn `uv run classify_complexity.py`.
     - Parse JSON output.
     - Graceful fallback to `{ complexity: "unknown" }`.
10. Create `server/src/routes/classify.ts` (FR-01.42):
    - `POST /api/projects/:id/classify` → validate body (description required). Run both classifiers in parallel via `Promise.all()`. Return `{ data: { intent, complexity, affected_frs } }`.
11. Create `server/src/routes/settings.ts` (FR-01.43):
    - Settings stored in `~/.shipwright-webui/settings.json`.
    - `GET /api/settings` → read and return settings file → `{ data: GlobalSettings }`. If file missing, return defaults.
    - `PUT /api/settings` → validate body, merge with existing settings, write to file → `{ data: GlobalSettings }`.
12. Update `server/src/index.ts` — the main entry point:
    - Initialize all managers in dependency order:
      1. Load config.
      2. Create `EventStore`.
      3. Create `SSEManager`.
      4. Create `ClaudeAdapter` with `onEvent` callback that: appends to chat store, checks for AskUserQuestion → inbox, forwards to SSE.
      5. Create `ProcessGovernor` with adapter.
      6. Create `HeartbeatScheduler` with governor.
      7. Create `ProjectManager`, load registry.
      8. Create `TaskManager` with event store.
      9. Create `InboxManager` with governor and SSE notify callback.
      10. Create `ChatStore`.
      11. Create `FileWatcher`.
    - For each registered project: replay events, start file watcher.
    - Run `governor.cleanupOrphans()`.
    - Start heartbeat scheduler.
    - Mount all route groups on the Hono app.
    - Register graceful shutdown handler (`process.on("SIGTERM", ...)` and `process.on("SIGINT", ...)`):
      - Stop heartbeat.
      - Unwatch all files.
      - Close all SSE connections.
      - Terminate all active Claude processes.
      - Persist governor PIDs.
      - Exit.

**Test Strategy:**
- Integration (per route file — use Hono's `app.request()` test helper):
  - **projects.ts:**
    - `GET /api/projects` returns 200 with array.
    - `POST /api/projects` with valid body returns 201 with project.
    - `POST /api/projects` with missing name returns 400.
    - `PATCH /api/projects/:id` returns 200 with updated project.
    - `DELETE /api/projects/:id` returns 204.
    - `GET /api/projects/:id` for non-existent project returns 404.
  - **tasks.ts:**
    - `GET /api/projects/:id/tasks` returns tasks with kanbanStatus.
    - `POST /api/projects/:id/tasks` returns 201 and starts process (mock adapter).
    - `POST /api/projects/:id/tasks` when governor is full returns 202 (queued).
    - `PATCH /api/projects/:id/tasks/:taskId/status` with `cancelled` returns updated task.
    - `PATCH /api/projects/:id/tasks/:taskId/status` for non-existent task returns 404.
  - **inbox.ts:**
    - `GET /api/inbox` returns all items.
    - `GET /api/inbox?status=pending` returns only pending items.
    - `POST /api/inbox/:id/answer` returns answered item.
    - `POST /api/inbox/:id/answer` for already-answered item returns 400.
  - **chat.ts:**
    - `GET /api/projects/:id/chat/:taskId` returns message array.
    - `POST /api/projects/:id/chat` sends message and returns it.
  - **pipeline.ts:**
    - `GET /api/projects/:id/pipeline` returns 7 phases with statuses.
  - **docs.ts:**
    - `GET /api/projects/:id/docs` returns file tree.
    - `GET /api/projects/:id/docs?file=...` returns file content.
    - Path traversal attempt returns 400.
  - **classify.ts:**
    - `POST /api/projects/:id/classify` returns intent and complexity (mock spawn).
    - Classifier failure returns graceful fallback.
  - **settings.ts:**
    - `GET /api/settings` returns defaults when no file exists.
    - `PUT /api/settings` persists and returns updated settings.

---

## Cross-Cutting Concerns

### Error Handling (QR-01.07)
- All routes use Hono's error handler middleware from Section 01.
- Business logic throws `AppError(statusCode, message, detail?)` — caught by middleware and returned as `{ error, detail }`.
- Unexpected errors → 500 with generic message, full error logged server-side.

### Structured Logging (QR-01.08)
- Every log line includes: `timestamp`, `level`, `message`, plus contextual fields (`projectId`, `taskId`, `pid`) when available.
- Use `console.log(JSON.stringify({ ... }))` for machine-parseable logs.
- Log at key lifecycle points: process spawn/exit, event replay start/end, file watcher change, SSE connect/disconnect, inbox question/answer.

### File Locking (C-01.05)
- All JSONL append operations go through `event-writer.ts` which uses `proper-lockfile`.
- Lock is acquired before read-append and released in `finally`.
- Lock timeout: 5 seconds. If lock cannot be acquired, retry once after 500ms, then throw.

### Graceful Shutdown
- `SIGTERM` and `SIGINT` handlers in `index.ts` (Section 10).
- Shutdown sequence: stop heartbeat → unwatch files → close SSE → terminate processes → persist PIDs → exit.
- Each step has a 5-second timeout to prevent hanging shutdown.

### Dependency Injection (QR-01.09)
- Every module that does I/O accepts a `Deps` interface parameter with default implementations.
- Tests inject mocks/stubs for: `fs.readFile`, `fs.writeFile`, `child_process.spawn`, `chokidar.watch`, `process.kill`.
- No global singletons in module scope — all instances created in `index.ts` and passed to consumers.

### Performance Targets
- Event replay: <2s for 1000 events (QR-01.01). Benchmark in event-store tests.
- SSE delivery: <200ms from trigger to client (QR-01.02). Verify by timestamp comparison in integration tests.
- NDJSON parsing: <50ms per message (QR-01.03). Micro-benchmark in parser tests.
