# UI Shell: Kanban Board & Task Detail

> Split 02 of 03 | Source: Spec/plan-shipwright-webui.md (Kanban pivot)

## 1. Purpose & Scope

This split delivers the complete frontend shell for the Shipwright Command Center: a Kanban-first UI with two main views. The **Kanban Dashboard** is the default home screen showing task cards organized in columns (Backlog, In Progress, In Review, Done). The **Task Detail** view opens when clicking a card and provides a Chat + Smart Viewer side-by-side layout. A persistent sidebar-nav provides navigation between views. Cards auto-update via SSE and are moved by Claude automatically — there is no drag-and-drop.

**In scope:**
- Sidebar-Nav (200px, persistent on both views)
- Kanban Dashboard: project tabs, filter bar, board columns, task cards, list view toggle
- New Issue flow: modal, immediate card creation, background auto-classify
- Task Detail: two-panel layout (Chat left, Smart Viewer slot right)
- Chat Engine: streaming messages, tool-call cards, diff view, AskUserQuestion cards
- Chat input toolbar: model selector, permission mode, effort, autonomy, / commands, @ files
- Card auto-update via SSE (status changes, new cards, enrichment)
- Phase-to-status mapping (configurable per project)

**Out of scope:**
- Smart Viewer file renderers (Split 03)
- File Explorer tree implementation (Split 03)
- New Project Wizard step-by-step flow (Split 03)
- Settings page implementation (Split 03)
- Global Inbox page content (Split 03)
- Intent Detection Banner (Split 03)

## 2. Functional Requirements

### Group: Sidebar Navigation

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.01 | SHALL | The system shall render a persistent sidebar-nav (~200px, left edge) with icon + text labels for: Task Board, Projects, Inbox (with badge count), Settings. | Primary navigation between views; always visible on both Kanban and Task Detail. |
| FR-02.02 | SHALL | The system shall highlight the active sidebar-nav item with a visual accent (background or left border). | User must know which view is currently active. |
| FR-02.03 | SHALL | The system shall display a real-time badge count on the Inbox item, updated via SSE events reflecting unanswered AskUserQuestion items. | Users need at-a-glance awareness of pending questions across all projects. |
| FR-02.04 | SHOULD | The system should collapse the sidebar-nav to icon-only mode when viewport width drops below 768px, with a hamburger toggle to expand it. | Ensures usability on smaller screens without losing navigation access. |

**Acceptance Criteria — FR-02.01:**
- [ ] Sidebar renders at ~200px width on the left edge of the viewport
- [ ] Four items visible: Task Board (board icon), Projects (folder icon), Inbox (inbox icon), Settings (gear icon)
- [ ] Sidebar remains visible when navigating between Kanban Dashboard and Task Detail
- [ ] Clicking Home navigates to the Kanban Dashboard

**Acceptance Criteria — FR-02.03:**
- [ ] Inbox item shows a numeric badge (1-99) when unanswered items exist
- [ ] Badge shows "99+" when count exceeds 99
- [ ] Badge disappears when count reaches 0
- [ ] Badge count updates in real-time via SSE `ask_user_question` and `inbox_answered` events

---

### Group: Kanban Board

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.05 | SHALL | The system shall render project tabs at the top of the board area, one tab per registered project plus an "All" tab for cross-project view, with "All" as the default. | Users manage multiple projects and need to switch context or see everything at once. |
| FR-02.06 | SHALL | The system shall render the Kanban board with four columns: Backlog, In Progress, In Review, Done. | Core board layout matching the Shipwright pipeline lifecycle. |
| FR-02.07 | SHALL | The system shall render task cards within columns showing: title, phase tag (colored pill), priority indicator, test count badge, and commit hash (truncated). | Cards must provide at-a-glance information about each task without opening it. |
| FR-02.08 | SHALL | The system shall color phase tags per phase: project=gray, design=purple, plan=blue, build=orange, test=green, deploy=teal. | Consistent color-coding enables instant phase recognition across the board. |
| FR-02.09 | SHALL | The system shall auto-update cards in real-time via SSE: new cards appear, status changes move cards between columns, phase tags update. | Claude moves cards automatically — the board must reflect changes without manual refresh. |
| FR-02.10 | SHALL | The system shall display a "..." overflow menu on each card with Close and Cancel options. | Users need lightweight task management actions without opening the full detail view. |
| FR-02.11 | SHALL | The system shall display a prominent "+ New Issue" button in the top-right area of the board. | Primary entry point for creating new work items. |
| FR-02.12 | SHALL | The system shall NOT support drag-and-drop reordering or column movement of cards. | Claude controls card movement via pipeline events; manual drag would conflict with automated state. |

