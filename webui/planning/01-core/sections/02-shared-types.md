# Section 02: Shared TypeScript Types

## Goal

Define all TypeScript interfaces used by both server and client. These are the data contracts that every subsequent section depends on. Placing them in `client/src/types/` and importing via path alias ensures a single source of truth.

## FRs Covered

No specific FR — this section supports all FRs by providing the type foundation.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/types/project.ts` | Project, ProjectSettings, ProjectStatus interfaces |
| `client/src/types/task.ts` | Task, KanbanStatus, TaskStatus, PhaseToStatusMapping interfaces |
| `client/src/types/event.ts` | ShipwrightEvent, EventType union, specific event payloads |
| `client/src/types/inbox.ts` | InboxItem, InboxStatus interfaces |
| `client/src/types/chat.ts` | ChatMessage, ChatMessageType union, NdjsonMessage interfaces |
| `client/src/types/pipeline.ts` | PipelineRun, PipelinePhase, PhaseStatus interfaces |
| `client/src/types/sse.ts` | SSEEvent, SSEEventType union |
| `client/src/types/settings.ts` | GlobalSettings interface |
| `client/src/types/api.ts` | ApiResponse<T>, ApiError, PaginatedResponse<T> generic wrappers |
| `client/src/types/index.ts` | Barrel export of all types |

## Implementation Steps

1. **Create `client/src/types/project.ts`**:
   - `ProjectStatus` as const union: `"active" | "archived" | "error"`
   - `ProjectSettings` interface: `phaseToStatusMapping?: Record<string, KanbanStatus>`, `claudePluginDirs?: string[]`
   - `Project` interface: `id: string`, `name: string`, `path: string`, `profile: string`, `status: ProjectStatus`, `lastActive: string` (ISO timestamp), `settings?: ProjectSettings`, `createdAt: string`

2. **Create `client/src/types/task.ts`**:
   - `KanbanStatus` as const union: `"backlog" | "in_progress" | "in_review" | "done" | "failed" | "cancelled"`
   - `TaskStatus` as const union: `"pending" | "running" | "waiting" | "done" | "failed" | "orphaned" | "cancelled"`
   - `PhaseToStatusMapping` as `Record<string, KanbanStatus>`
   - `Task` interface: `id: string`, `projectId: string`, `description: string`, `intent?: string`, `priority?: string`, `complexity?: string`, `status: TaskStatus`, `kanbanStatus: KanbanStatus`, `currentPhase?: string`, `sessionId: string`, `pid?: number`, `exitCode?: number`, `createdAt: string`, `updatedAt: string`

3. **Create `client/src/types/event.ts`**:
   - `EventType` as const union: `"task_created" | "phase_started" | "phase_completed" | "work_completed" | "work_failed" | "task_cancelled"`
   - `ShipwrightEvent` interface: `type: EventType`, `timestamp: string`, `task_id: string`, `project_id?: string`, `phase?: string`, `detail?: string`, `source?: string`, `description?: string`, `intent?: string`, `priority?: string`, plus `[key: string]: unknown` for extensibility

4. **Create `client/src/types/inbox.ts`**:
   - `InboxStatus` as const union: `"pending" | "answered"`
   - `InboxItem` interface: `id: string`, `projectId: string`, `taskId: string`, `question: string`, `context?: string`, `options?: string[]`, `answer?: string`, `status: InboxStatus`, `createdAt: string`, `answeredAt?: string`

5. **Create `client/src/types/chat.ts`**:
   - `ChatMessageType` as const union: `"assistant" | "tool_use" | "tool_result" | "result" | "user" | "system"`
   - `ChatMessage` interface: `id: string`, `taskId: string`, `type: ChatMessageType`, `content: string`, `toolName?: string`, `toolInput?: unknown`, `toolOutput?: unknown`, `timestamp: string`
   - `NdjsonMessage` interface: `type: string`, `message?: unknown`, `tool_name?: string`, `tool_input?: unknown`, `content?: string`, `result?: string`, `session_id?: string`, plus `[key: string]: unknown`

6. **Create `client/src/types/pipeline.ts`**:
   - `PhaseStatus` as const union: `"pending" | "running" | "completed" | "failed" | "skipped"`
   - `PipelinePhase` interface: `name: string`, `status: PhaseStatus`, `startedAt?: string`, `completedAt?: string`, `detail?: string`
   - `PipelineRun` interface: `projectId: string`, `phases: PipelinePhase[]`, `currentPhase?: string`, `taskId?: string`

7. **Create `client/src/types/sse.ts`**:
   - `SSEEventType` as const union: `"project:updated" | "task:created" | "task:updated" | "inbox:new" | "inbox:answered" | "chat:message" | "pipeline:updated"`
   - `SSEEvent<T = unknown>` interface: `type: SSEEventType`, `payload: T`, `timestamp: string`

8. **Create `client/src/types/settings.ts`**:
   - `GlobalSettings` interface: `port: number`, `maxConcurrent: number`, `heartbeatIntervalMs: number`, `claudeCliPath?: string`, `defaultProfile?: string`

9. **Create `client/src/types/api.ts`**:
   - `ApiResponse<T>` interface: `data: T`
   - `ApiError` interface: `error: string`, `detail?: string`
   - `PaginatedResponse<T>` interface extending `ApiResponse<T[]>` with `total: number`, `offset: number`, `limit: number`

10. **Create `client/src/types/index.ts`** — barrel export re-exporting all types from each file.

## Test Strategy

### Unit Tests

Type-only section — no runtime logic to test. Validate that types compile cleanly with `tsc --noEmit`. Write a small type-check test file (`client/src/types/types.typecheck.ts`) that constructs objects of each interface to ensure no type errors. This test runs as part of the TypeScript compiler check, not vitest.

### Integration Tests

N/A.

## Dependencies

- **Section 01** — project structure and TypeScript config must exist (tsconfig.json with path aliases)

## Acceptance Criteria

- [ ] All type files compile cleanly with `tsc --noEmit`
- [ ] Barrel export `client/src/types/index.ts` re-exports all types
- [ ] Server can import shared types via `@shared/*` path alias
- [ ] Every interface field documented in the plan is present in the type definitions
- [ ] No `any` types used — all fields have explicit types (except the `[key: string]: unknown` index signature on extensible interfaces)
