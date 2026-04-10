# Backend Core & Claude Adapter

> Split 01 of 03 | Source: Spec/plan-shipwright-webui.md

## 1. Purpose & Scope

This split establishes the complete server-side foundation for the Shipwright Command Center: a Hono-based HTTP server with SSE streaming, Claude CLI subprocess management, event-sourced state reconstruction, process governance, and all REST API routes. The primary UI consumer is a Kanban board that visualizes tasks as cards flowing through status columns (Backlog, In Progress, In Review, Done), with task status derived from pipeline events. This split provides the API contracts that Split 02 (UI Shell) and Split 03 (Features) consume.

**In Scope:**
- Hono server with middleware, CORS, static file serving, and SSE streaming
- Claude CLI Adapter: spawn, NDJSON stream parsing, session management, stdin delivery
- Event system: read shipwright_events.jsonl, replay into in-memory state, task lifecycle tracking
- Process Governor: concurrency semaphore, PID tracking, orphan cleanup, heartbeat
- SSE Manager: server-sent events endpoint for real-time frontend updates
- Config/Event Bridge: read shipwright_*_config.json and shipwright_events.jsonl from project dirs
- File Watcher: chokidar on event and config files, trigger SSE updates
- Multi-Project Registry: CRUD for projects in ~/.shipwright-webui/projects.json
- Inbox Manager: aggregate AskUserQuestion from all projects, deliver answers via stdin
- Chat Store: persist and replay parsed NDJSON messages per task
- All REST API route handlers (projects, tasks, inbox, chat, pipeline, docs, classify, settings)

**Out of Scope:**
- All frontend components, layouts, and UI rendering (Split 02 + 03)
- Smart File Viewer renderers (Split 03)
- Project Wizard UI (Split 03)
- New Task Dialog UI and Intent Detection Banner UI (Split 03)
- Telegram/Slack webhook integration (future)
- Authentication (local single-user app, no auth required)
- Database (JSONL event log + JSON files only)

## 2. Functional Requirements

### Server & SSE

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.01 | The system SHALL start a Hono HTTP server on a configurable port with a default of 3847. | Must |
| FR-01.02 | The system SHALL serve static files from the frontend build directory at the root path. | Must |
| FR-01.03 | The system SHALL enable CORS for localhost origins during development. | Must |
| FR-01.04 | The system SHALL provide an SSE endpoint at GET /api/events that streams real-time updates to connected clients. | Must |
| FR-01.05 | The system SHALL broadcast project state changes, inbox updates, task status transitions, and process lifecycle events via SSE. | Must |
| FR-01.06 | The system SHOULD support multiple concurrent SSE connections and clean up disconnected clients. | Should |

### Claude CLI Adapter

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.07 | The system SHALL spawn Claude CLI as a child process with --output-format stream-json and --plugin-dir flags for all registered Shipwright plugins. | Must |
| FR-01.08 | The system SHALL parse the NDJSON stream from Claude CLI, handling assistant, tool_use, tool_result, and result message types. | Must |
| FR-01.09 | The system SHALL manage Claude sessions using --session-id for new sessions and --continue for session resumption. | Must |
| FR-01.10 | The system SHALL deliver user input to a running Claude subprocess via stdin when responding to AskUserQuestion prompts. | Must |
| FR-01.11 | The system SHALL track process lifecycle states (spawning, running, exited) and capture the exit code on process termination. | Must |
| FR-01.12 | The system SHALL forward parsed NDJSON events to the SSE Manager for real-time streaming to the frontend. | Must |
| FR-01.13 | The system SHOULD skip malformed NDJSON lines without crashing the stream parser. | Should |

### Event System

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.14 | The system SHALL read shipwright_events.jsonl from each registered project directory using a tolerant reader that skips corrupt or malformed lines. | Must |
| FR-01.15 | The system SHALL reconstruct in-memory task and pipeline state from events on server startup (event replay). | Must |
| FR-01.16 | The system SHALL track task_created events without a matching work_completed event as orphaned tasks. | Must |
| FR-01.17 | The system SHALL deduplicate phase_completed events when both plugin and orchestrator emit them, preferring the event that contains a detail field. | Must |
| FR-01.18 | The system SHALL emit a task_created event (via record_event.py) when a user starts a new task through the API. The event SHALL include fields: description, intent (optional), priority (optional). | Must |

