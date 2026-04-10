# Decision Log — Shipwright Command Center

## Project Interview (2026-04-09)

### DEC-001: Hono over Express 5
- **Context:** Need a Node.js backend framework for local single-user web app
- **Decision:** Use Hono instead of Express 5
- **Rationale:** Better TypeScript DX, built-in SSE (streamSSE()), lightweight (~14KB), modern patterns (Web Standard APIs). Express 5 still maturing, larger but less TypeScript-native.
- **Rejected:** Express 5 (larger ecosystem but weaker TS), Fastify (solid but less modern DX)
- **Impact:** All server code uses Hono patterns, Paperclip Express code needs mechanical adaptation

### DEC-002: In-memory state from events (no tasks.json)
- **Context:** Need task state management — plan proposed tasks.json + events as dual source
- **Decision:** Pure in-memory state reconstructed from event log + active process tracking
- **Rationale:** Single source of truth (events.jsonl), no sync issues, crash recovery via event replay. Running/waiting states from process manager (ephemeral by nature).
- **Rejected:** tasks.json as primary store, hybrid model (tasks.json cache + events)
- **Impact:** Server startup replays events, no persistent task file needed

### DEC-003: New task_created event type
- **Context:** Events only captured task completion (work_completed), not creation
- **Decision:** Add task_created event type to record_event.py
- **Rationale:** Enables full task lifecycle tracking, orphan detection (task_created without work_completed = crashed task), immediate visibility in UI
- **Rejected:** In-memory only tracking (loses state on crash)
- **Impact:** record_event.py needs extension, event reader needs to handle new type

### DEC-004: Dual phase_completed deduplication
- **Context:** Deploy/Changelog plugins now emit phase_completed with --detail, orchestrator also emits phase_completed without detail
- **Decision:** Keep both, WebUI deduplicates (prefers event with detail field)
- **Rationale:** Backwards compatible, no orchestrator change needed. Detail-bearing events are strictly more informative.
- **Rejected:** Remove orchestrator emission (cleaner but breaks existing behavior)
- **Impact:** Event reader needs dedup logic (group by type+phase+timestamp window)

### DEC-005: SSE over WebSocket
- **Context:** Need real-time server-to-client push
- **Decision:** Server-Sent Events (SSE) instead of WebSocket/Socket.io
- **Rationale:** Unidirectional push is sufficient (client-to-server via REST). SSE is simpler, native browser API, Hono has built-in support. Socket.io is overkill for local single-user.
- **Rejected:** Socket.io (bidirectional overkill), raw WebSocket (more code for same result)
- **Impact:** Frontend uses EventSource API, server uses Hono streamSSE()

### DEC-006: WebUI stores chat history
- **Context:** Claude CLI has own session management (--session-id). Do we also store?
- **Decision:** Yes, WebUI persists parsed NDJSON stream per task
- **Rationale:** Enables chat replay, task context switching, offline viewing. CLI sessions are opaque — WebUI needs parsed messages for rendering.
- **Rejected:** CLI-only sessions (no replay, no task-context switching in UI)
- **Impact:** Chat store module needed, storage in project's .shipwright-webui/chat-history/

### DEC-007: Target audience — all Shipwright users
- **Context:** Could be power-user-only or broadly accessible
- **Decision:** All Shipwright users, "Replit light" — accessible but not dumbed down
- **Rationale:** Masterclass product built around it. Users have some dev experience but aren't necessarily CLI experts.
- **Rejected:** Power-user-only (limits audience), absolute beginner (too much hand-holding)
- **Impact:** Good defaults, clear UI, minimal required configuration

## UI Shell Spec Decisions (02-ui-shell)

### KD-02.01: Kanban-first replaces 5-panel IDE layout
- **Context:** Original spec used a 5-panel IDE layout (Rail, Sidebar, Chat, Viewer, Explorer)
- **Decision:** Kanban-first UI with two views (Board + Task Detail)
- **Rationale:** Kanban provides better multi-task overview; Task Detail preserves the deep chat experience. Board is more intuitive for project management than a code-IDE metaphor.
- **Rejected:** 5-panel IDE layout (original spec), single-page chat UI
- **Impact:** MainLayout.tsx becomes a router between Kanban Dashboard and Task Detail views; rail/ and sidebar/ components replaced by nav/ and board/

### KD-02.02: Wider sidebar-nav (200px) replaces 48px rail
- **Context:** Original spec had a narrow 48px icon-only rail
- **Decision:** 200px sidebar-nav with icon + text labels
- **Rationale:** Text labels improve discoverability; 200px is standard for app navigation (Slack, Linear, Notion).
- **Rejected:** 48px icon-only rail (original), no sidebar
- **Impact:** Navigation component changes from rail/ to nav/; width budget shifts from 48px to 200px