**Acceptance Criteria — FR-02.05:**
- [ ] One tab renders per registered project, showing the project name
- [ ] "All" tab renders first (or leftmost) and is selected by default
- [ ] Selecting a project tab filters the board to show only that project's tasks
- [ ] "All" tab shows tasks from all projects, grouped into the same four columns

**Acceptance Criteria — FR-02.06:**
- [ ] Four columns render horizontally: Backlog, In Progress, In Review, Done
- [ ] Each column header shows the column name and a task count
- [ ] Columns fill available horizontal space equally (flex layout)
- [ ] Empty columns show a subtle placeholder message

**Acceptance Criteria — FR-02.07:**
- [ ] Card displays task title (truncated at 2 lines with ellipsis)
- [ ] Phase tag renders as a colored pill with phase name
- [ ] Priority indicator renders (icon or colored dot) when priority is set
- [ ] Test count badge shows number of passing/total tests when available
- [ ] Commit hash shows first 7 characters when available

**Acceptance Criteria — FR-02.09:**
- [ ] New task cards appear in the correct column within 2 seconds of SSE event
- [ ] Cards move between columns when status changes arrive via SSE
- [ ] Phase tags update on cards when phase changes arrive via SSE
- [ ] No full page reload required for any card update

**Acceptance Criteria — FR-02.10:**
- [ ] "..." button appears on card hover or always visible on mobile
- [ ] Clicking "..." opens a dropdown menu with Close and Cancel options
- [ ] Close sends a status update to the backend API
- [ ] Cancel sends a cancellation request to the backend API
- [ ] Menu closes on outside click or Escape

---

### Group: New Issue

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.13 | SHALL | The system shall open a modal dialog with Title, Description, and a "Start immediately" checkbox (default off) when the user clicks "+ New Issue". | Minimal friction for creating new tasks. Start-immediately allows power users to skip the Backlog triage step. |
| FR-02.13a | SHALL | The system shall create the card in Backlog (default) and NOT spawn a Claude process unless "Start immediately" is checked. When checked, the card is created and Claude starts immediately. | Users can batch-create multiple tasks in Backlog, review/prioritize them, then start them individually — no need for multiple windows. |
| FR-02.13b | SHALL | The system shall display a "Start" button on each Backlog card that spawns the Claude CLI process and moves the card to In Progress. | Explicit user control over when work begins. Replaces the need for multiple terminal sessions. |
| FR-02.14 | SHALL | The system shall create a card immediately in the Backlog column upon modal submission, before classification completes. | Instant feedback — the user sees their issue appear immediately. |
| FR-02.15 | SHALL | The system shall trigger background auto-classification via POST /api/projects/:id/classify after card creation, enriching the card with intent badge, complexity, and FR links. | Automatic enrichment reduces manual triage work. |
| FR-02.16 | SHALL | The system shall auto-enrich the card in-place when classification results arrive (intent badge appears, complexity indicator, FR links), without requiring user action. | Seamless enrichment — the card evolves from bare to fully classified. |

**Acceptance Criteria — FR-02.13:**
- [ ] Modal opens centered on screen with overlay backdrop
- [ ] Title field is required, Description field is optional
- [ ] "Start immediately" checkbox is visible, default unchecked
- [ ] Modal closes on Escape, backdrop click, or Cancel button
- [ ] Submit button is disabled when Title is empty

**Acceptance Criteria — FR-02.13a:**
- [ ] When "Start immediately" is unchecked: card goes to Backlog, no Claude process spawned
- [ ] When "Start immediately" is checked: card goes to Backlog, then immediately moves to In Progress with Claude process spawned
- [ ] Multiple tasks can be created in Backlog without starting any

**Acceptance Criteria — FR-02.13b:**
- [ ] Backlog cards show a "Start" button (play icon) visible on hover or always
- [ ] Clicking "Start" spawns the Claude CLI process for this task
- [ ] Card transitions from Backlog to In Progress after Start
- [ ] Start button is not shown on cards in other columns (In Progress, In Review, Done)
- [ ] If a project tab is selected, the issue is created for that project; if "All" is selected, a project selector appears in the modal

