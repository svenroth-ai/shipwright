# Section 02: App Shell, Sidebar Navigation & Routing

## Goal

Build the persistent application shell: a 200px sidebar navigation on the left with icon + text labels, React Router for view switching, and a main content area that fills the remaining viewport width. The sidebar renders on every page (Kanban Dashboard and Task Detail), highlights the active item, shows a real-time inbox badge count via SSE, and collapses to icon-only on narrow viewports.

## FRs Covered

- **FR-02.01** — Persistent sidebar-nav (~200px) with icon + text labels for: Task Board, Projects, Inbox (with badge), Settings.
- **FR-02.02** — Active sidebar item highlighted with visual accent (background + left border).
- **FR-02.03** — Real-time badge count on Inbox item, updated via SSE events.
- **FR-02.04** — Sidebar collapses to icon-only below 768px viewport width with hamburger toggle.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/layouts/MainLayout.tsx` | App shell: sidebar + `<Outlet />` content area |
| `client/src/components/sidebar/SidebarNav.tsx` | Sidebar container with nav items + responsive collapse |
| `client/src/components/sidebar/SidebarNavItem.tsx` | Single nav item: icon + label, active state |
| `client/src/components/sidebar/InboxBadge.tsx` | Red badge with count, supports 1-99 and "99+" |
| `client/src/router.tsx` | React Router configuration with all routes |
| `client/src/pages/KanbanPage.tsx` | Placeholder page for Kanban Dashboard (replaced in Section 04) |
| `client/src/pages/TaskDetailPage.tsx` | Placeholder page for Task Detail (replaced in Section 07) |
| `client/src/layouts/MainLayout.test.tsx` | Tests for layout rendering |
| `client/src/components/sidebar/SidebarNav.test.tsx` | Tests for sidebar nav behavior |
| `client/src/components/sidebar/InboxBadge.test.tsx` | Tests for badge rendering |

## Implementation Steps

1. **Create `client/src/router.tsx`** with React Router v7 `createBrowserRouter`:
   - Root route: `"/"` with `<MainLayout />` as the element (wraps all views)
   - Index route: `""` rendering `<KanbanPage />`
   - Route: `"tasks/:taskId"` rendering `<TaskDetailPage />`
   - Route: `"projects"` rendering placeholder `<div>Projects</div>`
   - Route: `"inbox"` rendering placeholder `<div>Inbox</div>`
   - Route: `"settings"` rendering placeholder `<div>Settings</div>`
   - Export the router and update `App.tsx` to use `<RouterProvider router={router} />`

2. **Update `client/src/App.tsx`** to:
   - Import and render `<RouterProvider router={router} />`
   - Keep `<QueryClientProvider>` wrapping

3. **Create `client/src/layouts/MainLayout.tsx`**:
   - Flex container: `flex h-screen overflow-hidden`
   - Left: `<SidebarNav />`
   - Right: `<main>` with `<Outlet />` from React Router, `flex-1 overflow-auto bg-[var(--color-background)]`
   - No padding on main — individual pages control their own padding

4. **Create `client/src/components/sidebar/SidebarNav.tsx`**:
   - Container: `w-[200px] min-w-[200px] h-screen bg-white border-r border-gray-200 flex flex-col`
   - Top section: logo/brand area with "Shipwright" text (16px Inter semibold, primary color)
   - Nav items section: `flex-1 flex flex-col gap-1 py-4 px-3`
   - Items (using `<SidebarNavItem />`):
     - Task Board — `LayoutDashboard` icon from lucide-react, path `/`
     - Projects — `FolderOpen` icon, path `/projects`
     - Inbox — `Inbox` icon, path `/inbox`, with `<InboxBadge />`
   - Bottom section (separated with top border): Settings — `Settings` icon, path `/settings`
   - **Responsive collapse** (FR-02.04):
     - Track `collapsed` state, default based on `window.innerWidth < 768`
     - Listen to `resize` event (debounced) to auto-collapse/expand
     - When collapsed: `w-[60px] min-w-[60px]`, hide text labels, show icons only
     - Hamburger button visible in collapsed mode to manually expand
     - Use `useMediaQuery` pattern or direct `matchMedia` listener

5. **Create `client/src/components/sidebar/SidebarNavItem.tsx`**:
   - Props: `icon: LucideIcon`, `label: string`, `to: string`, `badge?: ReactNode`, `collapsed?: boolean`
   - Use `NavLink` from React Router for active detection
   - Active state (FR-02.02): `bg-[var(--color-primary)]/10 border-l-[3px] border-[var(--color-primary)]`
   - Inactive state: `hover:bg-gray-100 border-l-[3px] border-transparent`
   - Layout: `flex items-center gap-3 px-3 py-2 rounded-r-lg text-sm`
   - Icon: 20px, `text-gray-600` (inactive) or `text-[var(--color-primary)]` (active)
   - Label: `text-gray-700 font-medium`, hidden when `collapsed` is true
   - Badge slot: rendered after label when provided

6. **Create `client/src/components/sidebar/InboxBadge.tsx`**:
   - Props: `count: number`
   - Render nothing when `count === 0`
   - Render `count` when `1 <= count <= 99`
   - Render `"99+"` when `count > 99`
   - Styling: `min-w-[18px] h-[18px] rounded-full bg-red-500 text-white text-[11px] font-semibold flex items-center justify-center px-1`
   - **Real-time updates** (FR-02.03): The `SidebarNav` component connects to the inbox count via `useInbox()` hook (from Section 03). For now, accept a `count` prop — the hook integration happens when Section 03 is complete.

7. **Create placeholder pages**:
   - `client/src/pages/KanbanPage.tsx`: returns `<div className="p-6"><h1>Task Board</h1></div>` — replaced in Section 04
   - `client/src/pages/TaskDetailPage.tsx`: reads `taskId` from params, returns `<div className="p-6"><h1>Task {taskId}</h1></div>` — replaced in Section 07

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/layouts/MainLayout.test.tsx` | Sidebar renders alongside content area; Outlet content visible |
| `client/src/components/sidebar/SidebarNav.test.tsx` | All 4 nav items render; active item highlighted; collapse behavior |
| `client/src/components/sidebar/InboxBadge.test.tsx` | Badge hidden at 0; shows count 1-99; shows "99+" above 99 |

### Test Details

- **MainLayout**: Render within `MemoryRouter`, assert sidebar and main content area both present.
- **SidebarNav**: Render with `MemoryRouter` at `/`, assert "Task Board" item has active class. Navigate to `/inbox`, assert "Inbox" is active. Test collapse: mock `matchMedia` to return `matches: true` for `(max-width: 768px)`, assert labels hidden.
- **InboxBadge**: Render with `count={0}` — no element. Render with `count={5}` — shows "5". Render with `count={100}` — shows "99+".

## Dependencies

- **Section 01** — Vite project scaffold, React 19, TailwindCSS 4, dependencies installed

## Acceptance Criteria

From spec:
- [ ] Sidebar renders at ~200px width on the left edge of the viewport
- [ ] Four items visible: Task Board (board icon), Projects (folder icon), Inbox (inbox icon), Settings (gear icon)
- [ ] Sidebar remains visible when navigating between Kanban Dashboard and Task Detail
- [ ] Clicking Task Board navigates to the Kanban Dashboard
- [ ] Active sidebar item has accent background and left border
- [ ] Inbox item shows numeric badge (1-99) when unanswered items exist
- [ ] Badge shows "99+" when count exceeds 99
- [ ] Badge disappears when count reaches 0
- [ ] Sidebar collapses to icon-only below 768px viewport width
- [ ] Hamburger toggle available in collapsed mode to expand sidebar
