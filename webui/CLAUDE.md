# Shipwright Command Center (WebUI)

## WHAT
- **Purpose**: Local web application for managing multiple Shipwright SDLC projects in parallel
- **Architecture**: Hono backend (Node.js) + React 19 frontend (Vite 6), monorepo in `webui/`
- **Stack**: TypeScript strict, Hono, React 19, Vite 6, TailwindCSS 4, Radix UI, TanStack React Query

## Structure
```
webui/
  server/
    src/
      index.ts              # Hono server (port 3847)
      core/
        claude-adapter.ts   # Claude CLI spawn + NDJSON parser
        task-manager.ts     # In-memory task state from events + processes
        project-manager.ts  # Multi-project registry CRUD
        inbox-manager.ts    # Inbox aggregation + stdin delivery
        process-governor.ts # Semaphore (max N concurrent) + orphan cleanup
        heartbeat.ts        # Scheduler (node-cron, 30s interval)
        file-watcher.ts     # chokidar on events + configs
        chat-store.ts       # Chat history persist/load
        sse-manager.ts      # SSE endpoint for real-time push
      bridge/
        config-reader.ts    # Reads shipwright_*_config.json
        event-reader.ts     # Reads shipwright_events.jsonl
        pipeline-state.ts   # Pipeline status from events + configs
        doc-index.ts        # File tree for Smart Viewer
        intent-classifier.ts # Shell-out to classify_intent.py + classify_complexity.py
      routes/
        projects.ts         # GET/POST/PATCH/DELETE /api/projects
        tasks.ts            # GET/POST /api/projects/:id/tasks
        inbox.ts            # GET /api/inbox, POST /api/inbox/:id/answer
        chat.ts             # GET/POST /api/projects/:id/chat
        pipeline.ts         # GET /api/projects/:id/pipeline
        docs.ts             # GET /api/projects/:id/docs
        classify.ts         # POST /api/projects/:id/classify
        settings.ts         # GET/PUT /api/settings
        sse.ts              # GET /api/events (SSE stream)
  client/
    src/
      App.tsx
      layouts/
        MainLayout.tsx      # Kanban board + Task Detail layout
      components/
        nav/                # Sidebar Navigation (200px, icon + text)
        board/              # Kanban Board (columns, cards, filters, list view)
        detail/             # Task Detail (header, two-panel chat+viewer)
        chat/               # Chat Engine (messages, tools, diffs)
        viewer/             # Smart File Viewer (tab renderers)
        explorer/           # File Explorer (slide-in tree)
        inbox/              # Inbox / Global Inbox view
        wizard/             # Project Wizard (4-step modal)
        settings/           # Settings page (global + per-project)
      hooks/                # TanStack Query hooks + SSE hooks
      types/                # Shared TypeScript types
    index.html
    vite.config.ts
    tailwind.config.ts
  package.json
  tsconfig.json
```

## HOW

### Development
```bash
cd webui
npm install                   # Install dependencies
npm run dev                   # Start both server + client (concurrently)
npm run dev:server            # Server only (Hono, port 3847)
npm run dev:client            # Client only (Vite, port 5173, proxies to 3847)
npm run build                 # Production build
npm run test                  # Run tests (Vitest)
npm run test:e2e              # Run E2E tests (Playwright)
npm run lint                  # ESLint + TypeScript check
```

### Key Environment Variables
```
PORT=3847                     # Server port
SHIPWRIGHT_MAX_CONCURRENT=3   # Max parallel Claude processes
```

### Conventions
- TypeScript strict mode everywhere
- Hono routes in `server/src/routes/`, one file per resource
- React components in `client/src/components/`, grouped by UI area
- TanStack React Query for all data fetching (no raw fetch in components)
- SSE via native EventSource API (no Socket.io)
- TailwindCSS 4 for styling, Radix UI for accessible primitives
- Files under 300 lines — split if larger
- Conventional Commits (feat:, fix:, refactor:, test:, docs:, chore:)

### Architecture Rules
1. **All file writes through backend only** — never from child processes or frontend
2. **Event log is single source of truth** — task state derived from events + active processes
3. **No database** — JSONL event log + JSON files only
4. **No auth** — local single-user application
5. **SSE for real-time** — server pushes, client subscribes via EventSource
6. **Claude CLI as subprocess** — spawn with --output-format stream-json and --plugin-dir
7. **Build Dashboard** — `agent_docs/build_dashboard.md` is auto-generated during implementation by `update_build_dashboard.py`. Do not edit manually.
