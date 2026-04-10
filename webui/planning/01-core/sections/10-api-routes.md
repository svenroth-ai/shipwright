# Section 10: REST API Routes

## Goal

Wire all core modules together through Hono REST API routes. Each route file imports the relevant manager/store, validates input, calls business logic, and returns JSON responses following the `{ data: T }` / `{ error: string }` convention. This section also implements the docs file tree route, the classify shell-out route, settings persistence, the task status update route, and the main entry point that initializes all managers in dependency order with graceful shutdown.

## FRs Covered

- **FR-01.36** — Project CRUD routes (GET/POST/PATCH/DELETE /api/projects)
- **FR-01.37** — Task routes (GET/POST /api/projects/:id/tasks)
- **FR-01.38** — Inbox routes (GET /api/inbox, POST /api/inbox/:id/answer)
- **FR-01.39** — Chat routes (GET/POST /api/projects/:id/chat)
- **FR-01.40** — Pipeline status route (GET /api/projects/:id/pipeline)
- **FR-01.41** — Docs route (GET /api/projects/:id/docs)
- **FR-01.42** — Classify route (POST /api/projects/:id/classify)
- **FR-01.43** — Settings routes (GET/PUT /api/settings)
- **FR-01.47** — Task status update route (PATCH /api/projects/:id/tasks/:taskId/status)

## Files to Create/Modify

| Action | Path |
|--------|------|
| Create | `server/src/routes/projects.ts` |
| Create | `server/src/routes/tasks.ts` |
| Create | `server/src/routes/inbox.ts` |
| Create | `server/src/routes/chat.ts` |
| Create | `server/src/routes/pipeline.ts` |
| Create | `server/src/routes/docs.ts` |
| Create | `server/src/routes/classify.ts` |
| Create | `server/src/routes/settings.ts` |
| Create | `server/src/bridge/doc-index.ts` |
| Create | `server/src/bridge/intent-classifier.ts` |
| Create | `server/src/bridge/pipeline-state.ts` |
| Modify | `server/src/index.ts` |
| Create | `server/src/routes/projects.test.ts` |
| Create | `server/src/routes/tasks.test.ts` |
| Create | `server/src/routes/inbox.test.ts` |
| Create | `server/src/routes/chat.test.ts` |
| Create | `server/src/routes/pipeline.test.ts` |
| Create | `server/src/routes/docs.test.ts` |
| Create | `server/src/routes/classify.test.ts` |
| Create | `server/src/routes/settings.test.ts` |

## Implementation Steps

### Step 1: Create Project Routes

Create `server/src/routes/projects.ts`. Export a function that takes `ProjectManager`, `FileWatcher`, `EventStore`, and `SSEManager` as dependencies and returns a Hono app:

- `GET /api/projects` — call `projectManager.getAll()`, return `{ data: Project[] }`.
- `POST /api/projects` — validate body (`name` and `path` required, return 400 if missing). Call `projectManager.create(body)`, start file watcher for the new project, trigger event replay. Return 201 `{ data: Project }`.
- `GET /api/projects/:id` — call `projectManager.getById(id)`, return `{ data: Project }` or 404.
- `PATCH /api/projects/:id` — validate body, call `projectManager.update(id, body)`, return `{ data: Project }` or 404.
- `DELETE /api/projects/:id` — call `projectManager.delete(id)`, stop file watcher. Broadcast `project:updated` SSE. Return 204.

### Step 2: Create Task Routes

Create `server/src/routes/tasks.ts`. Export a function taking `TaskManager`, `EventStore`, `ProcessGovernor`, `ClaudeAdapter`, `SSEManager`, `ProjectManager`, and event writer dependencies:

- `GET /api/projects/:id/tasks` — resolve project (404 if missing). Call `taskManager.getTasksWithKanban(id, project.settings?.phaseToStatusMapping)`. Return `{ data: Task[] }`.
- `POST /api/projects/:id/tasks` — validate body (`description` required). Generate session ID. Emit `task_created` event via `eventWriter.emitTaskCreatedEvent()`. Call `governor.acquire()` to spawn Claude CLI. If process returned, return 201 `{ data: Task }`. If `"queued"`, return 202 `{ data: { taskId, status: "queued" } }`. Fire async classify call after creation (do not await -- enriches card in background).
- `PATCH /api/projects/:id/tasks/:taskId/status` — validate body (`status` required, must be `"closed"` or `"cancelled"`). Find task (404 if missing). Emit corresponding event: `task_cancelled` for cancelled, `work_completed` with `source: "manual"` for closed. Update in-memory state. Broadcast `task:updated` SSE. Return `{ data: Task }`.

