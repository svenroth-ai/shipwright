# Shipwright Command Center (WebUI)

## WHAT
- **Purpose**: Local web application for managing multiple Shipwright SDLC projects in parallel.
- **Architecture**: Hono backend (Node.js) + React 19 frontend (Vite 6), monorepo in `webui/`. **External-launch model (Plan D'' variant a, 2026-04-19)**: webui owns no Claude subprocess. The user runs Claude Code in their own terminal via a pre-bound `--session-id <uuid>` copy-command; webui observes the resulting JSONL at `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl`.
- **Stack**: TypeScript strict, Hono, React 19, Vite 6, TailwindCSS 4, Radix UI, TanStack React Query.

## Architecture reference

Plan of record: [`~/.claude/plans/plan-d-double-prime-external-launch.md`](../.claude/plans/plan-d-double-prime-external-launch.md).
PoC findings that shaped the implementation: [`~/.claude/plans/external-launch-poc-results.md`](../.claude/plans/external-launch-poc-results.md).
Decision record: `agent_docs/decision_log.md` ADR-034.

Two hard rules, survivors of every review round:
1. **Webui spawns no Claude process.** Users launch in their own terminal; webui observes the JSONL.
2. **Server is stateless on transcript reads.** Client passes `?fromByte=<offset>&expectFingerprint=<fp>`; no per-session byte-offset cache lives server-side. Multi-tab works by construction.

## Structure
```
webui/
  scripts/                      # install-windows.ps1, dev-restart.js
  server/                       # Hono backend (port 3847)
    src/
      index.ts                  # Server entry (~170 LOC — minimal wiring only)
      config.ts                 # Env config
      core/
        launcher.ts             # Copy-command generator (PS / cmd.exe / POSIX)
        session-watcher.ts      # Filename-first JSONL discovery + byte-range reader
        session-parser.ts       # Typed events from raw JSONL + unknown-fallback
        inbox-derive.ts         # Pending tool_use extraction (best-effort)
        sdk-sessions-store.ts   # Persistent task store (schema-versioned)
        cli-compat.ts           # Claude CLI version gate (MIN_SUPPORTED_CLI)
        project-manager.ts      # Project metadata CRUD (still used)
        profile-loader.ts       # Stack profile loading (wizard)
      external/
        routes.ts               # /api/external/{tasks,launch,transcript,inbox,...}
      middleware/
        error-handler.ts        # Centralized error response middleware
        logger.ts               # Request logging
      routes/
        projects.ts             # GET/POST/PATCH/DELETE /api/projects
        diagnostics.ts          # GET /api/diagnostics (CLI + launcher + sessions)
        settings.ts             # GET/PUT /api/settings
        profiles.ts             # GET /api/profiles
    package.json
    tsconfig.json
  client/                       # React 19 / Vite 6 frontend
    e2e/                        # Playwright E2E specs (30/32/33/34/35)
    src/
      main.tsx
      App.tsx
      router.tsx                # react-router-dom route definitions
      layouts/                  # Layout shells (Main)
      pages/
        TaskBoardPage.tsx       # Task list + create (/)
        TaskDetailPage.tsx      # LaunchRow + CopyCommandCard + SessionMetadata + TranscriptViewer
        ProjectsPage.tsx        # Project registry + wizard
        InboxPage.tsx           # Pending interactions (best-effort)
        DiagnosticsPage.tsx     # CLI + launcher + sessions snapshot
        SettingsPage.tsx        # Minimal stub (settings moved into user's Claude client)
      components/
        external/
          TranscriptViewer.tsx
          LaunchRow.tsx
          SessionMetadata.tsx
          CopyCommandCard.tsx
        common/
          DiagnosticsBanner.tsx # Warns when CLI < MIN_SUPPORTED_CLI
        sidebar/                # Sidebar navigation
        wizard/                 # Project Wizard (4-step modal)
      external/
        session-parser.ts       # Client-side parser (typed events for rendering)
      hooks/                    # TanStack Query + polling hooks
      lib/                      # externalApi.ts + utilities
      contexts/                 # React contexts
      test/                     # Vitest test utilities
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

# Terminal 2 — Vite client (port 5173 by default, proxies /api to 3847)
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
```

### Conventions
- TypeScript strict mode everywhere.
- Hono routes in `server/src/routes/`, one file per resource. External-launch routes live at `server/src/external/routes.ts`.
- React components in `client/src/components/`, grouped by UI area.
- TanStack React Query for data fetching + sequential polling for transcript updates.
- TailwindCSS 4 for styling, Radix UI for accessible primitives.
- Files under 300 lines — split if larger.
- Conventional Commits (feat:, fix:, refactor:, test:, docs:, chore:).

### Architecture rules (post-Plan-D'')
1. **Webui never spawns Claude.** Launchers produce command strings; the user pastes them. Regression guard: Playwright spec `35-no-chat-panel.spec.ts`.
2. **Task state is derived from `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl` + the persistent store.** Session UUID is pre-bound at task creation via `crypto.randomUUID()`.
3. **Discovery is filename-first.** `<uuid>.jsonl` is the primary match (PoC finding 1); first-line sessionId is a secondary sanity check.
4. **Transcript endpoint is stateless.** `GET /api/external/tasks/:id/transcript?fromByte=<n>&expectFingerprint=<fp>` — multi-tab support comes for free.
5. **UTF-8-safe chunking.** Server reads are cut on `\n` boundaries only.
6. **Torn-read retry budget.** `core/session-watcher.ts` retries EBUSY/EPERM/EACCES/ENOENT up to 6 attempts with 50→1600 ms backoff.
7. **No SSE for transcript.** Sequential 1 s polling on the client via `useTaskTranscript`.
8. **No chokidar.** Heartbeat-free; watcher state is derived on demand from mtime probes.
9. **Plugin dirs must be re-passed on every launch.** `--plugin-dir` does not reliably survive `--resume`.
10. **MIN_SUPPORTED_CLI is pinned.** See `core/cli-compat.ts`. Anything older shows a banner via `/api/diagnostics`.

### Dev-server troubleshooting

If recent code changes don't show up in the running webui, `tsx watch` has
probably gone stale on Windows. Kill the PID on :3847 explicitly:

```bash
# Windows:
netstat -ano | findstr :3847
taskkill //F //PID <pid>
cd webui/server && npm run dev
```

`npm run dev:fresh` (the dev-restart.js helper) has a known Windows bug and
is not recommended until fixed.