**Acceptance Criteria — FR-02.14:**
- [ ] Card appears in Backlog within 500ms of modal submission
- [ ] Card initially shows title only (no phase tag, no classification data)
- [ ] A subtle loading indicator (spinner or shimmer) signals pending classification

**Acceptance Criteria — FR-02.15:**
- [ ] POST /api/projects/:id/classify is called after task creation
- [ ] Classification runs asynchronously — modal is already closed
- [ ] If classification fails, card remains in Backlog with title only (graceful degradation)

**Acceptance Criteria — FR-02.16:**
- [ ] Intent badge (fix/feat/chg) appears on the card after classification
- [ ] Complexity indicator appears after classification
- [ ] FR links appear as tooltip or expandable detail after classification
- [ ] Card update is animated (fade-in of new elements)

---

### Group: Filter & View

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.17 | SHALL | The system shall provide a filter bar above the board with a phase filter dropdown (multi-select) and a priority filter. | Users need to narrow the board to specific phases or priorities during focused work. |
| FR-02.18 | SHALL | The system shall provide a view toggle in the filter bar to switch between Board view and List view. | Different users and tasks benefit from different visualizations. |
| FR-02.19 | SHALL | The system shall render a List view as a table with columns: Status icon, Title, Phase tag, Priority, Tests, Commit, Updated — with sortable column headers. | Table view provides denser information and sortability for large backlogs. |
| FR-02.20 | SHALL | The system shall navigate to the Task Detail view when the user clicks a row in the List view. | Consistent behavior — both board cards and list rows open the same detail view. |

**Acceptance Criteria — FR-02.17:**
- [ ] Phase filter dropdown allows multi-select of phases (project, design, plan, build, test, deploy)
- [ ] Priority filter allows selection of priority levels
- [ ] Filters apply immediately to the visible board/list
- [ ] Active filters are shown as removable chips/pills
- [ ] Clearing all filters restores the full view

**Acceptance Criteria — FR-02.18:**
- [ ] Two toggle buttons render in the filter bar: Board (grid icon) and List (list icon)
- [ ] Active view is visually highlighted
- [ ] View preference persists in localStorage across page reloads

**Acceptance Criteria — FR-02.19:**
- [ ] Table renders all tasks matching current filters
- [ ] Clicking a column header sorts the table by that column (toggle asc/desc)
- [ ] Status icon column shows the same status icons as board cards
- [ ] Phase tag column shows colored pills matching board card phase tags
- [ ] Updated column shows relative timestamps (e.g., "2h ago", "1d ago")

---

### Group: Task Detail

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.21 | SHALL | The system shall navigate to the Task Detail view when the user clicks a card on the Kanban board, replacing the board content area while keeping the sidebar-nav visible. | Task Detail is the deep-dive view for interacting with a specific task. |
| FR-02.22 | SHALL | The system shall render a task header showing the task title, phase tag, priority indicator, current status, and a "Back to Board" button. | Context bar — the user must always know which task they are viewing and how to return. |
| FR-02.23 | SHALL | The system shall render the Task Detail as a two-panel layout: Chat panel (~60% width, left) and Smart Viewer slot (~40% width, right). | Chat is the primary interaction; Smart Viewer provides file context side-by-side. |
| FR-02.24 | SHALL | The system shall render the Smart Viewer as an empty slot with a placeholder message ("Select a file to view here") and a tab management API for Split 03. | Viewer renderers are delivered in Split 03; this split provides the container and API surface. |

**Acceptance Criteria — FR-02.21:**
- [ ] Clicking a card navigates to Task Detail (URL changes, e.g., /tasks/:id)
- [ ] Sidebar-nav remains visible and functional in Task Detail view
- [ ] Board content area is fully replaced by the Task Detail layout
- [ ] Browser back button returns to the Kanban Dashboard

**Acceptance Criteria — FR-02.22:**
- [ ] Task title renders prominently in the header
- [ ] Phase tag, priority, and status render alongside the title
- [ ] "Back to Board" button is visible at the left of the header
- [ ] Clicking "Back to Board" returns to the Kanban Dashboard (preserving filter/tab state)

**Acceptance Criteria — FR-02.23:**
- [ ] Chat panel occupies ~60% of the available width (left side)
- [ ] Smart Viewer slot occupies ~40% of the available width (right side)
- [ ] A drag handle between panels allows resizing
- [ ] Panel widths are persisted in localStorage

---