### KD-02.03: No drag-and-drop on Kanban board
- **Context:** Kanban boards typically support drag-and-drop card reordering
- **Decision:** Cards auto-move via SSE events; no drag-and-drop
- **Rationale:** Claude controls the pipeline — manual drag would create conflicting state. Automatic movement provides a "magic" feel where tasks progress on their own.
- **Rejected:** Drag-and-drop with manual overrides
- **Impact:** No DnD library needed; card position derived entirely from pipeline events

### KD-02.04: Phase tags on cards replace horizontal pipeline steps
- **Context:** Original spec had horizontal pipeline steps as a separate visualization
- **Decision:** Phase tags rendered as colored pills on Kanban cards
- **Rationale:** Phase info is on the card itself — no need for a separate visualization. Simpler and more space-efficient.
- **Rejected:** Horizontal pipeline bar (original), separate pipeline panel
- **Impact:** Eliminates pipeline/ component directory; phase info embedded in card component

### KD-02.05: Immediate card creation, background classification
- **Context:** New Issue flow could block on classification before showing the card
- **Decision:** Card appears in Backlog immediately on submit; classification runs asynchronously
- **Rationale:** Instant feedback is critical — users see their issue immediately. Classification enriches the card asynchronously.
- **Rejected:** Classify first then create card; wait for classification
- **Impact:** Two-phase card lifecycle: bare card on creation, enriched card after classify API returns

### KD-02.06: SSE cache invalidation via TanStack Query
- **Context:** SSE events could directly mutate React state or invalidate query caches
- **Decision:** SSE events trigger queryClient.invalidateQueries(), not direct state mutation
- **Rationale:** Query cache is the single source of truth for server state; avoids dual-state bugs.
- **Rejected:** Direct state updates from SSE
- **Impact:** SSE hook invalidates relevant query keys; no manual state management for server data

### KD-02.07: 100ms streaming buffer for chat rendering
- **Context:** Streaming chat tokens need buffering to avoid jitter
- **Decision:** 100ms render buffer for chat message streaming
- **Rationale:** Balances perceived responsiveness with smooth rendering; proven pattern from Claude.ai-style interfaces.
- **Rejected:** No buffer (per-token), 250ms buffer
- **Impact:** Chat rendering hook includes a 100ms flush interval

### KD-02.08: Tool-call cards collapsed by default
- **Context:** Tool-call events (Bash, Read, Edit, Write) could render expanded or collapsed
- **Decision:** Collapsed by default, showing only tool name and summary line
- **Rationale:** Long build sessions produce hundreds of tool calls; expanded-by-default creates overwhelming scroll.
- **Rejected:** Expanded by default, no tool-call rendering
- **Impact:** Collapsible card component with expand/collapse toggle

### KD-02.09: Viewer SLOT pattern for Split 03
- **Context:** Smart Viewer renderers could be built in Split 02 or deferred
- **Decision:** Split 02 renders an empty placeholder slot; Split 03 plugs in actual renderers
- **Rationale:** Keeps Split 02 focused on layout + chat; viewer renderers are independent and can be added incrementally.
- **Rejected:** Build all renderers in Split 02
- **Impact:** ViewerSlot component with tab management API (openTab, closeTab, activeTab)

### KD-02.10: Panel widths in localStorage, not server-side
- **Context:** Task Detail panel widths (Chat vs Viewer) could be persisted server-side or locally
- **Decision:** localStorage persistence
- **Rationale:** Layout preferences are per-browser; localStorage is simpler and faster.
- **Rejected:** Persist in server settings API
- **Impact:** useLocalStorage hook for panel width state

## Features Spec Decisions (03-features)

### KD-03.01: Smart Viewer inside Task Detail, not top-level
- **Context:** Smart Viewer could be a permanent top-level panel or scoped to task detail
- **Decision:** Smart Viewer lives inside Task Detail view (right panel)
- **Rationale:** With Kanban-first, the board is the primary view. File viewing is contextual to a task, so it belongs inside the task detail rather than occupying permanent screen space.
- **Rejected:** Permanent top-level panel (original 5-panel layout)
- **Impact:** Viewer renders only when a task is open; no viewer on the Kanban Dashboard

### KD-03.02: File Explorer slide-in inside Task Detail
- **Context:** File Explorer could be global or task-scoped
- **Decision:** Slide-in inside Task Detail view, hidden by default
- **Rationale:** Files are browsed in the context of a specific task. Embedding the explorer inside the task detail keeps navigation task-scoped rather than global.
- **Rejected:** Global slide-in from any view
- **Impact:** Explorer toggle button in Task Detail toolbar; explorer component renders inside detail/

### KD-03.03: Minimal New Issue Dialog
- **Context:** New Issue could have many fields (type, priority, labels) or be minimal
- **Decision:** Title + Description only; classification runs in background after creation
- **Rationale:** Reduces friction for issue creation. Users want to capture ideas quickly. Auto-classification enriches the card asynchronously.
- **Rejected:** Full-featured issue form with manual classification
- **Impact:** Simple modal with two fields; POST to tasks API then fire-and-forget classify API call

