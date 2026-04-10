# Section 04: Kanban Board — Columns, Cards & Real-Time Updates

## Goal

Build the Kanban Dashboard as the default home screen: project tabs for filtering, four columns (Backlog, In Progress, In Review, Done) with equal flex widths, task cards showing title, phase tag, priority, test count, and commit hash, a card overflow menu with Close/Cancel actions, and real-time auto-updates via SSE. Cards are NOT draggable — Claude controls movement via pipeline events.

## FRs Covered

- **FR-02.05** — Project tabs at top of board: one per project + "All" tab (default).
- **FR-02.06** — Four columns: Backlog, In Progress, In Review, Done.
- **FR-02.07** — Task cards: title, phase tag (colored pill), priority, test count badge, commit hash.
- **FR-02.08** — Phase tag colors: project=gray, design=purple, plan=blue, build=orange, test=green, deploy=teal.
- **FR-02.09** — Auto-update via SSE: new cards appear, status changes move cards, phase tags update.
- **FR-02.10** — "..." overflow menu on each card with Close and Cancel.
- **FR-02.11** — "+ New Issue" button in top-right area (button only; modal in Section 05).
- **FR-02.12** — NO drag-and-drop.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/pages/KanbanPage.tsx` | Board page: project tabs + filter bar + board/list toggle area |
| `client/src/components/board/ProjectTabs.tsx` | Horizontal tab bar: "All" + one tab per project |
| `client/src/components/board/KanbanBoard.tsx` | Four-column flex layout |
| `client/src/components/board/KanbanColumn.tsx` | Single column: header (name + count) + card list |
| `client/src/components/board/TaskCard.tsx` | Card component with all metadata fields |
| `client/src/components/board/PhaseTag.tsx` | Colored pill component for phase name |
| `client/src/components/board/PriorityIndicator.tsx` | Priority dot (P1=red, P2=amber, P3=gray) |
| `client/src/components/board/CardOverflowMenu.tsx` | Radix DropdownMenu: Close + Cancel actions |
| `client/src/components/board/NewIssueButton.tsx` | "+ New Issue" button (click handler wired in Section 05) |
| `client/src/pages/KanbanPage.test.tsx` | Integration test: board renders with mock data |
| `client/src/components/board/TaskCard.test.tsx` | Unit test: card rendering, overflow menu |
| `client/src/components/board/PhaseTag.test.tsx` | Unit test: correct colors per phase |
| `client/src/components/board/ProjectTabs.test.tsx` | Unit test: tab rendering, selection |
| `client/src/components/board/KanbanColumn.test.tsx` | Unit test: column header, empty state |

## Implementation Steps

1. **Create `client/src/components/board/PhaseTag.tsx`**:
   - Props: `phase: string`
   - Map phase to color using CSS custom properties:
     ```typescript
     const PHASE_COLORS: Record<string, string> = {
       project: 'bg-gray-400',
       design: 'bg-purple-500',
       plan: 'bg-blue-500',
       build: 'bg-orange-500',
       test: 'bg-green-500',
       deploy: 'bg-teal-500',
     };
     ```
   - Render: `<span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium text-white {colorClass}">{phase}</span>`
   - Fallback for unknown phases: `bg-gray-400`

2. **Create `client/src/components/board/PriorityIndicator.tsx`**:
   - Props: `priority?: string`
   - Return `null` when `priority` is undefined/null
   - Map: `P1` -> red dot + "P1", `P2` -> amber dot + "P2", `P3` -> gray dot + "P3"
   - Render: `<span className="flex items-center gap-1 text-xs"><span className="w-2 h-2 rounded-full {dotColor}" />{label}</span>`

3. **Create `client/src/components/board/CardOverflowMenu.tsx`**:
   - Props: `taskId: string`, `projectId: string`, `onClose: () => void`, `onCancel: () => void`
   - Use `@radix-ui/react-dropdown-menu` for accessibility
   - Trigger: `<button aria-label="Task actions">...</button>` (three dots, `MoreHorizontal` icon from lucide)
   - Menu items: "Close" (calls PATCH to update task status to done), "Cancel" (calls PATCH to update task status to cancelled)
   - Menu closes on outside click or Escape (Radix handles this)
   - Use `useMutation` for Close/Cancel API calls, invalidate task queries on success

4. **Create `client/src/components/board/TaskCard.tsx`**:
   - Props: `task: Task`
   - Card container: `bg-white rounded-xl shadow-[var(--shadow-card)] p-3 cursor-pointer hover:shadow-md transition-shadow group`
   - Layout:
     - Top row: title (14px semibold, max 2 lines, `line-clamp-2`) + overflow menu (visible on hover via `opacity-0 group-hover:opacity-100`)
     - Middle row: `<PhaseTag phase={task.currentPhase} />` + `<PriorityIndicator priority={task.priority} />`
     - Bottom row: test count badge (`Tests: {passing}/{total}` or `--`) + commit hash (first 7 chars or `--`)
   - Click handler: `navigate(`/tasks/${task.id}`)` via `useNavigate()`
   - NO drag attributes, NO draggable (FR-02.12)

5. **Create `client/src/components/board/KanbanColumn.tsx`**:
   - Props: `title: string`, `tasks: Task[]`, `status: KanbanStatus`
   - Header: column name (semibold, 14px) + count badge (`tasks.length`)
   - Body: `<ScrollArea>` from Radix wrapping a flex column of `<TaskCard />` components
   - Empty state: subtle text "No tasks" in gray, centered
   - Container: `flex-1 min-w-[200px] flex flex-col bg-gray-50/50 rounded-xl p-3 gap-2`