### Group: Chat Engine

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.25 | SHALL | The system shall render user messages as right-aligned bubbles and assistant messages as left-aligned bubbles with Markdown rendering via react-markdown + remark-gfm + rehype-highlight. | Core chat experience — must match Claude.ai style. |
| FR-02.26 | SHALL | The system shall render AskUserQuestion events as interactive cards with option buttons and a freetext input field, and submit the user's answer via POST /api/inbox/:id/answer. | Primary human-in-the-loop mechanism. |
| FR-02.27 | SHALL | The system shall render tool-call events (Bash, Read, Grep, Edit, Write) as collapsible cards showing the tool name, input parameters, and output, collapsed by default. | Users need visibility into Claude's actions; collapsed by default reduces noise during long sessions. |
| FR-02.28 | SHALL | The system shall render code diffs for Edit and Write tool calls using react-diff-viewer, showing before/after content in a split or unified view. | File changes must be visually clear — plain text is insufficient for diffs. |
| FR-02.29 | SHALL | The system shall stream assistant messages with a 100ms render buffer for smooth incremental display. | Prevents jittery character-by-character rendering during streaming. |
| FR-02.30 | SHALL | The system shall auto-scroll the chat to the latest message when new content arrives, unless the user has manually scrolled up. | Standard chat UX — respects the user's scroll position while keeping up with new content. |
| FR-02.31 | SHALL | The system shall provide a chat input area with a send button, Shift+Enter for newlines, and a toolbar row above the input containing: model selector (Opus/Sonnet/Haiku), permission mode (Auto/Ask/Edit/Plan/Bypass), effort level (Low/Medium/High), autonomy toggle (Guided/Autonomous), slash-command trigger (/), and file-reference trigger (@). | Chat input must expose the same capabilities as the CLI. |
| FR-02.32 | SHALL | The system shall trigger a slash-command autocomplete popup when the user types `/` in the chat input, listing available Shipwright commands filtered as the user types. | Slash commands are the primary way to invoke pipeline phases and iterate. |
| FR-02.33 | SHALL | The system shall trigger a file-reference autocomplete popup when the user types `@` in the chat input, listing project files for inline reference, filtered as the user types. | File references provide context to Claude without copy-pasting content. |

**Acceptance Criteria — FR-02.25:**
- [ ] User messages render right-aligned with a distinct background color
- [ ] Assistant messages render left-aligned with Markdown formatting (headings, lists, bold, links)
- [ ] Code blocks have syntax highlighting via rehype-highlight
- [ ] GFM features render correctly (tables, task lists, strikethrough)

**Acceptance Criteria — FR-02.26:**
- [ ] AskUserQuestion card displays the question text prominently
- [ ] Option buttons render as clickable pills in a horizontal row
- [ ] Freetext input field is available below the option buttons
- [ ] Clicking an option or submitting freetext sends POST /api/inbox/:id/answer
- [ ] After answering, the card transitions to an "answered" state showing the chosen response

**Acceptance Criteria — FR-02.27:**
- [ ] Tool-call cards show an icon and label for the tool type (Bash, Read, Grep, Edit, Write)
- [ ] Cards are collapsed by default, showing only tool name and a summary line
- [ ] Expanding a card reveals input parameters and output content
- [ ] Long output is truncated with a "Show more" toggle

**Acceptance Criteria — FR-02.29:**
- [ ] Streaming tokens are buffered and flushed to the DOM every 100ms
- [ ] Partial Markdown renders correctly during streaming (no broken syntax)
- [ ] A typing indicator (pulsing dots or cursor) is visible during active streaming

**Acceptance Criteria — FR-02.31:**
- [ ] Enter key sends the message (when input is non-empty)
- [ ] Shift+Enter inserts a newline in the input
- [ ] Send button is visually disabled when input is empty
- [ ] Input field auto-grows vertically up to 6 lines, then scrolls
- [ ] Toolbar row above input shows all six controls: model, mode, effort, autonomy, / commands, @ files
- [ ] Model selector pill displays current model, clicking opens dropdown with Opus/Sonnet/Haiku
- [ ] Permission mode pill shows current mode, clicking opens dropdown with all 5 modes
- [ ] Effort pill shows current level, clicking cycles through Low/Medium/High
- [ ] Autonomy pill shows mode with colored dot (green=guided, amber=autonomous), click toggles

**Acceptance Criteria — FR-02.32:**
- [ ] Typing `/` in the input opens an autocomplete popup
- [ ] Commands are filtered as the user types (e.g., `/ship` filters to shipwright commands)
- [ ] Selecting a command inserts it into the input
- [ ] Popup closes on Escape or clicking outside

