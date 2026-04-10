# Section 06: Filter Bar, View Toggle & List View

## Goal

Build the filter bar above the board with phase and priority filter dropdowns, a Board/List view toggle with localStorage persistence, and a List view as a sortable table. Both board cards and list rows navigate to the Task Detail view on click. Filters apply to both views.

## FRs Covered

- **FR-02.17** — Filter bar with phase multi-select dropdown and priority filter.
- **FR-02.18** — View toggle: Board view and List view.
- **FR-02.19** — List view as sortable table (Status, Title, Phase, Priority, Tests, Commit, Updated).
- **FR-02.20** — List row click navigates to Task Detail.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/board/FilterBar.tsx` | Filter bar container with phase, priority, view toggle |
| `client/src/components/board/PhaseFilter.tsx` | Phase multi-select dropdown using Radix Popover |
| `client/src/components/board/PriorityFilter.tsx` | Priority filter dropdown |
| `client/src/components/board/ViewToggle.tsx` | Board/List toggle buttons |
| `client/src/components/board/FilterChip.tsx` | Removable active filter chip |
| `client/src/components/board/TaskListView.tsx` | Sortable table view |
| `client/src/components/board/TaskListRow.tsx` | Single table row |
| `client/src/components/board/StatusIcon.tsx` | Status icon component for list view |
| `client/src/hooks/useBoardFilters.ts` | Filter state management hook |
| `client/src/components/board/FilterBar.test.tsx` | Tests for filter bar behavior |
| `client/src/components/board/TaskListView.test.tsx` | Tests for list view rendering and sorting |
| `client/src/components/board/StatusIcon.test.tsx` | Tests for status icon mapping |

## Implementation Steps

1. **Create `client/src/hooks/useBoardFilters.ts`**:
   - Manages filter state: `selectedPhases: string[]`, `selectedPriority: string | null`
   - Manages view state: `viewMode: "board" | "list"` persisted via `useLocalStorage("board-view-mode", "board")`
   - Export `useBoardFilters()` returning:
     - `selectedPhases`, `togglePhase(phase: string)`, `clearPhases()`
     - `selectedPriority`, `setPriority(p: string | null)`
     - `viewMode`, `setViewMode(mode: "board" | "list")`
     - `filterTasks(tasks: Task[]): Task[]` — applies active filters to a task array
     - `hasActiveFilters: boolean`
     - `clearAllFilters()`

2. **Create `client/src/components/board/PhaseFilter.tsx`**:
   - Props: `selectedPhases: string[]`, `onToggle: (phase: string) => void`
   - Use `@radix-ui/react-popover` for dropdown
   - Trigger button: "Phase" label with down chevron, shows count when filters active
   - Content: checkbox list of all phases (project, design, plan, build, test, deploy) with colored dots
   - Each phase: `<label>` with checkbox + phase name + colored dot
   - "Clear" link at bottom when any phase selected

3. **Create `client/src/components/board/PriorityFilter.tsx`**:
   - Props: `selectedPriority: string | null`, `onSelect: (priority: string | null) => void`
   - Use `@radix-ui/react-popover` for dropdown
   - Trigger: "Priority" label with down chevron
   - Content: radio-style list: All, P1 (Critical), P2 (High), P3 (Normal)
   - Each option with priority dot color

4. **Create `client/src/components/board/ViewToggle.tsx`**:
   - Props: `viewMode: "board" | "list"`, `onChange: (mode: "board" | "list") => void`
   - Two buttons side by side with border: Board (grid icon `LayoutGrid`), List (list icon `List`)
   - Active button: `bg-[var(--color-primary)] text-white`
   - Inactive button: `bg-white text-gray-600 hover:bg-gray-100`
   - Keyboard accessible: Tab between buttons, Enter/Space to activate

5. **Create `client/src/components/board/FilterChip.tsx`**:
   - Props: `label: string`, `onRemove: () => void`
   - Render: pill with label + X button
   - Styling: `inline-flex items-center gap-1 px-2 py-1 rounded-full bg-gray-200 text-xs`

6. **Create `client/src/components/board/FilterBar.tsx`**:
   - Props: all from `useBoardFilters()` + `onNewIssue` callback
   - Layout: `flex items-center gap-3 px-4 py-2`
   - Left side: `<PhaseFilter />`, `<PriorityFilter />`
   - Center: active filter chips (one per selected phase, one for priority)
   - Right side: `<ViewToggle />`, `<NewIssueButton />`
   - When no filters active, chips area is empty

7. **Create `client/src/components/board/StatusIcon.tsx`**:
   - Props: `status: KanbanStatus`
   - Map:
     - `backlog` -> gray circle outline (`Circle` icon, gray)
     - `in_progress` -> blue filled circle with pulse animation (`CircleDot`, blue)
     - `in_review` -> amber circle (`CircleDashed`, amber)
     - `done` -> green checkmark (`CheckCircle2`, green)
     - `failed` -> red X circle (`XCircle`, red)
     - `cancelled` -> gray slash circle (`MinusCircle`, gray)
   - ARIA label: status name for screen readers

8. **Create `client/src/components/board/TaskListRow.tsx`**:
   - Props: `task: Task`
   - Table row (`<tr>`) with columns:
     - Status: `<StatusIcon status={task.kanbanStatus} />`
     - Title: text, max 1 line with ellipsis
     - Phase: `<PhaseTag phase={task.currentPhase} />`
     - Priority: `<PriorityIndicator priority={task.priority} />`
     - Tests: `{passing}/{total}` or `--`
     - Commit: first 7 chars of commit hash or `--`
     - Updated: relative timestamp (`formatDistanceToNow` pattern — implement simple helper for "2h ago", "1d ago")
   - Row click: `navigate(/tasks/${task.id})`
   - Hover: `hover:bg-gray-50 cursor-pointer`

9. **Create `client/src/components/board/TaskListView.tsx`**:
   - Props: `tasks: Task[]`
   - Sortable columns: state tracks `sortField` and `sortDirection` (asc/desc)
   - Column headers: clickable, show sort indicator arrow on active column
   - Sortable fields: title (alpha), phase (alpha), priority (P1 > P2 > P3), tests (numeric), commit (alpha), updated (date)
   - Table styling: `w-full border-collapse`, header `bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase`
   - Body: render `<TaskListRow />` for each task in sorted order

10. **Update `client/src/pages/KanbanPage.tsx`**:
    - Integrate `useBoardFilters()` hook
    - Replace direct filter bar slot with `<FilterBar />` component
    - Apply `filterTasks(tasks)` before passing to `<KanbanBoard />` or `<TaskListView />`
    - Conditionally render `<KanbanBoard />` when `viewMode === "board"` or `<TaskListView />` when `viewMode === "list"`

11. **Create relative time utility** in `client/src/lib/formatTime.ts`:
    - Export `formatRelativeTime(dateString: string): string`
    - Returns: "just now" (< 1 min), "Xm ago", "Xh ago", "Xd ago", "Xw ago"
    - No dependency on date-fns — simple math on Date.now() difference

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/components/board/FilterBar.test.tsx` | Renders all filter controls; chips appear for active filters |
| `client/src/components/board/TaskListView.test.tsx` | Table renders all rows; click header sorts; row click navigates |
| `client/src/components/board/StatusIcon.test.tsx` | Correct icon per status; ARIA labels present |