### KD-03.04: Reuse Python classify scripts via backend API
- **Context:** Classification could be reimplemented in TypeScript or reuse existing Python scripts
- **Decision:** Reuse classify_intent.py and classify_complexity.py via the backend classify API
- **Rationale:** Scripts already implement the detection logic for the CLI. Running them post-creation avoids blocking the dialog on API latency.
- **Rejected:** Reimplement in TypeScript, inline classification
- **Impact:** Backend shells out to Python via uv run; frontend calls POST /api/projects/:id/classify

### KD-03.05: Intent Detection downgraded to MAY
- **Context:** Intent Detection was originally a Must-have feature
- **Decision:** Downgraded from Must to May; scoped to Task Detail chat only
- **Rationale:** With Kanban-first, there is no global chat input. Intent detection can still add value inside a task's chat, but it is lower priority since tasks are already explicitly scoped.
- **Rejected:** Keep as Must-have
- **Impact:** Optional feature; implementation deferred if time-constrained

### KD-03.06: Directory validation, not emptiness validation
- **Context:** Project Wizard could validate directory existence and/or emptiness
- **Decision:** Validate directory existence only, not emptiness
- **Rationale:** Users may want to add Shipwright to an existing project directory that already contains files.
- **Rejected:** Validate both existence and emptiness
- **Impact:** Wizard Step 1 checks fs.existsSync only

### KD-03.07: Read-only viewer, no file editing
- **Context:** Viewer could support inline editing or be strictly read-only
- **Decision:** No file editing in the viewer or explorer — strictly read-only
- **Rationale:** Claude handles all code changes. The viewer is for inspection and review, not manual editing. This avoids conflicts with Claude's file operations.
- **Rejected:** Inline editing with save
- **Impact:** No Monaco Editor; rehype-highlight sufficient for code display

---

### ADR-001: Dynamic CORS origin matching for localhost
- **Date:** 2026-04-10
- **Section:** Build — 01-project-setup
- **Context:** CORS middleware needs to allow any localhost port during development
- **Decision:** Use Hono cors() with dynamic origin callback that matches any origin containing 'localhost'
- **Commit:** fd90c2c70ddd28193b2225bcb9f78927338cc656
- **Rationale:** Simpler than maintaining a whitelist of ports; Vite dev server port may vary
- **Consequences:** All localhost:* origins accepted during dev; null returned for non-localhost origins
- **Rejected:** Static origin list (e.g. localhost:5173 only)

---

### ADR-002: Injectable FileSystemDeps for testability
- **Date:** 2026-04-11
- **Section:** Build — 03-event-system
- **Context:** Event reader and writer need file access but must be unit-testable without real FS
- **Decision:** Define FileSystemDeps/WriterDeps interfaces, inject mocks in tests, use real fs in production
- **Commit:** 8121221
- **Rationale:** Dependency injection pattern from spec (QR-01.09); proven in all Shipwright plugins
- **Consequences:** All bridge modules are pure-function testable; no test-time file system side effects
- **Rejected:** Jest module mocking (brittle), test-time temp files (slow, flaky on CI)

---

### ADR-003: Standalone NDJSON parser as separate module
- **Date:** 2026-04-11
- **Section:** Build — 05-claude-adapter
- **Context:** NDJSON parsing needed by Claude adapter but also useful independently
- **Decision:** Extract parseNdjsonLine() and isAskUserQuestion() into ndjson-parser.ts
- **Commit:** 4160b5b
- **Rationale:** Single responsibility; parser has 8 dedicated tests covering edge cases
- **Consequences:** Adapter stays focused on process management; parser independently testable and reusable
- **Rejected:** Inline parsing in adapter (harder to test edge cases independently)

---

### ADR-004: PID file for orphan detection across restarts
- **Date:** 2026-04-11
- **Section:** Build — 06-process-governor
- **Context:** Server restarts need to detect and kill orphaned Claude processes from previous run
- **Decision:** Persist active PIDs to ~/.shipwright-webui/pids.json, check on startup
- **Commit:** bd2c3ef
- **Rationale:** process.kill(pid, 0) check is fast and reliable; JSON persistence is atomic enough for single-user
- **Consequences:** Reliable orphan cleanup; small JSON file written on every spawn/release
- **Rejected:** OS-level process group tracking (platform-specific), no tracking (orphans accumulate)

---

### ADR-005: Path traversal prevention in doc-index
- **Date:** 2026-04-11
- **Section:** Build — 10-api-routes
- **Context:** GET /api/projects/:id/docs?file=path reads arbitrary files within project directory
- **Decision:** Resolve path with path.resolve(), verify startsWith(projectDir) before reading
- **Commit:** d21e143
- **Rationale:** OWASP path traversal prevention; defense in depth even for local-only app
- **Consequences:** Prevents ../../etc/passwd style attacks; returns 400 AppError on violation
- **Rejected:** No validation (local app argument), regex-based filtering (bypassable)
