# Plan Interview — 02-ui-shell (Kanban Board & Task Detail)

## Session Info
- Date: 2026-04-10
- Split: 02-ui-shell
- Spec: webui/planning/02-ui-shell/spec.md (35 FRs)

## Decisions

All major UI decisions were made during the Design phase (mockup review):

### Kanban-First (from UI Pivot)
- Board as default home, Task Detail on card click
- Sidebar-nav with dark warm background (#5c5652), white text
- Columns: Backlog → In Progress → In Review → Done
- Phase tags on cards (not phase columns)
- No Drag&Drop — Claude moves cards via events
- Card menu for manual Close/Cancel

### Navigation (from Design Review)
- 4 items: Task Board, Projects, Inbox (badge), Settings
- Dark sidebar (~200px), warm gray (#5c5652)
- Active/inactive items: white / rgba(255,255,255,0.7)

### Chat Input Toolbar (from Design Review)
- Model selector (Opus/Sonnet/Haiku)
- Permission mode (Auto/Ask/Edit/Plan/Bypass)
- Effort (Low/Medium/High)
- Autonomy (Guided/Autonomous)
- / Commands autocomplete
- @ Files autocomplete

### Task switching
- Sidebar-driven: click task in board → Task Detail
- No chat tabs — one chat visible at a time
- Back button returns to board

## Context from Project Interview (carried forward)
- React 19 + Vite 6 + TailwindCSS 4 + Radix UI
- TanStack React Query for data fetching
- EventSource API for SSE
- react-markdown + remark-gfm + rehype-highlight
- react-diff-viewer for code diffs
- AI Portal design tokens (warm premium)
