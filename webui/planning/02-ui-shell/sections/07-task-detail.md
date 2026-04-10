# Section 07: Task Detail Page Layout

## Goal

Build the Task Detail page: a header bar with back navigation and task metadata, a resizable two-panel layout (Chat ~60% left, Smart Viewer slot ~40% right), and the Smart Viewer empty placeholder with a tab management API surface for Split 03 to plug into. Panel widths are persisted in localStorage and adjustable via a drag handle.

## FRs Covered

- **FR-02.21** — Clicking a card navigates to Task Detail, sidebar remains visible.
- **FR-02.22** — Task header: title, phase tag, priority, status, "Back to Board" button.
- **FR-02.23** — Two-panel layout: Chat (~60%) and Smart Viewer slot (~40%).
- **FR-02.24** — Smart Viewer as empty slot with placeholder and tab management API for Split 03.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/pages/TaskDetailPage.tsx` | Task Detail page container (replaces placeholder) |
| `client/src/components/detail/TaskHeader.tsx` | Header bar: back button, title, phase, priority, status |
| `client/src/components/detail/PanelLayout.tsx` | Resizable two-panel layout with drag handle |
| `client/src/components/detail/ViewerSlot.tsx` | Empty Smart Viewer placeholder + tab API |
| `client/src/components/detail/DragHandle.tsx` | Vertical drag handle between panels |
| `client/src/hooks/usePanelResize.ts` | Panel resize logic with localStorage persistence |
| `client/src/pages/TaskDetailPage.test.tsx` | Integration test: page renders with task data |
| `client/src/components/detail/TaskHeader.test.tsx` | Tests for header rendering and back navigation |
| `client/src/components/detail/PanelLayout.test.tsx` | Tests for panel layout and resize |
| `client/src/components/detail/ViewerSlot.test.tsx` | Tests for placeholder and tab API |

## Implementation Steps

1. **Create `client/src/hooks/usePanelResize.ts`**:
   - Export `usePanelResize(storageKey: string, defaultLeftPercent: number)`:
     - `leftPercent: number` — current left panel width as percentage (0-100)
     - `isDragging: boolean` — true during drag
     - `handleMouseDown: (e: React.MouseEvent) => void` — starts drag
   - Implementation:
     - Read initial `leftPercent` from localStorage (fallback to `defaultLeftPercent`)
     - On mousedown: set `isDragging = true`
     - On mousemove (global listener, added on mousedown): calculate new percentage from mouse X relative to container
     - On mouseup: set `isDragging = false`, persist to localStorage
     - Clamp: min 30%, max 80% (Chat min 400px equivalent, Viewer min 200px equivalent)
     - Clean up global listeners on unmount
     - Apply `user-select: none` on body during drag to prevent text selection

2. **Create `client/src/components/detail/DragHandle.tsx`**:
   - Props: `onMouseDown: (e: React.MouseEvent) => void`, `isDragging: boolean`
   - Render: vertical bar between panels
   - Styling: `w-1.5 cursor-col-resize hover:bg-[var(--color-primary)]/20 transition-colors flex items-center justify-center`
   - Visual indicator: three small dots stacked vertically (`GripVertical` icon from lucide)
   - Active state when dragging: `bg-[var(--color-primary)]/30`

3. **Create `client/src/components/detail/TaskHeader.tsx`**:
   - Props: `task: Task`
   - Layout: `flex items-center gap-4 px-4 py-3 border-b bg-white`
   - "Back to Board" button:
     - `<button onClick={() => navigate(-1)}>` with `ArrowLeft` icon + "Back to Board" text
     - Styling: `flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900`
   - Task title: `text-lg font-semibold text-gray-900`
   - Phase tag: `<PhaseTag phase={task.currentPhase} />`
   - Priority: `<PriorityIndicator priority={task.priority} />`
   - Status badge: `<StatusIcon status={task.kanbanStatus} />` + status text
   - All metadata elements flex-wrap for narrow viewports

4. **Create `client/src/components/detail/ViewerSlot.tsx`**:
   - Props: none (self-contained)
   - **Tab management API** (exposed via context or ref for Split 03):
     ```typescript
     interface ViewerTab {
       id: string;
       filePath: string;
       label: string;
     }
     
     interface ViewerSlotAPI {
       openTab: (file: { path: string; label: string }) => void;
       closeTab: (id: string) => void;
       activeTab: ViewerTab | null;
       tabs: ViewerTab[];
     }
     ```
   - Export `ViewerSlotContext` — React context providing the API
   - Export `useViewerSlot()` hook for consumers
   - Internal state: `tabs: ViewerTab[]`, `activeTabId: string | null`
   - Render:
     - Tab bar (top): shows open tabs, click to switch, X to close (hidden when no tabs)
     - Content area: when no tabs, show placeholder: centered icon (`FileSearch` from lucide) + "Select a file to view here" text in muted gray
     - When tabs exist but renderers are not yet available (Split 03): show file path text as placeholder
   - Styling: `h-full flex flex-col bg-white rounded-l-xl border-l`

5. **Create `client/src/components/detail/PanelLayout.tsx`**:
   - Props: `leftPanel: ReactNode`, `rightPanel: ReactNode`
   - Uses `usePanelResize("task-detail-panels", 60)` for resize logic
   - Layout: `flex h-full` container
     - Left panel: `style={{ width: '${leftPercent}%' }}`, `overflow-hidden`
     - `<DragHandle />` between panels
     - Right panel: `style={{ width: '${100 - leftPercent}%' }}`, `overflow-hidden`
   - During drag: both panels get `pointer-events-none` to prevent iframe/selection issues

6. **Create `client/src/pages/TaskDetailPage.tsx`** (replace placeholder):
   - Read `taskId` from URL params via `useParams()`
   - Need `projectId` — either from URL or from task data. Strategy: URL includes projectId or derive from task lookup
   - Fetch task via `useTask(projectId, taskId)` (from Section 03)
   - Layout:
     ```
     <div className="flex flex-col h-full">
       <TaskHeader task={task} />
       <PanelLayout
         leftPanel={<div className="p-4">Chat placeholder — Section 08</div>}
         rightPanel={<ViewerSlot />}
       />
     </div>
     ```
   - Loading state: skeleton header + empty panels
   - Error state: "Task not found" message with back button
   - The chat panel content is a placeholder div replaced in Section 08

7. **Update router** in `client/src/router.tsx`:
   - Ensure route for task detail includes projectId: `"projects/:projectId/tasks/:taskId"` OR use a flat `"tasks/:taskId"` with task data providing the projectId
   - Decision: use `"tasks/:taskId"` for cleaner URLs. The TaskDetailPage fetches the task and derives projectId from the response. Add a `useTaskLookup` helper that finds the task across all projects if needed.

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/pages/TaskDetailPage.test.tsx` | Page renders header + two panels; loading/error states |
| `client/src/components/detail/TaskHeader.test.tsx` | All metadata renders; back button navigates |
| `client/src/components/detail/PanelLayout.test.tsx` | Two panels render; drag handle present |
| `client/src/components/detail/ViewerSlot.test.tsx` | Placeholder shown; tab API works (open/close/switch) |