### Step 3: Create Inbox Routes

Create `server/src/routes/inbox.ts`. Export a function taking `InboxManager` and `SSEManager`:

- `GET /api/inbox` — read optional `?status=pending` query param. Call `inboxManager.getAll(filter)`. Return `{ data: InboxItem[] }`.
- `POST /api/inbox/:id/answer` — validate body (`answer` required). Call `inboxManager.answer(id, body.answer)`. Broadcast `inbox:answered` SSE. Return `{ data: InboxItem }`.

### Step 4: Create Chat Routes

Create `server/src/routes/chat.ts`. Export a function taking `ChatStore`, `ProcessGovernor`, `ClaudeAdapter`, `ProjectManager`:

- `GET /api/projects/:id/chat/:taskId` — resolve project (404 if missing). Call `chatStore.load(project.path, taskId)`. Return `{ data: ChatMessage[] }`.
- `POST /api/projects/:id/chat` — validate body (`taskId` and `message` required). Find active process via governor (400 if not running). Call `adapter.sendStdin(process, body.message)`. Create a `ChatMessage` of type `"user"` with generated ID and timestamp. Append to chat store. Return `{ data: ChatMessage }`.

### Step 5: Create Pipeline State Bridge

Create `server/src/bridge/pipeline-state.ts`. Export:

```typescript
async function getPipelineState(
  projectId: string,
  eventStore: EventStore,
  configReader: typeof readAllConfigs,
  projectDir: string
): Promise<PipelineRun>
```

- Get phase statuses from events via `eventStore.getPipelineState(projectId)`.
- Get phase statuses from configs via `configReader(projectDir)` then `derivePipelineFromConfigs()`.
- Merge: events take priority (more granular), configs fill gaps for standalone projects.
- Return `PipelineRun` with all 7 phases (project, design, plan, build, test, changelog, deploy).

### Step 6: Create Pipeline Route

Create `server/src/routes/pipeline.ts`. Export a function taking `EventStore`, `ProjectManager`:

- `GET /api/projects/:id/pipeline` — resolve project. Call `getPipelineState()`. Return `{ data: PipelineRun }`.

### Step 7: Create Doc Index Bridge

Create `server/src/bridge/doc-index.ts`. Export:

- `buildFileTree(projectDir: string, deps?: FileSystemDeps): FileTreeNode[]` — recursively scan project directory. Exclude: `node_modules`, `.git`, `__pycache__`, `.venv`, `.shipwright-webui`. Return tree of `{ name, path (relative), type: "file" | "directory", children? }`.
- `readFileContent(filePath: string, projectDir: string, deps?: FileSystemDeps): Promise<string>` — validate that `filePath` resolved against `projectDir` stays within `projectDir` (path traversal prevention -- use `path.resolve()` and check `startsWith()`). Throw `AppError(400, "Path traversal not allowed")` if violation. Read and return UTF-8 string.

### Step 8: Create Docs Route

Create `server/src/routes/docs.ts`. Export a function taking `ProjectManager`:

- `GET /api/projects/:id/docs` — resolve project. Check for `?file=path/to/file` query param.
  - If `file` param present: call `readFileContent(file, project.path)`, return `{ data: { content, path } }`.
  - If no `file` param: call `buildFileTree(project.path)`, return `{ data: FileTreeNode[] }`.

### Step 9: Create Intent Classifier Bridge

Create `server/src/bridge/intent-classifier.ts`. Export:

- `classifyIntent(description: string, projectDir: string, deps?: SpawnDeps): Promise<{ intent: string; affected_frs?: string[] }>` — spawn `uv run classify_intent.py` with description as argument. Parse JSON output from stdout. If script not found, spawn fails, or output is not valid JSON, return `{ intent: "unknown" }` (graceful degradation).
- `classifyComplexity(description: string, projectDir: string, deps?: SpawnDeps): Promise<{ complexity: string }>` — spawn `uv run classify_complexity.py`. Parse JSON output. Graceful fallback to `{ complexity: "unknown" }`.