**Acceptance Criteria — FR-02.33:**
- [ ] Typing `@` in the input opens a file picker popup
- [ ] Files are listed from the active project directory
- [ ] Files are filtered as the user types after `@`
- [ ] Selecting a file inserts the reference into the input

---

### Group: Phase-Status Mapping

| ID | Priority | Requirement | Rationale |
|----|----------|-------------|-----------|
| FR-02.34 | SHALL | The system shall map Shipwright pipeline phases to board columns using a configurable mapping, defaulting to: Backlog = (no phases, not yet started), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (no phases, task completion). | Enables the Kanban board to reflect pipeline progress. Backlog and Done are automatic states, not phase-driven. |
| FR-02.35 | SHOULD | The system should allow per-project override of the phase-to-status mapping via project settings. | Non-dev projects may have different phase semantics. |

**Acceptance Criteria — FR-02.34:**
- [ ] Tasks are placed in the correct column based on their current pipeline phase
- [ ] Default mapping is applied for new projects: Backlog = (empty), In Progress = project/design/plan/build, In Review = test/security/deploy/changelog, Done = (empty)
- [ ] When Claude advances a task's phase, the card moves to the mapped column automatically

## 3. Quality Requirements

| ID | Category | Requirement | Metric |
|----|----------|-------------|--------|
| QR-02.01 | Performance | The system shall render the initial Kanban Dashboard (sidebar + board with cards) within 500ms of page load. | First Contentful Paint < 500ms (Lighthouse, localhost). |
| QR-02.02 | Performance | The system shall render streaming chat tokens with no more than 200ms perceived latency from SSE event receipt to DOM update. | Measured via Performance API marks on SSE `onmessage` to `requestAnimationFrame`. |
| QR-02.03 | Performance | Card updates from SSE events shall appear on the board within 2 seconds of event receipt. | Measured from SSE event timestamp to card DOM mutation. |
| QR-02.04 | Accessibility | All interactive elements shall be keyboard-navigable and have ARIA labels. | Radix UI primitives provide baseline; custom components must match. |
| QR-02.05 | Accessibility | Color contrast for all text shall meet WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text). | Verified via axe-core or Lighthouse accessibility audit. |
| QR-02.06 | Maintainability | Each UI component shall have fewer than 300 lines of code. Larger components must be decomposed. | Enforced via code review. |
| QR-02.07 | Reliability | The board and chat shall reconnect SSE streams automatically within 5 seconds after connection loss. | EventSource native reconnect + TanStack Query retry. |
| QR-02.08 | Visual | The system shall use AI Portal brand tokens: primary #6b5e56, background #f5f0eb, surface #ffffff, font Inter, shadow-based cards, 12px border-radius. | Brand consistency across all views. |

## 4. Constraints

| ID | Constraint | Rationale |
|----|-----------|-----------|
| CO-02.01 | React 19 + Vite 6 + TailwindCSS 4 + Radix UI as the frontend stack. | Decided in architecture review; Radix for accessibility, Tailwind for utility-first styling. |
| CO-02.02 | TanStack React Query for all server data fetching; SSE events invalidate query caches. | Single data-fetching pattern; SSE triggers cache invalidation, not direct state mutation. |
| CO-02.03 | Native EventSource API for SSE (no third-party SSE library). | Sufficient for local single-user app; no polyfill needed for modern browsers. |
| CO-02.04 | react-markdown + remark-gfm + rehype-highlight for Markdown rendering. | Covers GFM tables, code highlighting in chat messages. |
| CO-02.05 | react-diff-viewer for code diffs in Edit/Write tool calls. | Plain text insufficient for diff visualization; library provides split/unified views. |
| CO-02.06 | NO Monaco Editor — rehype-highlight is sufficient for code display. | Monaco is overkill for a read-only viewer; reduces bundle size significantly. |
| CO-02.07 | NO xterm.js in V1 — terminal fallback deferred to a later version. | Reduces scope; tool-call cards provide sufficient visibility. |
| CO-02.08 | All data fetched from Split 01 REST APIs; no direct file system access from the frontend. | Clean separation of concerns; backend is the single writer. |
| CO-02.09 | NO drag-and-drop on the Kanban board. | Claude controls card movement via pipeline events; manual drag would conflict with automated state management. |
| CO-02.10 | Inter as the sole UI font. | AI Portal brand consistency. |