6. **Create `client/src/components/board/KanbanBoard.tsx`**:
   - Props: `tasks: Task[]`
   - Group tasks by `kanbanStatus` into four buckets: `backlog`, `in_progress`, `in_review`, `done`
   - Render four `<KanbanColumn />` components in a horizontal flex container: `flex gap-4 flex-1 overflow-x-auto`
   - Column order: Backlog, In Progress, In Review, Done
   - Done column: if more than 10 tasks, show only 10 most recent with a "Show all ({count})" toggle

7. **Create `client/src/components/board/ProjectTabs.tsx`**:
   - Props: `projects: Project[]`, `activeProjectId: string | null`, `onSelect: (projectId: string | null) => void`
   - Use `@radix-ui/react-tabs` for accessible tab UI
   - Render "All" tab first (value `null`), then one tab per project (value = `project.id`)
   - Active tab: bottom border accent (`border-b-2 border-[var(--color-primary)]`)
   - Tabs container: `overflow-x-auto whitespace-nowrap` for scrolling when many projects
   - Tab item: `px-4 py-2 text-sm font-medium cursor-pointer`

8. **Create `client/src/components/board/NewIssueButton.tsx`**:
   - Props: `onClick: () => void`
   - Render: `<button>+ New Issue</button>` styled as primary CTA
   - Styling: `bg-[var(--color-primary)] text-white px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90`
   - Click handler passed from parent (wired to modal in Section 05)

9. **Create `client/src/pages/KanbanPage.tsx`** (replace placeholder):
   - State: `activeProjectId: string | null` (default `null` = All)
   - Fetch projects via `useProjects()`
   - Fetch tasks via `useTasks(activeProjectId)` — when `null`, fetch all
   - Connect SSE via `useSSE(activeProjectId)` (already in MainLayout, but page can scope)
   - Layout:
     ```
     <div className="flex flex-col h-full">
       <div className="flex items-center justify-between p-4 border-b">
         <ProjectTabs projects={projects} activeProjectId={activeProjectId} onSelect={setActiveProjectId} />
         <div className="flex items-center gap-2">
           {/* Filter bar slot — Section 06 */}
           <NewIssueButton onClick={() => {/* Section 05 */}} />
         </div>
       </div>
       <div className="flex-1 p-4 overflow-hidden">
         <KanbanBoard tasks={tasks} />
       </div>
     </div>
     ```
   - Loading state: skeleton cards in columns
   - Error state: error message with retry button

10. **Real-time updates** (FR-02.09): No extra code needed in this section — `useSSE` (from Section 03) already invalidates task queries on `task:created` and `task:updated` events. TanStack Query automatically re-fetches and React re-renders with new data. Cards appear/move/update within the Query refetch cycle (< 2 seconds per QR-02.03).

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/components/board/PhaseTag.test.tsx` | Correct color class per phase; fallback for unknown phase |
| `client/src/components/board/TaskCard.test.tsx` | All metadata fields render; overflow menu opens; click navigates |
| `client/src/components/board/ProjectTabs.test.tsx` | All tabs render; "All" selected by default; tab click triggers onSelect |
| `client/src/components/board/KanbanColumn.test.tsx` | Column header shows name + count; empty state message; cards render |
| `client/src/pages/KanbanPage.test.tsx` | Full board renders with mock tasks in correct columns; project tab filtering |

### Test Details

- **PhaseTag**: Render for each phase name, assert correct background color class. Render with "unknown" phase, assert fallback color.
- **TaskCard**: Render with a full Task object. Assert title, phase tag, priority dot, test count, and commit hash all appear. Simulate hover, assert overflow menu becomes visible. Click the card, assert `navigate` was called.
- **ProjectTabs**: Render with 3 mock projects. Assert "All" + 3 project tabs visible. Click "Project B" tab, assert `onSelect` called with that project's ID.
- **KanbanColumn**: Render with 3 tasks, assert 3 cards + header "Backlog (3)". Render with 0 tasks, assert "No tasks" placeholder.
- **KanbanPage**: Wrap in QueryClientProvider + MemoryRouter. MSW returns mock projects and tasks. Assert 4 columns render. Assert tasks appear in correct columns based on `kanbanStatus`.

## Dependencies

- **Section 02** — MainLayout, router, page structure
- **Section 03** — `useProjects`, `useTasks`, `useSSE` hooks, query keys

## Acceptance Criteria

From spec:
- [ ] One tab renders per registered project; "All" tab first and selected by default
- [ ] Selecting a project tab filters board to that project's tasks
- [ ] Four columns render: Backlog, In Progress, In Review, Done
- [ ] Each column header shows name and task count
- [ ] Columns fill available space equally (flex)
- [ ] Empty columns show placeholder message
- [ ] Card displays title (truncated 2 lines), phase tag (colored pill), priority, test count, commit hash
- [ ] Phase tags colored: project=gray, design=purple, plan=blue, build=orange, test=green, deploy=teal
- [ ] New cards appear within 2 seconds of SSE event
- [ ] Cards move between columns on status change via SSE
- [ ] Phase tags update on phase change via SSE
- [ ] No full page reload for any card update
- [ ] "..." button appears on card hover
- [ ] Overflow menu has Close and Cancel options
- [ ] Close/Cancel send API requests
- [ ] Menu closes on outside click or Escape
- [ ] "+ New Issue" button visible in top-right area
- [ ] NO drag-and-drop on cards