Both functions must have a timeout (10 seconds) to prevent hanging. Use `child_process.spawn` with `stdio: ["pipe", "pipe", "pipe"]` and read stdout to completion.

### Step 10: Create Classify Route

Create `server/src/routes/classify.ts`. Export a function taking `ProjectManager`:

- `POST /api/projects/:id/classify` — validate body (`description` required). Resolve project. Run both classifiers in parallel via `Promise.all([classifyIntent(...), classifyComplexity(...)])`. Return `{ data: { intent, complexity, affected_frs } }`.

### Step 11: Create Settings Routes

Create `server/src/routes/settings.ts`. Settings stored in `~/.shipwright-webui/settings.json`.

- `GET /api/settings` — read settings file. If missing, return defaults: `{ port: 3847, maxConcurrent: 3, heartbeatIntervalMs: 30000 }`. Return `{ data: GlobalSettings }`.
- `PUT /api/settings` — validate body. Read existing settings, merge with provided values, write to file. Return `{ data: GlobalSettings }`.

### Step 12: Update Main Entry Point

Modify `server/src/index.ts` to initialize all managers in dependency order:

1. Load config from `config.ts`.
2. Create `EventStore`.
3. Create `SSEManager`.
4. Create `ClaudeAdapter` with `onEvent` callback that:
   - Appends message to `ChatStore`.
   - Checks `isAskUserQuestion(msg)` -- if true, calls `inboxManager.addQuestion()`.
   - Forwards all events to SSE via `sseManager.broadcast()`.
5. Create `ProcessGovernor` with adapter and `maxConcurrent` from config.
6. Create `HeartbeatScheduler` with governor.
7. Create `ProjectManager`, call `load()`.
8. Create `TaskManager` with event store.
9. Create `InboxManager` with governor, adapter, and SSE notify callback.
10. Create `ChatStore`.
11. Create `FileWatcher`.

For each registered project: replay events via event store, start file watcher with onChange callback that re-reads events/configs and broadcasts SSE updates.

Run `governor.cleanupOrphans()`.
Start heartbeat scheduler.

Mount all route groups on the Hono app:
- `app.route("/", createProjectRoutes(...))`
- `app.route("/", createTaskRoutes(...))`
- `app.route("/", createInboxRoutes(...))`
- `app.route("/", createChatRoutes(...))`
- `app.route("/", createPipelineRoutes(...))`
- `app.route("/", createDocsRoutes(...))`
- `app.route("/", createClassifyRoutes(...))`
- `app.route("/", createSettingsRoutes(...))`
- `app.route("/", createSSERoute(...))`

Register graceful shutdown handler (`process.on("SIGTERM")` and `process.on("SIGINT")`):
1. Stop heartbeat scheduler.
2. Unwatch all files via `fileWatcher.unwatchAll()`.
3. Close all SSE connections via `sseManager.closeAll()`.
4. Terminate all active Claude processes.
5. Persist governor PIDs via `governor.persistPids()`.
6. Exit process.

Each shutdown step should have a 5-second timeout to prevent hanging.

### Step 13: Write Integration Tests

Create integration test files using Hono's `app.request()` test helper. Mock all manager dependencies.

**`server/src/routes/projects.test.ts`:**
1. `GET /api/projects` returns 200 with array.
2. `POST /api/projects` with valid body returns 201 with project.
3. `POST /api/projects` with missing name returns 400.
4. `PATCH /api/projects/:id` returns 200 with updated project.
5. `DELETE /api/projects/:id` returns 204.
6. `GET /api/projects/:id` for non-existent project returns 404.

**`server/src/routes/tasks.test.ts`:**
7. `GET /api/projects/:id/tasks` returns tasks with kanbanStatus field.
8. `POST /api/projects/:id/tasks` returns 201 and invokes governor.acquire (mock adapter).
9. `POST /api/projects/:id/tasks` when governor is full returns 202 (queued).
10. `PATCH /api/projects/:id/tasks/:taskId/status` with `cancelled` returns updated task.
11. `PATCH /api/projects/:id/tasks/:taskId/status` for non-existent task returns 404.

**`server/src/routes/inbox.test.ts`:**
12. `GET /api/inbox` returns all items.
13. `GET /api/inbox?status=pending` returns only pending items.
14. `POST /api/inbox/:id/answer` returns answered item.
15. `POST /api/inbox/:id/answer` for already-answered item returns 400.