## 5. Dependencies

### Depends On

| Dependency | Split | Detail |
|-----------|-------|--------|
| REST API routes | Split 01 | `GET /api/projects`, `GET /api/projects/:id/tasks`, `GET /api/projects/:id/chat`, `POST /api/projects/:id/chat`, `POST /api/inbox/:id/answer`, `POST /api/projects/:id/classify` |
| SSE endpoint | Split 01 | `GET /api/projects/:id/events` (SSE stream for real-time updates: task status, chat messages, card enrichment, inbox changes) |
| TypeScript types | Split 01 | Shared types for `Project`, `Task`, `InboxItem`, `Event`, `ChatMessage` |
| Event format | Split 01 | NDJSON event schema (`work_completed`, `phase_completed`, `task_created`, `ask_user_question`, `task_classified`) |
| Classify endpoint | Split 01 | `POST /api/projects/:id/classify` for auto-classification of new issues |

### Provides To

| Consumer | Split | Detail |
|----------|-------|--------|
| Smart Viewer renderers | Split 03 | `<ViewerSlot />` component with tab management API (`openTab(file)`, `closeTab(id)`, `activeTab`) |
| Settings page | Split 03 | Sidebar-nav "Settings" click callback; settings page renders in the main content area |
| Inbox page | Split 03 | Sidebar-nav "Inbox" click callback; inbox page renders in the main content area |
| New Project Wizard | Split 03 | Callback from project creation flow; wizard renders inside a modal slot |

## 6. Key Decisions

| ID | Decision | Alternatives Considered | Rationale |
|----|----------|------------------------|-----------|
| KD-02.01 | Kanban-first UI with two views (Board + Task Detail) replaces the 5-panel IDE layout. | 5-panel IDE layout (original spec), single-page chat UI. | Kanban provides better multi-task overview; Task Detail preserves the deep chat experience. Board is more intuitive for project management than a code-IDE metaphor. |
| KD-02.02 | Wider sidebar-nav (200px, icon + text) replaces the narrow 48px rail. | 48px icon-only rail (original), no sidebar. | Text labels improve discoverability; 200px is standard for app navigation (Slack, Linear, Notion). |
| KD-02.03 | Cards auto-move via SSE events; no drag-and-drop. | Drag-and-drop with manual overrides. | Claude controls the pipeline — manual drag would create conflicting state. Automatic movement provides a "magic" feel where tasks progress on their own. |
| KD-02.04 | Phase tags on cards replace horizontal pipeline steps. | Horizontal pipeline bar (original), separate pipeline panel. | Phase info is on the card itself — no need for a separate visualization. Simpler and more space-efficient. |
| KD-02.05 | New Issue creates a card immediately, classifies in background. | Classify first, then create card. Wait for classification before showing card. | Instant feedback is critical — users see their issue immediately. Classification enriches the card asynchronously. |
| KD-02.06 | SSE cache invalidation via TanStack Query `queryClient.invalidateQueries()` on SSE events, not direct React state mutation. | Direct state updates from SSE. | Query cache is the single source of truth for server state; avoids dual-state bugs. |
| KD-02.07 | 100ms streaming buffer for chat rendering. | No buffer (per-token rendering); 250ms buffer. | 100ms balances perceived responsiveness with smooth rendering; proven pattern from Claude.ai-style interfaces. |
| KD-02.08 | Tool-call cards collapsed by default. | Expanded by default; no tool-call rendering. | Long build sessions produce hundreds of tool calls; expanded-by-default creates overwhelming scroll. |
| KD-02.09 | Component SLOT for Smart Viewer — render empty placeholder, actual renderers plugged in by Split 03. | Build all renderers in this split. | Keeps Split 02 focused on layout + chat; viewer renderers are independent and can be added incrementally. |
| KD-02.10 | Panel widths (Task Detail) in localStorage, not server-side. | Persist in server settings API. | Layout preferences are per-browser; localStorage is simpler and faster. |

## 7. UI Requirements

### 7.1 Kanban Dashboard (Default View)

