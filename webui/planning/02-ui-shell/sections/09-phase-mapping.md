# Section 09: Phase-to-Status Mapping

## Goal

Implement the phase-to-status mapping logic that determines which Kanban column a task card appears in based on its current Shipwright pipeline phase. Provide a default mapping, support per-project overrides via project settings, and expose a UI component for viewing and editing the mapping configuration.

## FRs Covered

- **FR-02.34** — Map Shipwright phases to board columns with configurable mapping. Default: Backlog = (empty, not yet started), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (empty, task completion).
- **FR-02.35** — Per-project override of phase-to-status mapping via project settings.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/lib/phaseMapping.ts` | Default mapping, merge logic, phase-to-column resolver |
| `client/src/hooks/usePhaseMapping.ts` | Hook: resolve mapping for a project (default + overrides) |
| `client/src/components/board/PhaseMappingConfig.tsx` | UI for viewing/editing phase-to-column mapping |
| `client/src/lib/phaseMapping.test.ts` | Tests for mapping logic |
| `client/src/hooks/usePhaseMapping.test.ts` | Tests for hook behavior |
| `client/src/components/board/PhaseMappingConfig.test.tsx` | Tests for config UI |

## Design Reference

- **Secondary:** `designs/screens/15-settings.html` — Settings page layout (phase mapping is a subsection of project settings)

## Implementation Steps

1. **Create `client/src/lib/phaseMapping.ts`**:
   - Import `KanbanStatus` from shared types
   - Define the default mapping constant:
     ```typescript
     export const DEFAULT_PHASE_MAPPING: Record<string, KanbanStatus> = {
       project: "backlog",
       design: "backlog",
       plan: "backlog",
       build: "in_progress",
       test: "in_review",
       deploy: "done",
       done: "done",
     } as const;
     ```
   - Export `resolvePhaseMapping(projectOverrides?: Record<string, KanbanStatus>): Record<string, KanbanStatus>`:
     - Merges `DEFAULT_PHASE_MAPPING` with `projectOverrides` (overrides win)
     - Returns the merged mapping
   - Export `getKanbanStatus(phase: string, mapping: Record<string, KanbanStatus>): KanbanStatus`:
     - Looks up phase in mapping
     - Fallback: if phase not found, return `"backlog"` (safe default for unknown phases)
   - Export `KANBAN_COLUMNS` constant:
     ```typescript
     export const KANBAN_COLUMNS = [
       { id: "backlog" as const, label: "Backlog" },
       { id: "in_progress" as const, label: "In Progress" },
       { id: "in_review" as const, label: "In Review" },
       { id: "done" as const, label: "Done" },
     ] as const;
     ```
   - Export `PIPELINE_PHASES` constant:
     ```typescript
     export const PIPELINE_PHASES = [
       "project", "design", "plan", "build", "test", "deploy", "done"
     ] as const;
     ```

2. **Create `client/src/hooks/usePhaseMapping.ts`**:
   - Export `usePhaseMapping(projectId?: string)`:
     - Fetch project data via `useProject(projectId)` when projectId is defined
     - Extract `project.settings?.phaseToStatusMapping` as overrides
     - Compute resolved mapping via `resolvePhaseMapping(overrides)`
     - Return `{ mapping, getStatus: (phase: string) => KanbanStatus }`
   - When `projectId` is undefined (All tab): use default mapping only
   - Memoize the resolved mapping to avoid unnecessary recalculations

3. **Create `client/src/components/board/PhaseMappingConfig.tsx`**:
   - Props: `projectId: string`, `mapping: Record<string, KanbanStatus>`, `onSave: (mapping: Record<string, KanbanStatus>) => void`
   - Layout: a table/grid showing each phase and its mapped column
   - For each phase in `PIPELINE_PHASES`:
     - Row: phase name (with colored dot matching phase color) + dropdown to select target column
     - Dropdown options: all four `KANBAN_COLUMNS`
     - Current mapping highlighted as selected
   - "Reset to defaults" button: reverts to `DEFAULT_PHASE_MAPPING`
   - "Save" button: calls `onSave` with the modified mapping
   - Uses `@radix-ui/react-select` for accessible dropdown
   - Changes are tracked locally until Save is clicked (controlled form pattern)
   - This component is intended to be used in Settings (Split 03) but is built now for completeness

4. **Integrate mapping into KanbanBoard**:
   - Update `client/src/components/board/KanbanBoard.tsx` to use `usePhaseMapping(projectId)` instead of reading `kanbanStatus` directly from the task
   - The grouping logic becomes:
     ```typescript
     const { getStatus } = usePhaseMapping(projectId);
     const grouped = tasks.reduce((acc, task) => {
       const column = task.kanbanStatus || getStatus(task.currentPhase || "project");
       acc[column] = acc[column] || [];
       acc[column].push(task);
       return acc;
     }, {} as Record<KanbanStatus, Task[]>);
     ```
   - Prefer `task.kanbanStatus` from backend (already mapped server-side) but fall back to client-side mapping if not set

5. **Create mutation for saving mapping overrides**:
   - In `usePhaseMapping.ts`, export `useSavePhaseMapping()`:
     - `useMutation` for `PATCH /api/projects/:id` with body `{ settings: { phaseToStatusMapping: mapping } }`
     - Invalidates project queries on success

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/lib/phaseMapping.test.ts` | Default mapping values; override merge; fallback for unknown phases |
| `client/src/hooks/usePhaseMapping.test.ts` | Default mapping when no project; override applied; memoization |
| `client/src/components/board/PhaseMappingConfig.test.tsx` | Displays all phases; dropdown changes; save/reset |

### Test Details

- **phaseMapping.ts**:
  - Assert `DEFAULT_PHASE_MAPPING["project"] === "backlog"`, `["build"] === "in_progress"`, `["test"] === "in_review"`, `["deploy"] === "done"`
  - Call `resolvePhaseMapping({ build: "in_review" })`, assert build is now "in_review" while others unchanged
  - Call `getKanbanStatus("unknown_phase", DEFAULT_PHASE_MAPPING)`, assert returns "backlog" (fallback)
  - Call `getKanbanStatus("test", DEFAULT_PHASE_MAPPING)`, assert returns "in_review"

- **usePhaseMapping**:
  - `renderHook` with no projectId: assert returns default mapping
  - `renderHook` with projectId, MSW returns project with `settings.phaseToStatusMapping = { build: "in_review" }`: assert mapping has build -> "in_review"

- **PhaseMappingConfig**:
  - Render with default mapping. Assert 7 rows (one per phase). Assert "build" row shows "In Progress" selected.
  - Change "build" dropdown to "In Review". Click Save. Assert `onSave` called with modified mapping.
  - Click "Reset to defaults". Assert all dropdowns revert to default values.

## Dependencies

- **Section 03** — `useProject`, `useQueryClient`, data hooks

## Acceptance Criteria

From spec:
- [ ] Tasks placed in correct column based on current pipeline phase
- [ ] Default mapping applied: Backlog = (empty), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (empty)
- [ ] When Claude advances a task's phase, card moves to mapped column automatically
- [ ] Per-project override supported via project settings
- [ ] Unknown phases fall back to Backlog
- [ ] Mapping config UI shows all phases with column dropdowns
- [ ] Reset to defaults reverts all overrides
- [ ] Saving mapping persists via project settings API