### Test Details

- **FilterBar**: Render with no filters active, assert Phase and Priority dropdowns visible. Open Phase dropdown, select "build", assert filter chip appears. Assert ViewToggle shows Board as active.
- **TaskListView**: Render with 5 mock tasks. Assert 5 rows visible. Click "Title" header, assert rows sorted alphabetically. Click again, assert reverse sort. Click a row, assert navigation called.
- **StatusIcon**: Render for each KanbanStatus value. Assert correct icon element. Assert `aria-label` present.
- **useBoardFilters**: Use `renderHook`. Toggle phase "build", assert `selectedPhases` includes "build". Call `filterTasks` with mixed tasks, assert only matching tasks returned. Assert `viewMode` persisted to localStorage.

## Dependencies

- **Section 04** — `KanbanBoard`, `TaskCard`, `KanbanPage` (updated with filter integration)

## Acceptance Criteria

From spec:
- [ ] Phase filter dropdown allows multi-select of phases
- [ ] Priority filter allows selection of priority levels
- [ ] Filters apply immediately to visible board/list
- [ ] Active filters shown as removable chips/pills
- [ ] Clearing all filters restores full view
- [ ] Board and List toggle buttons render in filter bar
- [ ] Active view visually highlighted
- [ ] View preference persists in localStorage across reloads
- [ ] Table renders all tasks matching current filters
- [ ] Clicking column header sorts table (toggle asc/desc)
- [ ] Status icon column matches board card status icons
- [ ] Phase tag column shows colored pills
- [ ] Updated column shows relative timestamps
- [ ] Row click navigates to Task Detail view