```
+------------+------------------------------------------------------------------+
| Sidebar    | [Project-A] [Project-B] [All]          [Phase v] [Prio v] [= |||] [+ New Issue] |
| (200px)    +------------------------------------------------------------------+
|            | Backlog (5)       | In Progress (2)  | In Review (1) | Done (8)   |
| [H] Home   |                   |                  |               |            |
|            | +---------------+ | +-------------+  | +-----------+ | +--------+ |
| [I] Inbox  | | Auth module   | | | Build UI    |  | | Run tests | | | Deploy | |
|  (3)       | | [plan] P2     | | | [build] P1  |  | | [test]    | | | [done] | |
|            | | Tests: --     | | | Tests: 4/12 |  | | Tests: 12 | | | abc123 | |
|            | | ...           | | | a1b2c3      |  | | ...       | | +--------+ |
|            | +---------------+ | | ...          |  | +-----------+ |            |
| [S] Settings| +---------------+ | +-------------+  |               | +--------+ |
|            | | Add API       | |                  |               | | Hotfix | |
|            | | [project] P3  | |                  |               | | [done] | |
|            | | intent: feat  | |                  |               | | def456 | |
|            | +---------------+ |                  |               | +--------+ |
+------------+-------------------+------------------+---------------+------------+
```

**Layout behavior:**
- Sidebar-nav: fixed 200px, does not resize
- Board area: fills remaining horizontal space (flex)
- Columns: equal flex width within the board area, min 200px each
- Cards: full column width minus padding, shadow-based, 12px border-radius, white surface
- Project tabs: horizontal tab bar above the board, scrollable if many projects
- Filter bar: below project tabs, contains phase dropdown, priority dropdown, view toggle (right-aligned)

---

### 7.2 Sidebar Navigation

```
+------------+
|            |
| [H] Home   |  <- Board icon + "Home" (active: accent background)
|            |
| [I] Inbox  |  <- Inbox icon + "Inbox"
|  (3)       |     ^ red badge with count
|            |
|            |
|            |
|            |
| [S] Settings|  <- Gear icon + "Settings" (bottom-anchored)
+------------+
```

