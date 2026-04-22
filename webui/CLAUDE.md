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
      config/
        default-actions.json    # Shipwright phase + action catalog (Iterate 3)
      core/
        launcher.ts             # Copy-command generator (PS / cmd.exe / POSIX). Exports qPs/qCmd/qPosix for reuse.
        session-watcher.ts      # Filename-first JSONL discovery + byte-range reader
        session-parser.ts       # Typed events from raw JSONL + unknown-fallback
        inbox-derive.ts         # Pending tool_use extraction (best-effort)
        sdk-sessions-store.ts   # Persistent task store (schema-versioned v1/v2; projectId field)
        cli-compat.ts           # Claude CLI version gate (MIN_SUPPORTED_CLI)
        project-manager.ts      # Project metadata CRUD (still used)
        profile-loader.ts       # Stack profile loading (wizard)
        project-actions-loader.ts  # Iterate 3: mtime-cached resolver for .webui/actions.json → default-actions.json fallback
        actions-substitute.ts   # Iterate 3: placeholder substitution ({project.path}, {task.uuid}, …) w/ per-shell escape
        preview-session-manager.ts # Iterate 3: Preview subprocess lifecycle (spawn shell:false, keyed by projectId, kill-on-shutdown)
        path-guard.ts           # Iterate 3: shared path-traversal guard (realpath + path.relative, NOT startsWith) for tree + file routes
        gitignore-cache.ts      # Iterate 3: mtime-keyed gitignore rule cache for FolderTree
      external/
        routes.ts               # /api/external/{tasks,launch,transcript,inbox,actions,preview,actions-stub,projects/:id/tree,projects/:id/file}
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
          BubbleTranscript.tsx       # Chat-style transcript (replaces TranscriptViewer)
          MarkdownText.tsx           # react-markdown wrapper (XSS-safe + code cap)
          ToolOutputBlock.tsx        # ANSI-stripped tool output
          TerminalLaunchButton.tsx   # Shared launch CTA (compact / primary / inline)
          EditableTaskTitle.tsx      # In-place title edit on TaskDetail
          TaskCard.tsx               # TaskBoard card (state icon + menu + launch)
          ConfirmDeleteDialog.tsx    # Delete confirm for non-terminal states
          SessionMetadata.tsx        # State badge + UUID + cwd + timestamps
          # Iterate 3 additions (LaunchRow + CopyCommandCard were removed — replaced by header-level state-dependent CTA):
          FolderTree.tsx             # Lazy-expand gitignore-aware tree (left pane of TaskDetail)
          SmartViewer/               # Right pane of TaskDetail — 5 renderers (Markdown/Code/Text/Image/Mermaid; mermaid lazy-imported, 609 KB chunk)
          NewIssueModal.tsx          # Shared New-* modal body (Pipeline / Iterate / Task variants)
          PreviewButton.tsx          # Dev-server spawn trigger; visibility-gated by profile.stack.frontend
          CreateMenuSplitButton.tsx  # Sidebar "+ New ▾" split-button (Pipeline / Iterate / Task)
          TaskDetailThreePane.tsx    # react-resizable-panels wrapper; persists widths + collapsed state in localStorage
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

### Architecture rules (post-Plan-D'' + Iterate 2)
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

### Preview-capability precedence (Iterate 3, plan § 2.1)

Iterate 3 introduces a Preview dev-server spawn path (not Claude — see ADR-044). Three sources interact:

1. **Profile `stack.frontend` presence** — the capability gate (is this project a frontend project at all?).
2. **Profile `dev_server.command`** — the spawn target (which command actually starts the dev-server).
3. **`.webui/actions.json` → `actions.preview.enabled`** — the policy override (user-level opt-out).

`stack.frontend` AND `dev_server.command` must both be present for `<PreviewButton>` to render. `actions.preview.enabled = false` hides it regardless. Boot-time coherence check warns when `stack.frontend` is set but `dev_server.command` is missing (button would render, spawn would 500). The full diagram lives in [`webui/agent_docs/architecture.md`](agent_docs/architecture.md).

### DO-NOT regression guards (Iterate 2 / ADR-035)
1. **DO NOT write into Claude's JSONL files under `~/.claude/projects/`.** Webui is a read-only polling observer of that directory. Title sync uses Claude's first-party `--name` CLI flag at launch time, not JSONL mutation or a sidecar file.
2. **Auto-scroll pattern is CSS-first.** `overflow-anchor: auto` + `scroll-padding` on the scroll container is the primary path. `useAutoScroll` (ResizeObserver-light, ref-based, ~50 LOC) is the safety net for Chrome+polling cases. Do NOT reach for stale libraries like `react-scroll-to-bottom`. See ADR-035.
3. **DO NOT re-introduce a chat composer.** External-launch architecture is load-bearing. See ADR-034. Spec 35 fails the build if a chat-* surface re-appears.
4. **DO NOT re-add `@assistant-ui/*` packages.** Rendering is bespoke via `react-markdown` + `remark-gfm` + `rehype-highlight` + `strip-ansi`. The full stack is in `webui/client/package.json` already.
5. **DO NOT run `claude --resume <uuid>` as a webui-initiated side-effect command** while the user's session may be active in their terminal. SQLite lock + JSONL interleave risk (EBUSY on Windows). Title updates take effect on next user-initiated launch only.
6. **Multi-writer state files** (`sdk-sessions.json`, any future sidecars) MUST use `proper-lockfile`, not just temp-file + rename. The PATCH /tasks/:id endpoint surfaces ELOCKED as 409 so the client can retry instead of silently overwriting.
7. **TSC baseline:** server has 4 pre-existing errors (cross-package imports + missing `@types/proper-lockfile`). Policy is "no regression" — new code must compile clean; existing errors are tracked but not required to fix in this iterate.
8. (Iterate 3 — ADR-044) **Schema v2 is write-on-touch.** `sdk-sessions.json` v1 rows load as `projectId: "unassigned"` in memory and rewrite to v2 on next mutation. DO NOT batch-rewrite on boot — ADR-038 explicitly rejected that path. The `schemaVersion` header field must load both v1 and v2 during the forward-compat window.
9. (Iterate 3 — ADR-044) **Preview spawn uses `shell: false`.** User-controlled `dev_server.command` strings + `shell: true` would be command-injection. All Preview subprocess entrypoints flow through `core/preview-session-manager.ts`, which tokenizes the command and spawns with `shell: false`. DO NOT add a parallel spawn path.
10. (Iterate 3 — ADR-044) **Path-guard is `realpath + path.relative`, NOT `startsWith`.** Symlinks, unicode, and Windows junction points defeat prefix checks. All tree + file routes share `core/path-guard.ts`; null-byte input is hard-rejected.
11. (Iterate 3 — ADR-044) **DO NOT hardcode `shipwright-run` / `shipwright-iterate` / phase strings (`build`, `plan`, `design`, …) in components** — read from `/api/external/projects/:id/actions`. Violations re-introduce the configurability debt iterate 3 paid down and will cause custom `.webui/actions.json` installations to break silently. Meta-test `client/src/test/doc-sync.test.ts` keeps this file-map honest; grep your component for `shipwright-` literals before committing.

### Title integration (`--name`)

Webui owns the task title in `sdk-sessions.json`. Every launch command (initial OR resume) emits `--name "<title>"` after `--session-id` / `--resume`. Claude pre-seeds the picker title from this flag and produces `custom-title` + `agent-name` events in the JSONL. There is no mid-session sync. Renames take effect on the NEXT user-initiated launch — see `core/launcher.ts`, `external/routes.ts` PATCH handler, and `client/src/components/external/EditableTaskTitle.tsx`.

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