### Task Manager — Kanban Status Derivation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.44 | The system SHALL derive Kanban column status (Backlog / In Progress / In Review / Done) from pipeline events using a configurable phase-to-status mapping. | Must |
| FR-01.45 | The system SHALL support a default phase-to-status mapping: Backlog = (no phases, not yet started), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (no phases, task completion). | Must |
| FR-01.46 | The system SHALL allow per-project custom phase-to-status mappings stored in project settings. | Should |

### Process Governor

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.19 | The system SHALL enforce a configurable semaphore limiting the maximum number of concurrent Claude processes, with a default of 3. | Must |
| FR-01.20 | The system SHALL track PIDs of all spawned Claude processes for orphan detection. | Must |
| FR-01.21 | The system SHALL detect and terminate orphaned Claude processes on server startup by checking tracked PIDs against running OS processes. | Must |
| FR-01.22 | The system SHALL run a heartbeat scheduler at 30-second intervals that checks process health and identifies hung processes. | Must |
| FR-01.23 | The system SHOULD queue tasks that exceed the concurrency limit and start them when a slot becomes available. | Should |

### Multi-Project Registry

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.24 | The system SHALL persist the project registry in ~/.shipwright-webui/projects.json with CRUD operations (create, read, update, delete). | Must |
| FR-01.25 | The system SHALL store per-project metadata including name, directory path, profile, status, and last active timestamp. | Must |
| FR-01.26 | The system SHOULD support project discovery by scanning a directory for shipwright_run_config.json OR shipwright_project_config.json (standalone projects without orchestrator). | Should |

### Inbox Manager

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.27 | The system SHALL aggregate AskUserQuestion events from all active Claude subprocesses into a unified inbox. | Must |
| FR-01.28 | The system SHALL create inbox items containing question text, context, response options, project_id, and task_id. | Must |
| FR-01.29 | The system SHALL deliver user answers to the correct Claude subprocess via stdin and mark the inbox item as answered. | Must |
| FR-01.30 | The system SHALL emit an SSE notification when a new inbox item is created. | Must |

### Chat Store

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.31 | The system SHALL persist parsed NDJSON messages per task in the project's .shipwright-webui/chat-history/ directory. | Must |
| FR-01.32 | The system SHALL load chat history for a given task to support context switching and chat replay as a chronological message list. | Must |

### Config/Event Bridge & File Watcher

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.33 | The system SHALL read shipwright_*_config.json files from project directories to derive pipeline orchestration state. | Must |
| FR-01.34 | The system SHALL watch config files and shipwright_events.jsonl per project using chokidar and trigger SSE updates on changes. | Must |
| FR-01.35 | The system SHOULD debounce file watcher events to avoid flooding SSE clients during rapid file changes. | Should |

### REST API Routes

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.36 | The system SHALL expose project CRUD routes at GET/POST /api/projects and GET/PATCH/DELETE /api/projects/:id. | Must |
| FR-01.37 | The system SHALL expose task routes at GET/POST /api/projects/:id/tasks for listing tasks and starting new tasks. | Must |
| FR-01.38 | The system SHALL expose inbox routes at GET /api/inbox (global across all projects) and POST /api/inbox/:id/answer for delivering responses. | Must |
| FR-01.39 | The system SHALL expose chat routes at GET /api/projects/:id/chat/:taskId for history retrieval and POST /api/projects/:id/chat for sending messages. | Must |
| FR-01.40 | The system SHALL expose a pipeline status route at GET /api/projects/:id/pipeline returning current phase states derived from events and configs. | Must |
| FR-01.41 | The system SHALL expose a docs route at GET /api/projects/:id/docs returning a file tree and file content from the project directory. | Must |
| FR-01.42 | The system SHALL expose a classify route at POST /api/projects/:id/classify that shells out to classify_intent.py and classify_complexity.py and returns the classification result. The classify endpoint SHALL be called asynchronously after task creation to enrich the Kanban card with intent and complexity metadata. | Must |
| FR-01.47 | The system SHALL expose a task status route at PATCH /api/projects/:id/tasks/:taskId/status for manual status changes (e.g., close, cancel). | Must |
| FR-01.43 | The system SHALL expose settings routes at GET/PUT /api/settings for global WebUI configuration. | Must |

### Acceptance Criteria

**FR-01.01: Hono Server Startup**
- [ ] Server starts on port 3847 by default
- [ ] Port is configurable via settings.json or environment variable
- [ ] Server logs the listening address on startup

**FR-01.04: SSE Endpoint**
- [ ] GET /api/events returns Content-Type: text/event-stream
- [ ] Events are formatted as valid SSE (data: + newline)
- [ ] Connection stays open and receives subsequent events

