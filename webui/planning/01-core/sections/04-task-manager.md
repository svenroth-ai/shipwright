# Section 04: Task Manager — Kanban Status Derivation

## Goal

Implement the logic that maps pipeline phases to Kanban board columns, supporting both the default mapping and per-project custom mappings. The task manager sits on top of the event store and enriches task objects with their derived Kanban status.

## FRs Covered

- **FR-01.44** — The system SHALL derive Kanban column status (Backlog / In Progress / In Review / Done) from pipeline events using a configurable phase-to-status mapping.
- **FR-01.45** — The system SHALL support a default phase-to-status mapping: Backlog = (no phases, not yet started), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (no phases, task completion).
- **FR-01.46** — The system SHALL allow per-project custom phase-to-status mappings stored in project settings.

## Files to Create

| File | Purpose |
|------|---------|
| `server/src/core/task-manager.ts` | Kanban status derivation, phase-to-status mapping |
| `server/src/core/task-manager.test.ts` | Unit tests |

## Implementation Steps

1. **Create `server/src/core/task-manager.ts`**:

   - Export `DEFAULT_PHASE_TO_STATUS_MAPPING` as a `PhaseToStatusMapping`:
     ```
     project   -> backlog
     design    -> backlog
     plan      -> backlog
     build     -> in_progress
     test      -> in_review
     deploy    -> done
     changelog -> done
     done      -> done
     ```

   - Export `deriveKanbanStatus(task: { currentPhase?: string; status: TaskStatus }, mapping: PhaseToStatusMapping): KanbanStatus`:
     - If `task.status` is `done` -> return `done`
     - If `task.status` is `failed` -> return `failed`
     - If `task.status` is `cancelled` -> return `cancelled`
     - If `task.status` is `orphaned` -> return `backlog` (orphans surface in backlog for user action)
     - If `task.currentPhase` exists and mapping has an entry -> return mapped status
     - Fallback -> `backlog`

   - Export class `TaskManager`:
     - Constructor takes `EventStore` dependency (from Section 03)
     - `getTasksWithKanban(projectId: string, customMapping?: PhaseToStatusMapping): Task[]`:
       - Retrieve tasks from event store via `eventStore.getTasksForProject(projectId)`
       - Apply Kanban status derivation using resolved mapping
       - Return tasks with `kanbanStatus` field populated
     - `getTaskById(projectId: string, taskId: string): Task | undefined`:
       - Find single task from event store, derive Kanban status
     - `getTasksByStatus(projectId: string, kanbanStatus: KanbanStatus): Task[]`:
       - Filter tasks by Kanban column
     - `resolveMapping(projectMapping?: PhaseToStatusMapping): PhaseToStatusMapping`:
       - Merge custom mapping over default so unmapped phases fall through to defaults (FR-01.46)
       - Return `{ ...DEFAULT_PHASE_TO_STATUS_MAPPING, ...projectMapping }`

## Test Strategy

### Unit Tests

**`server/src/core/task-manager.test.ts`**:

**`deriveKanbanStatus` tests:**
- Phase `build` with default mapping -> `in_progress`
- Phase `test` with default mapping -> `in_review`
- Phase `project` with default mapping -> `backlog`
- Phase `deploy` with default mapping -> `done`
- No phase and status `pending` -> `backlog`
- Status `done` regardless of phase -> `done`
- Status `failed` regardless of phase -> `failed`
- Status `cancelled` -> `cancelled`
- Status `orphaned` -> `backlog`

**Custom mapping tests:**
- Custom mapping overrides default for `build` -> custom value used
- Custom mapping missing `test` -> default fallback used for `test`
- `resolveMapping` merges correctly: custom keys override, default keys fill gaps

**`TaskManager` class tests (mock EventStore):**
- `getTasksWithKanban` returns tasks with `kanbanStatus` field populated
- `getTasksWithKanban` with custom mapping applies overrides correctly
- `getTaskById` returns single task with Kanban status or undefined
- `getTasksByStatus("in_progress")` filters correctly
- `getTasksByStatus("done")` returns only done tasks

### Integration Tests

N/A — pure logic, no HTTP endpoints.

## Dependencies

- **Section 02** — shared types (`Task`, `TaskStatus`, `KanbanStatus`, `PhaseToStatusMapping`)
- **Section 03** — `EventStore` class (provides `getTasksForProject()`)

## Acceptance Criteria

**FR-01.44: Kanban Status Derivation**
- [ ] Tasks are assigned a Kanban column (Backlog, In Progress, In Review, Done) based on their latest pipeline phase
- [ ] Status derivation uses the configurable phase-to-status mapping
- [ ] Default mapping: Backlog = (empty), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (empty)
- [ ] Tasks with no pipeline events default to Backlog

**FR-01.45: Default Phase-to-Status Mapping**
- [ ] The default mapping is applied when no per-project mapping is configured
- [ ] All seven Shipwright phases are covered by the default mapping

**FR-01.46: Custom Phase-to-Status Mapping**
- [ ] Per-project custom mappings are stored in project settings
- [ ] Custom mappings override the default mapping for that project
- [ ] Invalid or incomplete custom mappings fall back to the default for unmapped phases