- Width: ~200px
- Items: icon (20px) + text label, vertically stacked with 8px gap between items
- Active item: warm accent background (#6b5e56 at 10% opacity) + left border (3px solid #6b5e56)
- Badge: 18px red circle, 11px white text, positioned right of "Inbox" text
- Settings: bottom-anchored with separator line above
- Background: surface white (#ffffff) with subtle right border

---

### 7.3 Task Card

```
+---------------------------+
| Auth module           ... |  <- Title + overflow menu
| [plan]  P2                |  <- Phase tag (colored pill) + Priority
| Tests: --   |  --         |  <- Test count + Commit hash
+---------------------------+
```

- Card: white background (#ffffff), 12px border-radius, subtle shadow (`0 1px 3px rgba(0,0,0,0.1)`)
- Title: 14px Inter semibold, max 2 lines, ellipsis overflow
- Phase tag: 10px rounded pill, colored per phase (project=#9ca3af gray, design=#a855f7 purple, plan=#3b82f6 blue, build=#f97316 orange, test=#22c55e green, deploy=#14b8a6 teal)
- Priority: P1=red dot, P2=amber dot, P3=gray dot (or text label)
- "..." menu: appears on hover (desktop) or always visible (mobile)
- Hover state: slightly elevated shadow

---

### 7.4 Task Detail View

```
+------------+---------------------------------------------+--------------------+
| Sidebar    | [<- Back to Board]  Auth module  [plan] P2 In Progress          |
| (200px)    +---------------------------------------------+--------------------+
|            |                                             |                    |
| [H] Home   | Chat (~60%)                                 | Smart Viewer (~40%)|
|            |                                             |                    |
| [I] Inbox  |       +---------------------------+        | [empty slot]       |
|  (3)       |       | How should I handle auth? |        | "Select a file     |
|            |       | Options:                  |        |  to view here"     |
| [S] Settings|       | * JWT tokens              |        |                    |
|            |       | * Session cookies         |        |                    |
|            |       +---------------------------+        |                    |
|            |                                             |                    |
|            |  +-------------------------------+          |                    |
|            |  | Use JWT with refresh tokens   |          |                    |
|            |  +-------------------------------+          |                    |
|            |                                             |                    |
|            |       +---------------------------+        |                    |
|            |       | AskUserQuestion           |        |                    |
|            |       | Which DB for sessions?    |        |                    |
|            |       | [Redis] [Postgres] [Both] |        |                    |
|            |       | [Type your answer...    ] |        |                    |
|            |       +---------------------------+        |                    |
|            |                                             |                    |
|            |       [v Bash: npm install ...]              |                    |
|            |       [v Edit: src/auth.ts]                  |                    |
|            |         +-----------------------------+     |                    |
|            |         | - old line                  |     |                    |
|            |         | + new line                  |     |                    |
|            |         +-----------------------------+     |                    |
|            |                                             |                    |
|            | +------------------------------------------+|                    |
|            | | [Opus v] [Auto v] [Med v] [Guided v]     ||                    |
|            | | [Message input...                ] [Send]||                    |
|            | | Shift+Enter for new line  [/] [@]        ||                    |
|            | +------------------------------------------+|                    |
+------------+---------------------------------------------+--------------------+
```

**Panel behavior:**
- Sidebar-nav: fixed 200px (same as Dashboard view)
- Header bar: full width of content area, showing back button + task title + metadata
- Chat panel: ~60% of remaining width, min 400px
- Smart Viewer slot: ~40% of remaining width, min 200px
- Drag handle between Chat and Viewer allows resizing
- Panel widths persisted in localStorage

**Chat input toolbar:**
- Model selector: pill showing "Opus" / "Sonnet" / "Haiku", dropdown on click
- Permission mode: pill showing current mode, dropdown with 5 options + descriptions
- Effort: pill showing "Low" / "Med" / "High", click cycles through
- Autonomy: pill with colored dot (green=Guided, amber=Autonomous), click toggles
- `/` trigger: icon button or implicit from typing `/` in input
- `@` trigger: icon button or implicit from typing `@` in input

**Message styling:**
- User messages: right-aligned, rounded corners, primary accent background (#6b5e56), white text
- Assistant messages: left-aligned, rounded corners, warm cream background (#f5f0eb), dark text
- AskUserQuestion cards: left-aligned, bordered card, white surface, with option pills + freetext
- Tool-call cards: full-width, muted background, collapsible header with tool icon + name
- Diff view: react-diff-viewer inside expanded Edit/Write tool cards, split view by default

---

### 7.5 List View (Alternative to Board)

```
+------------+------------------------------------------------------------------+
| Sidebar    | [Project-A] [Project-B] [All]          [Phase v] [Prio v] [= |||] [+ New Issue] |
| (200px)    +------------------------------------------------------------------+
|            | Status | Title              | Phase    | Priority | Tests | Commit | Updated |
| [H] Home   +--------+--------------------+----------+----------+-------+--------+---------+
|            | [o]    | Auth module        | [plan]   | P2       | --    | --     | 2h ago  |
| [I] Inbox  | [o]    | Add API            | [project]| P3       | --    | --     | 5h ago  |
|  (3)       | [*]    | Build UI           | [build]  | P1       | 4/12  | a1b2c3 | 30m ago |
|            | [?]    | Run tests          | [test]   | --       | 12/12 | b2c3d4 | 1h ago  |
| [S] Settings| [v]    | Deploy v1          | [done]   | --       | 12/12 | abc123 | 1d ago  |
|            | [v]    | Hotfix login       | [done]   | P1       | 14/14 | def456 | 2d ago  |
+------------+--------+--------------------+----------+----------+-------+--------+---------+
```

- Status icons: `[o]` = open (gray circle), `[*]` = in progress (blue filled, pulse), `[?]` = in review (amber), `[v]` = done (green checkmark)
- Sortable columns: click header to sort asc/desc, sort indicator arrow on active column
- Row hover: subtle background highlight
- Row click: navigates to Task Detail view (same as card click)

## 8. References

| Reference | Location | Relevance |
|-----------|----------|-----------|
| Implementation plan | `Spec/plan-shipwright-webui.md` | Authoritative source for architecture and tech decisions |
| Project manifest | `webui/planning/project-manifest.md` | Split definitions, dependencies, and execution order |
| Architecture review | `Spec/claude-code-webui-architektur.md` | Review findings that shaped tech stack decisions |
| Radix UI docs | https://www.radix-ui.com/primitives | Accessible component primitives (Dialog, Collapsible, Tooltip, ScrollArea, Popover) |
| react-markdown | https://github.com/remarkjs/react-markdown | Markdown rendering with plugin ecosystem |
| react-diff-viewer | https://github.com/praneshr/react-diff-viewer | Split/unified code diff visualization |
| TanStack React Query | https://tanstack.com/query | Data fetching, caching, SSE cache invalidation |
| AI Portal brand | Internal design tokens | Primary #6b5e56, Background #f5f0eb, Surface #ffffff, Font Inter |