**FR-01.07: Claude CLI Spawn**
- [ ] Claude CLI is spawned with --output-format stream-json
- [ ] All Shipwright plugin directories are passed via --plugin-dir flags
- [ ] The working directory is set to the project directory

**FR-01.08: NDJSON Stream Parsing**
- [ ] assistant messages are parsed and forwarded
- [ ] tool_use messages are parsed with name and input
- [ ] tool_result messages are parsed with output
- [ ] result messages are parsed and trigger process completion handling

**FR-01.09: Session Management**
- [ ] New tasks generate a unique session ID and pass --session-id
- [ ] Resumed tasks use --continue to continue the existing session
- [ ] Session IDs are persisted for task-to-session mapping

**FR-01.10: Stdin Delivery**
- [ ] User answers are written to the correct subprocess stdin
- [ ] The Claude process resumes processing after receiving stdin input
- [ ] Writing to stdin of a terminated process returns an error

**FR-01.11: Process Lifecycle**
- [ ] Process state transitions are tracked (spawning -> running -> exited)
- [ ] Exit code is captured and stored on process termination
- [ ] Non-zero exit codes mark the associated task as failed

**FR-01.14: Tolerant Event Reader**
- [ ] Valid JSONL lines are parsed into event objects
- [ ] Corrupt or malformed lines are skipped without error
- [ ] Empty files return an empty event list

**FR-01.15: Event Replay**
- [ ] On startup, all registered projects have their events replayed
- [ ] Task states are correctly reconstructed (done, failed, orphaned)
- [ ] Pipeline phase states match the event history

**FR-01.16: Orphaned Task Detection**
- [ ] task_created without matching work_completed is marked as orphaned
- [ ] Orphaned tasks are visible in the task list with appropriate status

**FR-01.17: Phase Event Deduplication**
- [ ] Two phase_completed events for the same phase are deduplicated
- [ ] The event with a detail field is preferred over the one without
- [ ] Single phase_completed events are kept as-is

**FR-01.18: Task Created Event Emission**
- [ ] Starting a new task via API emits a task_created event to shipwright_events.jsonl
- [ ] The event contains task_id, project_id, source, and timestamp
- [ ] The event contains description field
- [ ] The event contains optional intent and priority fields when provided

**FR-01.44: Kanban Status Derivation**
- [ ] Tasks are assigned a Kanban column (Backlog, In Progress, In Review, Done) based on their latest pipeline phase
- [ ] Status derivation uses the configurable phase-to-status mapping
- [ ] Default mapping: Backlog = (no phases, not yet started), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (no phases, task completion)
- [ ] Tasks with no pipeline events default to Backlog

**FR-01.45: Default Phase-to-Status Mapping**
- [ ] The default mapping is applied when no per-project mapping is configured
- [ ] All seven Shipwright phases are covered by the default mapping

**FR-01.46: Custom Phase-to-Status Mapping**
- [ ] Per-project custom mappings are stored in project settings
- [ ] Custom mappings override the default mapping for that project
- [ ] Invalid or incomplete custom mappings fall back to the default for unmapped phases

**FR-01.19: Concurrency Semaphore**
- [ ] No more than N Claude processes run simultaneously (default 3)
- [ ] The concurrency limit is configurable via settings
- [ ] Exceeding the limit queues the task rather than rejecting it

**FR-01.20: PID Tracking**
- [ ] Every spawned Claude process PID is recorded
- [ ] PIDs are removed from tracking when the process exits

**FR-01.21: Orphan Cleanup**
- [ ] On startup, tracked PIDs are checked against running OS processes
- [ ] Stale PIDs (process no longer running) are removed from tracking
- [ ] Still-running orphaned processes are terminated

**FR-01.22: Heartbeat Scheduler**
- [ ] Heartbeat runs every 30 seconds
- [ ] Dead processes are detected and their tasks marked as failed
- [ ] Queued tasks are started when slots become available

**FR-01.24: Project Registry**
- [ ] Projects are persisted to ~/.shipwright-webui/projects.json
- [ ] Create, read, update, and delete operations work correctly
- [ ] Registry file is created automatically if it does not exist

**FR-01.25: Project Metadata**
- [ ] Each project entry stores name, path, profile, status, and lastActive
- [ ] lastActive is updated on any project interaction

