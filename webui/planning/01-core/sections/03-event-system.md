# Section 03: Event System — Reader, Replay & State

## Goal

Implement the tolerant JSONL event reader, event replay engine that reconstructs in-memory task and pipeline state from the event log, orphaned task detection, phase deduplication, and the ability to emit new events (task_created) via file append with proper-lockfile.

## FRs Covered

- **FR-01.14** — The system SHALL read shipwright_events.jsonl from each registered project directory using a tolerant reader that skips corrupt or malformed lines.
- **FR-01.15** — The system SHALL reconstruct in-memory task and pipeline state from events on server startup (event replay).
- **FR-01.16** — The system SHALL track task_created events without a matching work_completed event as orphaned tasks.
- **FR-01.17** — The system SHALL deduplicate phase_completed events when both plugin and orchestrator emit them, preferring the event that contains a detail field.
- **FR-01.18** — The system SHALL emit a task_created event when a user starts a new task through the API.

## Files to Create

| File | Purpose |
|------|---------|
| `server/src/bridge/event-reader.ts` | Tolerant JSONL parser, file reading with lockfile |
| `server/src/bridge/event-writer.ts` | Append events to JSONL with proper-lockfile |
| `server/src/core/event-store.ts` | In-memory event store, replay engine, state reconstruction |
| `server/src/bridge/event-reader.test.ts` | Unit tests for reader |
| `server/src/bridge/event-writer.test.ts` | Unit tests for writer |
| `server/src/core/event-store.test.ts` | Unit tests for replay and state derivation |

## Implementation Steps

1. **Create `server/src/bridge/event-reader.ts`**:
   - Export `FileSystemDeps` interface: `{ readFile: (path: string, encoding: string) => Promise<string>, existsSync: (path: string) => boolean }` — injectable for testing (QR-01.09)
   - Export `readEventsFromFile(filePath: string, fs?: FileSystemDeps): Promise<ShipwrightEvent[]>`
   - Read file content as UTF-8 string. If file does not exist, return empty array (graceful)
   - Split by newlines. For each line:
     - Try `JSON.parse()`, validate it has at least `type` and `timestamp` fields
     - Push valid events to result array
     - On parse error or missing fields, skip the line and log a warning with line number (QR-01.06, FR-01.14)

2. **Create `server/src/bridge/event-writer.ts`**:
   - Export `WriterDeps` interface: `{ appendFile: (path: string, data: string) => Promise<void>, lock: (path: string) => Promise<() => Promise<void>> }`
   - Export `appendEvent(filePath: string, event: ShipwrightEvent, deps?: WriterDeps): Promise<void>`:
     - Use `proper-lockfile` to acquire a lock on the file before appending
     - Serialize event as JSON, append with trailing newline
     - Release lock in a `finally` block
   - Export `emitTaskCreatedEvent(filePath: string, taskId: string, projectId: string, description: string, intent?: string, priority?: string): Promise<ShipwrightEvent>`:
     - Construct a `task_created` event with `timestamp: new Date().toISOString()`, `source: "webui"`
     - Call `appendEvent()` (FR-01.18)

3. **Create `server/src/core/event-store.ts`**:
   - Define internal `TaskStateEntry` type holding derived status, current phase, description, timestamps
   - Export class `EventStore`:
     - `private events: Map<string, ShipwrightEvent[]>` — keyed by projectId
     - `private taskStates: Map<string, TaskStateEntry>` — keyed by taskId
     - `replayProject(projectId: string, events: ShipwrightEvent[]): void` — processes events in order:
       - `task_created` -> create new task state entry with status `pending`
       - `phase_started` -> update task's current phase, mark task as `running`
       - `phase_completed` -> apply deduplication logic (FR-01.17, see step 4), update pipeline phase status to `completed`
       - `work_completed` -> mark task as `done`
       - `work_failed` -> mark task as `failed`
       - `task_cancelled` -> mark task as `cancelled`
     - `detectOrphans(): Task[]` — scan all task states: any task with status `pending` or `running` that has a `task_created` event but no `work_completed` / `work_failed` event and no active OS process is marked as `orphaned` (FR-01.16)
     - `getTasksForProject(projectId: string): Task[]` — return derived task list
     - `getPipelineState(projectId: string): PipelinePhase[]` — return per-phase status derived from events
     - `addEvent(projectId: string, event: ShipwrightEvent): void` — incrementally update state without full replay

4. **Implement phase deduplication** (FR-01.17):
   - Maintain a `Map<string, ShipwrightEvent>` keyed by `${task_id}:${phase}`
   - When a second `phase_completed` arrives for the same key, compare timestamps
   - If within 60 seconds, keep the event that has a truthy `detail` field
   - If both have `detail`, keep the later one

## Test Strategy

### Unit Tests

**`server/src/bridge/event-reader.test.ts`**:
- Valid JSONL with 3 events -> returns 3 parsed events
- JSONL with 1 corrupt line in the middle -> returns 2 events, skips corrupt line
- Empty file -> returns empty array
- File does not exist -> returns empty array (no throw)
- Line with valid JSON but missing `type` field -> skipped

**`server/src/bridge/event-writer.test.ts`**:
- Appends event with trailing newline
- Lock is acquired before write and released after
- `emitTaskCreatedEvent` produces correct event shape with all fields (task_id, project_id, source, timestamp, description, intent, priority)

**`server/src/core/event-store.test.ts`**:
- Replay with task_created + work_completed -> task status is `done`
- Replay with task_created only -> task status is `pending` (orphan candidate)
- Replay with two phase_completed for same phase within 60s -> one with detail is kept
- Replay with two phase_completed for same phase >60s apart -> both kept
- `detectOrphans()` returns tasks with `task_created` but no completion event
- `addEvent()` incrementally updates state correctly
- Pipeline state derived correctly: 7 phases with correct statuses
- Performance: replay 1000 events in <2s (QR-01.01)

### Integration Tests

N/A — pure logic, no HTTP endpoints.

## Dependencies

- **Section 01** — project structure, package.json (for `proper-lockfile` dependency)
- **Section 02** — shared types (`ShipwrightEvent`, `EventType`, `Task`, `TaskStatus`, `PipelinePhase`, `PhaseStatus`)

## Acceptance Criteria

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
