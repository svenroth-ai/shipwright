# Implementation Plan — Kanban Board & Task Detail

## Overview

This plan covers the complete frontend implementation of the Shipwright Command Center: a React 19 single-page application with two primary views (Kanban Dashboard and Task Detail) connected via sidebar navigation. The architecture follows a Kanban-first approach where task cards auto-update via SSE events — Claude controls card movement through the pipeline, and there is no drag-and-drop.

The implementation is organized into 9 sections in dependency order. Section 01 establishes the Vite + React 19 + TailwindCSS 4 project scaffold. Section 02 builds the app shell (sidebar-nav, routing, layout). Section 03 creates TanStack Query data hooks and SSE integration. Sections 04-06 implement the Kanban Dashboard (board, new issue modal, filters/list view). Sections 07-08 build the Task Detail view (layout, chat engine). Section 09 adds phase-to-status mapping configuration.

The TDD approach uses Vitest + @testing-library/react for component tests, renderHook for custom hook tests, and MSW (Mock Service Worker) for API mocking. SSE streams are mocked via custom EventSource stubs. Every component test verifies rendering, interaction, and accessibility (ARIA labels, keyboard navigation). Tests are co-located with source files per project conventions.

**Key patterns:**
- TanStack React Query as single data layer — SSE events trigger `queryClient.invalidateQueries()`, never direct state mutation (KD-02.06)
- Radix UI primitives for all interactive elements (Dialog, Popover, Collapsible, Tooltip, Select, Tabs)
- TailwindCSS 4 utility classes with AI Portal brand tokens (primary #6b5e56, background #f5f0eb, surface #ffffff, font Inter)
- Component files under 300 lines (QR-02.06), decomposed into subcomponents when larger
- Smart Viewer rendered as empty slot with tab management API — actual renderers delivered in Split 03

## SECTION_MANIFEST
```yaml
sections:
  - id: "01"
    name: "vite-setup"
    title: "Vite Project Setup"
    depends_on: []
    frs: []
  - id: "02"
    name: "layout-routing"
    title: "App Shell, Sidebar Navigation & Routing"
    depends_on: ["01"]
    frs: ["FR-02.01", "FR-02.02", "FR-02.03", "FR-02.04"]
  - id: "03"
    name: "data-hooks"
    title: "TanStack Query Data Hooks & SSE Integration"
    depends_on: ["01", "02"]
    frs: []
  - id: "04"
    name: "kanban-board"
    title: "Kanban Board — Columns, Cards & Real-Time Updates"
    depends_on: ["02", "03"]
    frs: ["FR-02.05", "FR-02.06", "FR-02.07", "FR-02.08", "FR-02.09", "FR-02.10", "FR-02.11", "FR-02.12"]
  - id: "05"
    name: "new-issue"
    title: "New Issue Modal & Background Auto-Classify"
    depends_on: ["03", "04"]
    frs: ["FR-02.13", "FR-02.14", "FR-02.15", "FR-02.16"]
  - id: "06"
    name: "filter-list"
    title: "Filter Bar, View Toggle & List View"
    depends_on: ["04"]
    frs: ["FR-02.17", "FR-02.18", "FR-02.19", "FR-02.20"]
  - id: "07"
    name: "task-detail"
    title: "Task Detail Page Layout"
    depends_on: ["02", "03"]
    frs: ["FR-02.21", "FR-02.22", "FR-02.23", "FR-02.24"]
  - id: "08"
    name: "chat-engine"
    title: "Chat Engine — Messages, Tools, Diffs & Input Toolbar"
    depends_on: ["03", "07"]
    frs: ["FR-02.25", "FR-02.26", "FR-02.27", "FR-02.28", "FR-02.29", "FR-02.30", "FR-02.31", "FR-02.32", "FR-02.33"]
  - id: "09"
    name: "phase-mapping"
    title: "Phase-to-Status Mapping"
    depends_on: ["03"]
    frs: ["FR-02.34", "FR-02.35"]
```

## Sections

---

### Section 01: Vite Project Setup
**Goal:** Create the Vite 6 + React 19 project scaffold with TailwindCSS 4, Radix UI, TanStack React Query, and all runtime/dev dependencies. Configure TypeScript strict mode, Vite proxy to backend, and Vitest with React Testing Library.

**FRs:** None directly (infrastructure).

**Files:**
- `client/package.json` — dependencies and scripts
- `client/tsconfig.json` — TypeScript strict configuration
- `client/vite.config.ts` — Vite config with proxy to backend port 3847
- `client/index.html` — HTML entry point with Inter font
- `client/src/main.tsx` — React 19 entry point with QueryClientProvider
- `client/src/App.tsx` — Root component (placeholder)
- `client/src/index.css` — TailwindCSS 4 imports + brand tokens as CSS custom properties
- `client/vitest.config.ts` — Vitest + jsdom + React Testing Library setup
- `client/src/test/setup.ts` — Test setup (MSW, cleanup)
- `client/src/test/mocks/handlers.ts` — MSW request handlers (empty scaffold)
- `client/src/test/mocks/server.ts` — MSW server setup

---

### Section 02: App Shell, Sidebar Navigation & Routing
**Goal:** Build the persistent sidebar-nav (200px, dark warm theme), React Router routes, main content area, and responsive collapse behavior. Sidebar remains visible across all views.

**FRs:** FR-02.01, FR-02.02, FR-02.03, FR-02.04

**Files:**
- `client/src/layouts/MainLayout.tsx` — Sidebar + content area shell
- `client/src/components/sidebar/SidebarNav.tsx` — Sidebar navigation component
- `client/src/components/sidebar/SidebarNavItem.tsx` — Individual nav item with icon + label
- `client/src/components/sidebar/InboxBadge.tsx` — Real-time badge count
- `client/src/router.tsx` — React Router configuration

---

### Section 03: TanStack Query Data Hooks & SSE Integration
**Goal:** Create all TanStack Query hooks for backend API consumption and the SSE hook that drives real-time cache invalidation. This is the data backbone that all UI components consume.

**FRs:** Supports all data-consuming FRs.

**Files:**
- `client/src/hooks/useProjects.ts` — Query hook for projects list
- `client/src/hooks/useTasks.ts` — Query hook for tasks by project
- `client/src/hooks/useInbox.ts` — Query hook for inbox items
- `client/src/hooks/useChat.ts` — Query hook for chat messages + send mutation
- `client/src/hooks/usePipeline.ts` — Query hook for pipeline state
- `client/src/hooks/useSSE.ts` — SSE EventSource hook with query invalidation
- `client/src/hooks/useLocalStorage.ts` — localStorage persistence hook
- `client/src/lib/api.ts` — Shared fetch wrapper with error handling

---

### Section 04: Kanban Board — Columns, Cards & Real-Time Updates
**Goal:** Build the Kanban Dashboard with project tabs, four columns (Backlog, In Progress, In Review, Done), task cards with phase tags and metadata, overflow menu, and SSE-driven auto-updates.

**FRs:** FR-02.05 through FR-02.12

**Files:**
- `client/src/pages/KanbanPage.tsx` — Board page container
- `client/src/components/board/ProjectTabs.tsx` — Project tab bar
- `client/src/components/board/KanbanBoard.tsx` — Four-column board layout
- `client/src/components/board/KanbanColumn.tsx` — Single column with header + card list
- `client/src/components/board/TaskCard.tsx` — Card component with metadata
- `client/src/components/board/PhaseTag.tsx` — Colored phase pill
- `client/src/components/board/PriorityIndicator.tsx` — Priority dot/label
- `client/src/components/board/CardOverflowMenu.tsx` — "..." menu with Close/Cancel

---

### Section 05: New Issue Modal & Background Auto-Classify
**Goal:** Build the New Issue modal (Title + Description), immediate Backlog card creation, background auto-classification via POST /api/projects/:id/classify, and card enrichment via SSE.

**FRs:** FR-02.13 through FR-02.16

**Files:**
- `client/src/components/board/NewIssueButton.tsx` — "+ New Issue" button
- `client/src/components/board/NewIssueModal.tsx` — Modal dialog with form
- `client/src/hooks/useCreateTask.ts` — Mutation hook for task creation + classify

---

### Section 06: Filter Bar, View Toggle & List View
**Goal:** Build the filter bar (phase/priority dropdowns), Board/List view toggle with localStorage persistence, and the List view as a sortable table.

**FRs:** FR-02.17 through FR-02.20

**Files:**
- `client/src/components/board/FilterBar.tsx` — Filter bar container
- `client/src/components/board/PhaseFilter.tsx` — Phase multi-select dropdown
- `client/src/components/board/PriorityFilter.tsx` — Priority filter dropdown
- `client/src/components/board/ViewToggle.tsx` — Board/List toggle buttons
- `client/src/components/board/TaskListView.tsx` — Sortable table view
- `client/src/components/board/TaskListRow.tsx` — Table row component
- `client/src/components/board/StatusIcon.tsx` — Status icon component

---

### Section 07: Task Detail Page Layout
**Goal:** Build the Task Detail page with header bar (back navigation, task metadata), two-panel layout (Chat ~60%, Smart Viewer slot ~40%), resizable drag handle, and localStorage panel width persistence.

**FRs:** FR-02.21 through FR-02.24

**Files:**
- `client/src/pages/TaskDetailPage.tsx` — Task Detail page container
- `client/src/components/detail/TaskHeader.tsx` — Header with back button, title, metadata
- `client/src/components/detail/PanelLayout.tsx` — Resizable two-panel layout
- `client/src/components/detail/ViewerSlot.tsx` — Empty Smart Viewer placeholder with tab API

---

### Section 08: Chat Engine — Messages, Tools, Diffs & Input Toolbar
**Goal:** Build the full chat experience: message bubbles (user/assistant), Markdown rendering, AskUserQuestion cards, tool-call cards (collapsible), code diffs, streaming with 100ms buffer, auto-scroll, chat input with toolbar pills, slash-command and file-reference autocomplete.

**FRs:** FR-02.25 through FR-02.33

**Files:**
- `client/src/components/chat/ChatPanel.tsx` — Chat container with auto-scroll
- `client/src/components/chat/ChatMessage.tsx` — Message routing (user/assistant/tool/ask)
- `client/src/components/chat/UserMessage.tsx` — Right-aligned user bubble
- `client/src/components/chat/AssistantMessage.tsx` — Left-aligned assistant bubble with Markdown
- `client/src/components/chat/AskUserCard.tsx` — Interactive AskUserQuestion card
- `client/src/components/chat/ToolCallCard.tsx` — Collapsible tool-call card
- `client/src/components/chat/DiffView.tsx` — Code diff via react-diff-viewer
- `client/src/components/chat/ChatInput.tsx` — Input area with send button
- `client/src/components/chat/ChatToolbar.tsx` — Toolbar pills row
- `client/src/components/chat/ModelSelector.tsx` — Model dropdown pill
- `client/src/components/chat/PermissionMode.tsx` — Permission mode dropdown pill
- `client/src/components/chat/EffortPill.tsx` — Effort level cycling pill
- `client/src/components/chat/AutonomyPill.tsx` — Autonomy toggle pill
- `client/src/components/chat/SlashCommandPopup.tsx` — / command autocomplete
- `client/src/components/chat/FileReferencePopup.tsx` — @ file autocomplete
- `client/src/hooks/useStreamingChat.ts` — SSE streaming with 100ms buffer

---

### Section 09: Phase-to-Status Mapping
**Goal:** Implement the phase-to-status mapping logic that places task cards in the correct Kanban columns, with default mapping and per-project override support.

**FRs:** FR-02.34, FR-02.35

**Files:**
- `client/src/lib/phaseMapping.ts` — Mapping logic + defaults
- `client/src/components/board/PhaseMappingConfig.tsx` — Mapping display/edit component
- `client/src/hooks/usePhaseMapping.ts` — Hook for phase mapping per project