**FR-01.27: Inbox Aggregation**
- [ ] AskUserQuestion from any active Claude subprocess creates an inbox item
- [ ] Inbox items from multiple projects are accessible via a single global endpoint

**FR-01.28: Inbox Item Structure**
- [ ] Inbox items contain question, context, options, project_id, and task_id
- [ ] Items have a unique ID and timestamp

**FR-01.29: Answer Delivery**
- [ ] POST /api/inbox/:id/answer delivers the answer text to the correct Claude subprocess
- [ ] The inbox item is marked as answered after delivery
- [ ] Answering an already-answered item returns an error

**FR-01.30: Inbox SSE Notification**
- [ ] New inbox items trigger an SSE event of type inbox_new
- [ ] The SSE event includes the inbox item ID and project_id

**FR-01.31: Chat Persistence**
- [ ] NDJSON messages are written to .shipwright-webui/chat-history/{taskId}.jsonl
- [ ] Messages are appended in real-time as the stream progresses

**FR-01.32: Chat Replay**
- [ ] GET /api/projects/:id/chat/:taskId returns the full chronological message list
- [ ] Messages are ordered by timestamp

**FR-01.33: Config Reader**
- [ ] shipwright_run_config.json is read and parsed
- [ ] shipwright_plan_config.json, shipwright_build_config.json etc. are read when present
- [ ] Missing config files are handled gracefully (not an error)
- [ ] Pipeline state is derivable from events + phase configs alone when shipwright_run_config.json is missing (standalone invocation)

**FR-01.34: File Watcher**
- [ ] Changes to shipwright_events.jsonl trigger SSE updates
- [ ] Changes to shipwright_*_config.json trigger SSE updates
- [ ] File watchers are created per registered project

**FR-01.36: Project CRUD Routes**
- [ ] GET /api/projects returns all registered projects
- [ ] POST /api/projects creates a new project entry
- [ ] PATCH /api/projects/:id updates project metadata
- [ ] DELETE /api/projects/:id removes the project from the registry

**FR-01.37: Task Routes**
- [ ] GET /api/projects/:id/tasks returns all tasks for the project
- [ ] POST /api/projects/:id/tasks spawns a new Claude subprocess and creates a task

**FR-01.38: Inbox Routes**
- [ ] GET /api/inbox returns all open inbox items across all projects
- [ ] POST /api/inbox/:id/answer delivers the answer and marks the item resolved

**FR-01.39: Chat Routes**
- [ ] GET /api/projects/:id/chat/:taskId returns persisted chat messages
- [ ] POST /api/projects/:id/chat sends a message to the Claude subprocess

**FR-01.40: Pipeline Status Route**
- [ ] GET /api/projects/:id/pipeline returns phase states with status per phase
- [ ] Status is derived from event replay + config bridge
- [ ] Pipeline status works for standalone-invoked projects (no run_config)
- [ ] All 7 phases show status: project, design, plan, build, test, changelog, deploy

**FR-01.41: Docs Route**
- [ ] GET /api/projects/:id/docs returns a file tree of project artifacts
- [ ] Supports query parameter for reading individual file content

**FR-01.42: Classify Route**
- [ ] POST /api/projects/:id/classify accepts a text description
- [ ] Shells out to classify_intent.py and classify_complexity.py via uv run
- [ ] Returns intent, complexity, and affected FRs
- [ ] Is called asynchronously after task creation to enrich the Kanban card

**FR-01.47: Task Status Route**
- [ ] PATCH /api/projects/:id/tasks/:taskId/status accepts a status value (e.g., closed, cancelled)
- [ ] Updates the task state and emits a corresponding event to shipwright_events.jsonl
- [ ] Returns 404 if the task does not exist

**FR-01.43: Settings Routes**
- [ ] GET /api/settings returns current global settings
- [ ] PUT /api/settings updates and persists global settings

## 3. Quality Requirements

| ID | Requirement | Category |
|----|-------------|----------|
| QR-01.01 | The system SHALL reconstruct full in-memory state from events within 2 seconds for projects with up to 1000 events. | Performance |
| QR-01.02 | The system SHALL deliver SSE events to connected clients within 200ms of the triggering change. | Performance |
| QR-01.03 | The NDJSON stream parser SHALL process messages with less than 50ms latency per message. | Performance |
| QR-01.04 | The system SHALL continue operating when a single Claude subprocess crashes without affecting other running subprocesses. | Reliability |
| QR-01.05 | The system SHALL recover from a server restart by replaying events and reconstructing state without data loss. | Reliability |
| QR-01.06 | The system SHALL handle corrupt or truncated JSONL files gracefully by skipping invalid lines rather than failing. | Reliability |
| QR-01.07 | All REST API routes SHALL return appropriate HTTP status codes (200, 201, 400, 404, 500) and JSON error bodies. | Usability |
| QR-01.08 | The system SHALL log errors with sufficient context (project_id, task_id, process PID) for debugging. | Maintainability |
| QR-01.09 | All core modules SHALL be unit-testable with dependency injection for child_process, file system, and chokidar. | Testability |