### Test Details

- **TaskDetailPage**: Wrap in QueryClientProvider + MemoryRouter with initial entry `/tasks/task-1`. MSW returns mock task. Assert TaskHeader, chat placeholder, and ViewerSlot all render. Test error: MSW returns 404, assert "Task not found" message.
- **TaskHeader**: Render with mock task. Assert title, phase tag, priority, status all visible. Click "Back to Board", assert `navigate(-1)` called.
- **PanelLayout**: Render with two div children. Assert both divs visible. Assert DragHandle element present between them. (Full drag interaction tested via integration test if needed.)
- **ViewerSlot**: Render in isolation. Assert placeholder text "Select a file to view here" visible. Use `ViewerSlotContext` to call `openTab`, assert tab bar appears with file label.

## Dependencies

- **Section 02** — MainLayout, router, sidebar (remains visible)
- **Section 03** — `useTask`, data hooks, SSE integration

## Acceptance Criteria

From spec:
- [ ] Clicking a card navigates to Task Detail (URL changes to /tasks/:id)
- [ ] Sidebar remains visible and functional in Task Detail view
- [ ] Board content area fully replaced by Task Detail layout
- [ ] Browser back button returns to Kanban Dashboard
- [ ] Task title renders prominently in header
- [ ] Phase tag, priority, and status render alongside title
- [ ] "Back to Board" button visible at left of header
- [ ] Clicking "Back to Board" returns to Dashboard (preserving filter/tab state)
- [ ] Chat panel occupies ~60% of available width (left)
- [ ] Smart Viewer slot occupies ~40% of available width (right)
- [ ] Drag handle between panels allows resizing
- [ ] Panel widths persisted in localStorage
- [ ] Smart Viewer shows placeholder "Select a file to view here"
- [ ] ViewerSlot exposes tab management API (openTab, closeTab, activeTab)
