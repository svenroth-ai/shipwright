# Project Manifest — Shipwright Command Center

## SPLIT_MANIFEST
```yaml
splits:
  - name: "01-core"
    title: "Backend Core & Claude Adapter"
    description: >
      Hono server, Claude CLI adapter (spawn + NDJSON parse), event system
      (reader + in-memory state + task_created), process governor, SSE manager,
      config/event bridge, REST API routes, multi-project registry, inbox manager,
      chat store, file watcher. Everything server-side.
    estimated_sections: 8-10
    dependencies: []
    parallel_hint: "Can start immediately. Defines API contracts for 02-ui-shell."

  - name: "02-ui-shell"
    title: "UI Shell: Kanban Board & Task Detail"
    description: >
      Kanban-first UI with two views: Kanban Dashboard (sidebar-nav 200px,
      project tabs, filter bar, 4-column board, task cards, list view toggle)
      and Task Detail (chat ~60% + Smart Viewer slot ~40%). Sidebar Navigation
      (200px, icon+text), Chat Engine (streaming, messages, tool-call cards,
      diff view, AskUserQuestion cards), Chat Input Toolbar (model, mode,
      effort, autonomy, / commands, @ files). No drag-and-drop.
    estimated_sections: 8-10
    dependencies:
      - split: "01-core"
        type: "APIs"
        detail: "REST API routes + SSE endpoints for projects, tasks, chat, pipeline"
    parallel_hint: "Can start layout/styling in parallel with 01-core using mock data."

  - name: "03-features"
    title: "Viewers, Explorer, Wizard & Advanced Features"
    description: >
      Smart File Viewer (Markdown, HTML preview, Mermaid, code, JSON tree,
      consistency dashboard), File Explorer (slide-in tree with git status),
      Project Wizard (step-by-step), New Task Dialog (intent/complexity preview
      via classify API), Intent Detection Banner, Global Inbox view, Settings page.
    estimated_sections: 6-8
    dependencies:
      - split: "01-core"
        type: "APIs"
        detail: "docs, classify, settings API routes"
      - split: "02-ui-shell"
        type: "patterns"
        detail: "Layout shell, component patterns, Radix UI conventions"
    parallel_hint: "Smart Viewer renderers can be built independently."

execution_order:
  - "01-core"
  - "02-ui-shell"
  - "03-features"

shared_dependencies:
  - type: "models"
    detail: "TypeScript types for Project, Task, InboxItem, Event, PipelineRun (shared between server and client)"
  - type: "patterns"
    detail: "Hono API route pattern, SSE event format, TanStack Query hooks pattern"
```

## Rationale

### Why 3 splits (not 2 or 4)?

**2 splits (backend/frontend)** would be 10-15 sections each — on the edge of "too big" per split heuristics. Planning sessions lose focus with 15+ sections.

**4 splits** would fragment natural feature groups. Smart Viewer renderers, File Explorer, and Project Wizard are too small individually for their own split.

**3 splits** hits the sweet spot:
- **01-core** (~9 sections): All server-side code. Clear boundary at API level.
- **02-ui-shell** (~9 sections): Layout + interactive core (Chat is the biggest piece). Clear boundary at component level.
- **03-features** (~7 sections): Specialized viewers + wizard + advanced features. Can be built incrementally.

### Dependency flow
```
01-core ──────────────> 02-ui-shell ──────> 03-features
 (APIs, SSE, types)     (Layout, Chat)      (Viewers, Wizard)
```

Sequential execution recommended. Partial parallelism possible:
- 02-ui-shell layout/styling can start with mock data while 01-core APIs are being built
- 03-features Smart Viewer renderers are independent of each other