## 4. Constraints

| ID | Constraint | Type |
|----|-----------|------|
| C-01.01 | The backend SHALL use Hono as the HTTP framework (not Express, Fastify, or Koa). | Technology |
| C-01.02 | The system SHALL use SSE for server-to-client push (not WebSocket or Socket.io). | Technology |
| C-01.03 | The system SHALL use chokidar for file watching. | Technology |
| C-01.04 | The system SHALL use child_process.spawn (not exec) for Claude CLI subprocesses. | Technology |
| C-01.05 | The system SHALL use proper-lockfile for JSONL file append operations. | Technology |
| C-01.06 | The system SHALL NOT use any database; all persistence is via JSONL event logs and JSON files. | Technology |
| C-01.07 | The system SHALL NOT implement authentication or authorization (local single-user app). | Architecture |
| C-01.08 | All file writes to project directories SHALL occur only through the backend process, never through child processes or frontend. | Architecture |
| C-01.09 | The backend SHALL be written in TypeScript with strict mode enabled. | Technology |
| C-01.10 | The system SHALL use node-cron for the heartbeat scheduler. | Technology |

## 5. Dependencies

**Depends on:** Nothing (foundation split).

**Provides to:**
- **Split 02 (UI Shell & Chat):** REST API routes + SSE endpoints for projects, tasks, chat, inbox, and pipeline. TypeScript types for shared data models (Project, Task, InboxItem, Event, PipelineRun).
- **Split 03 (Viewers, Explorer & Advanced Features):** docs API (file tree + content), classify API (intent/complexity detection), settings API.

## 6. Key Decisions

- **Decision:** Use Hono instead of Express 5 as the HTTP framework.
  **Rationale:** Hono is modern, TypeScript-first, lightweight (~14KB), and has built-in streamSSE() support. Express 5 is still maturing and lacks native SSE. Better developer experience and Masterclass appeal.

- **Decision:** Reconstruct task state from events in-memory instead of persisting to tasks.json.
  **Rationale:** Avoids sync problems between a tasks.json cache and the event log as source of truth. Pure event-sourcing with in-memory state is cleaner and eliminates an entire class of consistency bugs.

- **Decision:** Add a task_created event type to record_event.py.
  **Rationale:** The existing event system only tracks completion (work_completed, phase_completed). Without task_created, there is no way to detect orphaned tasks (started but never completed due to crash). Enables full lifecycle tracking.

- **Decision:** Deduplicate phase_completed events by preferring the event with a detail field.
  **Rationale:** All pipeline phases (project, design, plan, build, deploy, changelog) and the orchestrator emit phase_completed. The backend deduplicates in record_event.py (skips if same phase already recorded). The WebUI also handles deduplication client-side, preferring the event with a detail field.

- **Decision:** Use SSE instead of WebSocket/Socket.io for real-time updates.
  **Rationale:** SSE is sufficient for a local single-user app with unidirectional server-to-client push. Simpler than WebSocket, no reconnection protocol needed, native browser support via EventSource API.

- **Decision:** All file writes go through the backend process only.
  **Rationale:** Prevents race conditions when multiple projects run in parallel. Child processes (Claude CLI) write their own artifacts, but the WebUI backend is the sole writer of registry, inbox, chat history, and task_created events.

- **Decision:** Use proper-lockfile for JSONL append operations.
  **Rationale:** Multiple file watchers and event writers could attempt concurrent appends. File-level locking prevents corruption of the append-only event log.

## 8. References

- Spec/plan-shipwright-webui.md — Full product plan and architecture
- webui/planning/project-manifest.md — Split manifest and dependency flow
- webui/planning/shipwright_project_interview.md — Interview transcript with architectural decisions
- docs/hooks-and-pipeline.md — Shipwright hooks registry, context loading matrix, artifact write matrix
- Paperclip (MIT): https://github.com/paperclipai/paperclip — Claude Adapter patterns, heartbeat, live events
