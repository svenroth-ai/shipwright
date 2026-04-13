# Shipwright Command Center (WebUI)

## WHAT
- **Purpose**: Local web application for managing multiple Shipwright SDLC projects in parallel
- **Architecture**: Hono backend (Node.js) + React 19 frontend (Vite 6), monorepo in `webui/`
- **Stack**: TypeScript strict, Hono, React 19, Vite 6, TailwindCSS 4, Radix UI, TanStack React Query

## Structure
```
webui/
  scripts/                      # install-windows.ps1, dev-restart.js
  server/                       # Hono backend (port 3847)
    src/
      index.ts                  # Server entry
      config.ts                 # Env config
      core/
        claude-adapter.ts       # Claude CLI spawn + NDJSON parser
        ndjson-parser.ts        # NDJSON stream parsing (shared)
        task-manager.ts         # In-memory task state from events + processes
        project-manager.ts      # Multi-project registry CRUD
        inbox-manager.ts        # Inbox aggregation + stdin delivery
        process-governor.ts     # Semaphore (max N concurrent) + orphan cleanup
        heartbeat.ts             # Scheduler (node-cron, 30s interval)
        file-watcher.ts         # chokidar on events + configs
        chat-store.ts           # Chat history persist/load
        event-store.ts          # Event log read/write coordination
        sse-manager.ts          # SSE endpoint for real-time push
      bridge/
        config-reader.ts        # Reads shipwright_*_config.json
        event-reader.ts         # Reads shipwright_events.jsonl
        event-writer.ts         # Writes shipwright_events.jsonl entries
        pipeline-state.ts       # Pipeline status from events + configs
        doc-index.ts            # File tree for Smart Viewer
        intent-classifier.ts    # Shell-out to classify_intent.py + classify_complexity.py
      middleware/
        error-handler.ts        # Centralized error response middleware
        logger.ts               # Request logging
      routes/
        projects.ts             # GET/POST/PATCH/DELETE /api/projects
        tasks.ts                # GET/POST /api/projects/:id/tasks, PATCH .../status, .../description
        inbox.ts                # GET /api/inbox, POST /api/inbox/:id/answer
        chat.ts                 # GET/POST /api/projects/:id/chat
        pipeline.ts             # GET /api/projects/:id/pipeline
        docs.ts                 # GET /api/projects/:id/docs
        classify.ts             # POST /api/projects/:id/classify
        settings.ts             # GET/PUT /api/settings
        sse.ts                  # GET /api/events (SSE stream)
    package.json
    tsconfig.json
  client/                       # React 19 / Vite 6 frontend
    e2e/                        # Playwright E2E specs
    src/
      main.tsx
      App.tsx
      router.tsx                # react-router-dom route definitions
      layouts/                  # Layout shells (Main, etc.)
      pages/                    # Route-level pages (Kanban, TaskDetail, Inbox, Projects, Settings)
      components/
        sidebar/                # Sidebar navigation
        board/                  # Kanban Board (columns, cards, filters, list view)
        detail/                 # Task Detail (header, two-panel chat+viewer)
        chat/                   # Chat engine (messages, tool calls, diffs)
        viewer/                 # Smart File Viewer (tab renderers)
        explorer/               # File Explorer (slide-in tree)
        wizard/                 # Project Wizard (4-step modal)
      contexts/                 # React contexts
      hooks/                    # TanStack Query + SSE hooks
      lib/                      # Utilities and API clients
      test/                     # Vitest test utilities and setup
      types/                    # Shared TypeScript types
    index.html
    vite.config.ts
    package.json
    tsconfig.json
```

## HOW

### Development

`webui/` has **no root `package.json`** — server and client are independent workspaces. Run each in its own terminal:

```bash
# Install (once)
cd webui/server && npm install
cd webui/client && npm install

# Terminal 1 — Hono backend (tsx watch, port 3847)
cd webui/server && npm run dev

# Terminal 2 — Vite client (port from vite.config.ts, proxies /api to 3847)
cd webui/client && npm run dev
```

Other scripts (run from the respective subdir):

```bash
npm run build                 # Production build
npm run test                  # Vitest
npm run test:e2e              # Playwright (client only)
npm run lint                  # ESLint
npm run typecheck             # tsc --noEmit
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

### Dev-server troubleshooting

If recent code changes don't show up in the running webui, the `tsx watch`
process has probably gone stale. This happens most often after `git merge`
operations (file swaps don't always fire chokidar events on Windows) and
after long dev sessions where multiple `npm run dev` calls left orphaned
child processes.

**One-command recovery** (kills every `tsx watch`/`vite`/node process
owning ports 3847/5173/5177, then respawns `npm run dev` in
`webui/server/`):

```bash
cd webui/server
npm run dev:fresh
```

The client (`webui/client`) normally does not need a restart because Vite
HMR handles file changes reliably. If the client is also stale, start it
manually in a second terminal: `cd webui/client && npm run dev`.

**Note:** this is a dev-only concern. Production users of shipwright never
run `tsx watch` — they run the compiled server where the code doesn't
change under them, so this class of problem cannot occur.