**`server/src/routes/chat.test.ts`:**
16. `GET /api/projects/:id/chat/:taskId` returns message array.
17. `POST /api/projects/:id/chat` sends message and returns it.

**`server/src/routes/pipeline.test.ts`:**
18. `GET /api/projects/:id/pipeline` returns 7 phases with statuses.

**`server/src/routes/docs.test.ts`:**
19. `GET /api/projects/:id/docs` returns file tree.
20. `GET /api/projects/:id/docs?file=...` returns file content.
21. Path traversal attempt (`?file=../../etc/passwd`) returns 400.

**`server/src/routes/classify.test.ts`:**
22. `POST /api/projects/:id/classify` returns intent and complexity (mock spawn).
23. Classifier failure returns graceful fallback `{ intent: "unknown", complexity: "unknown" }`.

**`server/src/routes/settings.test.ts`:**
24. `GET /api/settings` returns defaults when no file exists.
25. `PUT /api/settings` persists and returns updated settings.

## Test Strategy

### Unit Tests

| File | Coverage |
|------|----------|
| (none -- this section is route integration) | |

### Integration Tests

| File | Coverage |
|------|----------|
| `server/src/routes/projects.test.ts` | Project CRUD HTTP status codes, validation, JSON shape |
| `server/src/routes/tasks.test.ts` | Task list, create, queue, status update |
| `server/src/routes/inbox.test.ts` | Inbox list, filter, answer delivery |
| `server/src/routes/chat.test.ts` | Chat history load, message send |
| `server/src/routes/pipeline.test.ts` | Pipeline phase derivation from events + configs |
| `server/src/routes/docs.test.ts` | File tree, content read, path traversal prevention |
| `server/src/routes/classify.test.ts` | Classifier shell-out, graceful fallback |
| `server/src/routes/settings.test.ts` | Settings read/write, defaults |

### Mocking Strategy

All route tests mock the underlying managers/stores:
- `ProjectManager` — mock `getAll`, `getById`, `create`, `update`, `delete`.
- `TaskManager` — mock `getTasksWithKanban`, `getTaskById`.
- `ProcessGovernor` — mock `acquire`, `getProcess`.
- `ClaudeAdapter` — mock `sendStdin`.
- `InboxManager` — mock `getAll`, `answer`.
- `ChatStore` — mock `load`, `append`.
- `EventStore` — mock `getPipelineState`, `addEvent`.
- `SSEManager` — mock `broadcast`.
- `child_process.spawn` — mock for classify tests to return fake stdout.
- `FileSystemDeps` — mock for docs/settings tests.

## Dependencies

- **Section 04 (Task Manager)** — `TaskManager` class with `getTasksWithKanban()`.
- **Section 06 (Process Governor)** — `ProcessGovernor` class with `acquire()`, `release()`, `getProcess()`, `cleanupOrphans()`, `persistPids()`.
- **Section 07 (Project Registry)** — `ProjectManager`, `FileWatcher`, `configReader`.
- **Section 08 (Inbox & Chat)** — `InboxManager`, `ChatStore`.
- **Section 09 (SSE Manager)** — `SSEManager` and SSE route.
- **Section 03 (Event System)** — `EventStore`, `eventWriter`.
- **Section 05 (Claude Adapter)** — `ClaudeAdapter`.
- **Section 02 (Shared Types)** — all TypeScript interfaces.
- **Section 01 (Project Setup)** — Hono app, middleware, config, `AppError`.

## Acceptance Criteria

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
- [ ] Path traversal attempts are blocked with 400 error

**FR-01.42: Classify Route**
- [ ] POST /api/projects/:id/classify accepts a text description
- [ ] Shells out to classify_intent.py and classify_complexity.py via uv run
- [ ] Returns intent, complexity, and affected FRs
- [ ] Is called asynchronously after task creation to enrich the Kanban card
- [ ] Classifier failure returns graceful fallback

**FR-01.47: Task Status Route**
- [ ] PATCH /api/projects/:id/tasks/:taskId/status accepts a status value (closed, cancelled)
- [ ] Updates the task state and emits a corresponding event to shipwright_events.jsonl
- [ ] Returns 404 if the task does not exist

**FR-01.43: Settings Routes**
- [ ] GET /api/settings returns current global settings
- [ ] PUT /api/settings updates and persists global settings
- [ ] Missing settings file returns sensible defaults
