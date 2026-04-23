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

### ADR-005: Task actions — Close + Delete (no Cancel)
- **Date:** 2026-04-11
- **Section:** Test Phase — Task Actions
- **Context:** Task card menu had Close, Cancel, and Delete. "Cancel" was confusing.
- **Decision:** Simplify to Close (→ Done) and Delete (→ remove). No separate "Cancel" action.
- **Rationale:** Simpler mental model — task is either done or gone. "Cancelled" had no clear meaning.
- **Consequences:** CardOverflowMenu and TaskHeader both use Close + Delete; same actions on card and detail page
- **Rejected:** Three-action model (Close + Cancel + Delete)

---

### ADR-006: Autonomy as per-project setting (not chat toggle)
- **Date:** 2026-04-11
- **Section:** Test Phase — Autonomy
- **Context:** Autonomy was a toggle on the chat toolbar, changeable per-message.
- **Decision:** Autonomy is a per-project setting (Settings → Project tab). Chat toolbar shows read-only badge.
- **Rationale:** Autonomy is a project-level decision (e.g., production app = guided, prototype = autonomous). Changing per-message is confusing and doesn't map to how Shipwright plugins implement it.
- **Consequences:** Global default as fallback; project override takes precedence; ChatToolbar AutonomyPill becomes read-only
- **Rejected:** Per-message toggle, global-only setting

---

### ADR-007: task_updated event for description edits
- **Date:** 2026-04-11
- **Section:** Test Phase — Task Edit
- **Context:** Description editing needed for pending tasks, but no update mechanism existed.
- **Decision:** New task_updated event type + PATCH /api/projects/:id/tasks/:taskId/description endpoint
- **Rationale:** Consistent with event-sourced architecture. Only pending tasks can be edited (running tasks are owned by Claude).
- **Consequences:** EventStore processes task_updated to merge description; API validates pending status
- **Rejected:** Direct in-memory mutation without event (loses auditability)

---

### ADR-008: Path traversal prevention in doc-index
- **Date:** 2026-04-11
- **Section:** Build — 10-api-routes
- **Context:** GET /api/projects/:id/docs?file=path reads arbitrary files within project directory
- **Decision:** Resolve path with path.resolve(), verify startsWith(projectDir) before reading
- **Commit:** d21e143
- **Rationale:** OWASP path traversal prevention; defense in depth even for local-only app
- **Consequences:** Prevents ../../etc/passwd style attacks; returns 400 AppError on violation
- **Rejected:** No validation (local app argument), regex-based filtering (bypassable)

---

### ADR-009: Persistent Claude CLI Process via --input-format stream-json
- **Date:** 2026-04-12
- **Section:** Iterate — persistent-process
- **Context:** Spawn-per-message Claude CLI via print mode (-p) incurred 5-10s cold start on every chat follow-up (plugin loading, API handshake, session setup). User feedback: 'Wenn ich jedes mal 10s warten muss drehe ich durch'. Completely unacceptable for an interactive chat.
- **Decision:** Run exactly one persistent Claude CLI process per active task using --input-format stream-json + --output-format stream-json. Send user messages as NDJSON on stdin via a new sendUserMessage(proc, content) API. Process stays alive for the entire task conversation. Task lifecycle events (phase_started, work_completed, work_failed) emitted via the adapter's onExit callback.
- **Commit:** ec9b0e1
- **Consequences:** Measured 6x speedup: initial cold start 15.35s (one-off per task) → follow-up 2.57s (warm, just API latency). SessionRegistry and its 8 unit tests deleted (~350 LOC removed). chat.ts POST handler simplified from respawn+resume flow to single sendUserMessage call. Multimodal image input became straightforward (just content block arrays on the same pipe). No --permission-mode mid-task switching without respawn (acceptable for v0.1).
- **Rejected:** --sdk-url ws:// WebSocket mode (hidden .hideHelp() flag in Claude CLI source, marked unstable); per-message respawn with --resume <sessionId> (tried in 60167fa, required SessionRegistry to map our UUID to Claude's real session_id from system/init events, still cold-started on every message).

---

### ADR-010: Companion MarkdownContent Port (MIT) for chat rendering
- **Date:** 2026-04-12
- **Section:** Iterate — chat-rendering
- **Context:** Hand-rolled @tailwindcss/typography prose classes broke markdown tables in the chat: cells collapsed into each other (e.g., 'SpieleTordiff.Punkte' instead of 'Spiele | Tordiff | Punkte'). Users also wanted a VS Code-extension feel (flat messages, no avatar) and image upload. User explicit direction: 'Können wir das nicht von dem companion repo kopieren? Möchte nicht alles nochmals durchmachen'.
- **Decision:** Port the MarkdownContent sub-component from The-Vibe-Company/companion/web/src/components/MessageBubble.tsx (MIT license) into webui/client/src/components/chat/MarkdownContent.tsx. Use explicit react-markdown component overrides for every element (h1-h4, p, ul/ol/li, table/thead/th/td, blockquote, hr, code, pre, a, strong, em) instead of relying on @tailwindcss/typography. Swap companion's cc-* Tailwind tokens for our CSS custom properties (--color-primary, --color-border, --color-muted-bg). Also port readFileAsBase64 helper from companion/web/src/utils/image.ts for clipboard paste support.
- **Commit:** 15928b8
- **Consequences:** All common markdown artifacts render correctly including tables with proper borders. Image upload feature lands alongside (paperclip button + clipboard paste + thumbnail strip). MIT attribution obligation added to CHANGELOG and file headers. Future updates from companion upstream are now a simple copy-merge operation. Same stack (React 19 + react-markdown + remark-gfm) so no new dependencies.
- **Rejected:** Fix prose classes in place (fragile, ongoing maintenance burden for every table edge case); adopt a different Markdown library (unnecessary churn, same risk); write ad-hoc CSS overrides (already tried, user rejected).

---

### ADR-011: VS Code Permission Modes — Default is bypassPermissions
- **Superseded by:** ADR-022 (2026-04-13) — mid-task mode switching is now supported via `--resume` respawn. ADR-011's "v0.1 not supported" stance no longer applies; the underlying reasoning (per-message respawn cost from ADR-009) doesn't apply to explicit one-off user actions.
- **Date:** 2026-04-12
- **Section:** Iterate — permission-modes
- **Context:** The legacy 'Default | Plan | Auto-accept' permission dropdown was confusing and none of its values were actually wired to the Claude CLI spawn arguments. The adapter always used --dangerously-skip-permissions regardless of user selection. User asked for VS Code-style modes matching their mental model from the VS Code Claude extension.
- **Decision:** Adopt the exact same 4-mode system as VS Code's Claude extension: Ask before edits (default) / Edit automatically (acceptEdits) / Plan mode (plan) / Bypass permissions (bypassPermissions). UI default = bypassPermissions (matches VS Code ship default). Wire client mode selection through POST /tasks body → coercePermissionMode validator → governor.acquire → adapter.spawn. Adapter picks --dangerously-skip-permissions for bypass or --permission-mode <mode> otherwise. Legacy localStorage values (default/plan/auto-accept) auto-migrated on read.
- **Commit:** 27fce3a
- **Consequences:** Client and server now consistent with Claude CLI's --permission-mode flag. Default matches VS Code expectation. Mid-task mode switching is NOT supported in v0.1 (would require process respawn or undocumented control_request protocol) — selected mode locks in for the whole task conversation. Popover closes on select via Popover.Close asChild wrap (265ec07).
- **Rejected:** Keep legacy names (doesn't match CLI flag semantics, user confusion persists); hide the mode selector entirely (loses power-user control, bad UX for people running untrusted prompts); use raw CLI mode names only without friendly labels (bypassPermissions is unfriendly in chat).

---

### ADR-012: Rule-based phase detection via classify_phase.py
- **Date:** 2026-04-13
- **Section:** Iterate — phase-detection
- **Context:** Task creation emitted phase_started events with a hardcoded phase of build, which prevented the kanban from reflecting non-build work (design, test, deploy) without manual intervention. Users asked to classify phase from the task description at creation time.
- **Decision:** Add plugins/shipwright-iterate/scripts/lib/classify_phase.py (rule-based keyword + priority tie-break). Expose classifyPhase() in webui/server/src/bridge/intent-classifier.ts. POST /api/projects/:id/classify returns phase + phase_confidence. POST /api/projects/:id/tasks accepts body.phase; when absent, classifyPhase is invoked as fallback. NewIssueModal gains an 8-option phase dropdown with debounced auto-suggest + Sparkle indicator and manual override.
- **Commit:** HEAD
- **Consequences:** Phase_started events now reflect actual work type. UI surfaces an auto-suggest with override. Keyword-based classifier is deterministic, offline, and has no external dependencies. Future work may upgrade to LLM-based classification when latency budget allows.
- **Rejected:** LLM-based classification rejected (latency + cost on a synchronous create path). Hardcoded mapping based on project profile rejected (too coarse, ignores user intent).

---

### ADR-013: Persist requested phase on task_created events; close NewIssueModal classify race
- **Date:** 2026-04-13
- **Section:** Iterate — phase-dropdown-fix
- **Context:** After shipping ADR-012 (phase detection) the dropdown selection was still being lost in two ways: (1) the /api/projects/:id/tasks/:taskId/start route hardcoded phase=build regardless of what the user picked at creation time; (2) NewIssueModal's debounced classify call had no abort mechanism, so an in-flight response would overwrite a user's subsequent manual dropdown pick when it resolved.
- **Decision:** (1) Server: task_created events now carry an optional phase field. EventStore reads it into task.requestedPhase. The /start route resolves the phase as body.phase > task.requestedPhase > classifyPhase(title+description) > 'project'. (2) Client: NewIssueModal tracks phaseIsAuto in a ref (phaseIsAutoRef) and the debounced classify's .then guards against both effect-abort and current phaseIsAutoRef.current before calling setPhase, so a late-arriving classify response cannot clobber a manual selection.
- **Commit:** HEAD
- **Consequences:** Phase dropdown is now authoritative in both immediate-start and deferred-start flows. Task model gains requestedPhase field. Existing task_created events without phase remain compatible (field is optional and EventStore treats missing as undefined). Client event handler uses a ref instead of closure-captured state — standard pattern for 'latest value in async callback'.
- **Rejected:** (a) Re-classify on every /start call (wasteful; user's original intent lost). (b) AbortController for the classify fetch (would work but requires threading signal through apiPost; the ref guard achieves the same goal with less surface change). (c) Storing requestedPhase in a separate event type (phase_requested) — extra event noise for something that logically belongs on task_created.

---

### ADR-014: Fold tool_result into tool_use by toolUseId — live and persisted
- **Date:** 2026-04-13
- **Section:** Iterate — tool-call-merge
- **Context:** Tool-call cards in the chat panel showed 'Running' forever. Root cause: tool_use and tool_result NDJSON events were persisted and rendered as two separate ChatMessage entries. The tool_use card's status came from message.type === 'tool_result', which never becomes true for the tool_use message itself. The NDJSON parser also did not propagate Anthropic's tool_use_id, so there was no key to match a tool_result back to its tool_use.
- **Decision:** (1) Persist both tool_use and tool_result as separate ChatMessages (append-only, lossless), but propagate Anthropic's tool_use_id via a new optional ChatMessage.toolUseId field. (2) Introduce a pure foldToolResults(messages) helper in webui/client/src/lib/ that walks the list once, indexes tool_use by toolUseId, and folds matching tool_result into the parent tool_use by copying content into toolOutput and inheriting isError. Orphan tool_results and legacy messages without toolUseId pass through. (3) ChatPanel folds both the persisted message list and the live streaming list before rendering. (4) ToolCallCard status is now derived from isLegacyResult OR toolOutput !== undefined OR isError, so a folded tool_use correctly transitions to 'Done' / 'Error'.
- **Commit:** HEAD
- **Consequences:** Tool cards now transition from Running to Done in place as soon as the matching tool_result arrives, both during live streaming and when a persisted chat history loads. Chat store remains append-only. Backward compatible with pre-fold histories (tool_use without toolUseId stays 'Running' until a matching result; legacy standalone tool_result messages still render as their own 'Done' card). foldToolResults is O(N) single-pass and pure.
- **Rejected:** (a) Merging at persist time in chat-store — would require rewriting existing jsonl entries which violates append-only. (b) Mutating streamingMessages in useStreamingChat when tool_result arrives — viable but forces an extra state-update pass and couples the hook to the render concern. A pure selector at render time is simpler and testable in isolation. (c) Storing tool_result inline on the assistant message — breaks the type shape and loses the chronological order for tools that span multiple assistant turns.

---

### ADR-015: Extract AskUserQuestion nested schema + dedupe streaming against persisted
- **Date:** 2026-04-13
- **Section:** Iterate — ask-user-card-fix
- **Context:** AskUserCard rendered as two empty yellow boxes with a 'Type your answer...' textarea and a 'Submit Answer' button, but no question text and no suggestion chips. Two root causes: (1) The component read toolInput.question and toolInput.options as if the schema were flat, but Claude Code's built-in AskUserQuestion tool emits a nested shape { questions: [{ header, question, multiSelect: { mode, options: [{ label, description }] } }] }. With the flat keys missing, question fell through to message.content (empty) and options was an empty array. (2) Every NDJSON chat:message event is persisted to chat-store AND broadcast via SSE. useSSE invalidates the chat query on each broadcast, so useChat refetches during streaming and the persisted messages end up containing the same event that is also in streaming.streamingMessages. ChatPanel renders both arrays sequentially, producing two identical cards.
- **Decision:** (1) New pure helper webui/client/src/lib/askUserPayload.ts with extractAskUserPayload(toolInput) that flattens both the nested Claude Code schema AND the legacy flat schema into { question, header?, context?, options? }. Used by AskUserCard.tsx for rendering and by server/index.ts for the inbox path — one extractor, two consumers. (2) New pure helper webui/client/src/lib/dedupeStreamingMessages.ts that removes streaming entries whose stable signature is already present in the persisted messages list. Signature: 'tool:<toolUseId>' for tool_use/tool_result when toolUseId is present, otherwise '<type>:<content-prefix-200>'. ChatPanel pipes streamingMessages through dedupeStreamingMessages BEFORE foldToolResults so the ordering is: persisted → rendered as-is; streaming → deduped against persisted → folded → rendered.
- **Commit:** HEAD
- **Consequences:** AskUserQuestion prompts now render with their actual question text, header tag, and option chips. Legacy flat schema still works. The chat panel no longer double-renders ANY event that landed in both stores during a stream, not just AskUserQuestion — tool calls, text, thinking blocks, everything. dedupeStreamingMessages is pure, O(N+M), and unit-tested. extractAskUserPayload is a single source of truth shared between client rendering and server inbox creation — future schema drift requires only one update.
- **Rejected:** (a) Move dedupe to the SSE layer (don't invalidate chat on chat:message during stream) — couples useSSE to streaming state, messy. (b) Remove the inbox-manager path entirely and let the ChatMessage tool_use be the single surface — breaks the global Inbox page which reads from inboxManager. (c) Use message.id as the dedupe key — IDs are generated independently by the server parser and the client streaming hook, so they never match. (d) Render-time mergeByToolUseId of the streaming list into messages — couples persisted data with live data and breaks the 'persisted is authoritative' invariant.

---

### ADR-016: Kill content_block persistence + displayContent guard + AskUserCard redesign + classifier tiebreak
- **Date:** 2026-04-13
- **Section:** Iterate — chat-dup-root-cause
- **Context:** Live test on port 5177 (2026-04-13) showed iterate 3's dedupeStreamingMessages was not sufficient. Chat shows every tool_use twice, every assistant text twice, and the phase badge on the kanban card displays 'build' for a 'Build a ToDo-App' task instead of 'project'. Root causes were deeper than the streaming-vs-persisted overlap my iterate 3 targeted. Four independent bugs were investigated by pulling the real chat-history jsonl from a recent task and grepping for duplicates: two tool_use AskUserQuestion entries with toolInput differing only by '(Recommended)' suffix appeared 4.6 seconds apart — proof that the server parser was persisting both the partial content_block event and the final assistant event for the same logical tool call. Separately, the assistant text showed twice in the chat because displayContent renders next to its already-persisted copy in messages. And the classifier's tiebreak had 'build' priority over 'project', which made 'Build a ToDo-App' classify as build since both scored 1.
- **Decision:** (A) webui/server/src/core/ndjson-parser.ts — delete the content_block_start/delta/stop handler entirely. Return empty array. Claude CLI emits these events with partial state while generating a content block token-by-token; our client's useStreamingChat hook does not consume them (live text streaming runs off the assistant event's text blocks), so deleting the server-side path only removes the double-persist. (B) webui/client/src/components/chat/ChatPanel.tsx — before rendering the streaming displayContent AssistantMessage, check whether any persisted message already contains that exact text. If yes, suppress the streaming render. Inline pure predicate, no new state. (C) webui/server/src/core/chat-store.ts — defense-in-depth: ChatStore.append maintains an 8-entry, 10-second rolling window of recent message signatures per task. Exact structural duplicates (same type/toolName/content/JSON.stringify(toolInput)/isError) within the window are silently dropped. Prevents any future parser regression or Claude CLI stream quirk from producing duplicate persisted rows. (D) webui/client/src/components/chat/AskUserCard.tsx — visual redesign per user feedback: switch from solid bg-amber-50 to bg-white with border border-amber-200 plus a thick amber-400 left accent bar (border-l-4 border-l-amber-400) and a soft card shadow. Aligns chrome with the white Claude cards in mockup 11 while keeping the 'needs attention' amber signal via the left accent. (E) plugins/shipwright-iterate/scripts/lib/classify_phase.py — remove 'build' from the BUILD phase keyword set (the verb in a user title almost always means 'create', not the Shipwright build phase) AND reorder PHASE_PRIORITY so 'project' wins ties over 'build'. Regression: 'Build a ToDo-App' now classifies as project.
- **Commit:** HEAD
- **Consequences:** (A) No more duplicate persisted tool calls or assistant text from parser double-processing. Chat-history jsonl stays clean. (B) Streaming displayContent and persisted messages no longer show the same text twice during the invalidation window. (C) Defense in depth catches any future quirks. (D) AskUserCard visually aligns with the white-card chat language while keeping the amber-accent attention signal. (E) 'Build a ToDo-App' and similar create-new-app phrasings classify as project; Kanban card phase badge shows 'project' in the default mapping (project -> backlog). Still a separate UX question whether the kanban mapping should put project-phase tasks in in_progress when they are running, but that is not this iterate. All tests green: server 206 (+7), client 198, iterate plugin 59 (+13).
- **Rejected:** (a) Keep the content_block handler and dedupe at render time — would require teaching the dedupe helper about partial-vs-final state of the same logical event, complex and brittle. (b) Move displayContent into streamingMessages so a single dedupe path covers both — would break the useStreamingChat hook contract and force a larger refactor for a one-line fix. (c) Add a delay before persisting content_block events to wait for assistant event — timing-sensitive, unreliable. (d) Special-case 'build a X' via regex in classify_phase.py — too narrow, doesn't cover 'construct a X', 'create a X', etc. Removing the standalone 'build' verb from the keyword set and reordering priority is the general fix.

---

### ADR-017: Correct AskUserQuestion schema path (options direct, multiSelect boolean) + orange accent + thinking label
- **Date:** 2026-04-13
- **Section:** Iterate — chat-polish-plus-restart
- **Context:** Live test of iterate 4 on port 5177 uncovered: (1) the dev server had never been restarted since before iterate 1 — it was running 12h stale code, so all of iterate 1-4's server-side fixes were not in effect (phase_started still hardcoded build, content_block_* still double-persisted, toolUseId not extracted). (2) Even with a fresh server, the AskUserCard still rendered options-as-bullets in the following assistant message instead of chips inside the card, because my iterate-3 extractAskUserPayload read questions[0].multiSelect.options — assuming multiSelect was an object — when the real Claude Code schema has options as a sibling of multiSelect, and multiSelect is just a boolean flag for allow-multiple-answers. Verified by dumping the full toolInput from a chat-history jsonl. (3) The amber color scheme read as yellow against the chat background — user asked for orange. (4) The awaiting-response indicator showed only three tiny bouncing dots with no text — the user described it as just a blinking cursor in the white area, not obviously communicating thinking state.
- **Decision:** (1) Kill the stale webui server (PID 60252, started 2026-04-12 22:36) and restart via npm run dev:server. Confirmed new PID 59168 started 11:10 running iterate-4 code. (2) Rewrite extractAskUserPayload to read options directly from questions[0].options as an array of {label, description} objects. Add allowMultiple boolean derived from questions[0].multiSelect === true. Update unit tests with the verified jsonl-dump shape. (3) Swap AskUserCard colors: bg-white + border-orange-300 + border-l-4 border-l-orange-500 + text-orange-600 header (was amber-200 / amber-400 / amber-600). (4) Replace bare StreamingIndicator in AssistantMessage empty-streaming state with an inline-flex row containing the dots + italic 'Thinking…' label in text-gray-500. More visible signal that Claude is working.
- **Commit:** HEAD
- **Consequences:** Post-restart, all iterate-1..4 server-side fixes finally take effect: phase badge reflects resolvePhase's classify result, content_block_* events are not double-persisted, task_created events carry the phase field, toolUseId propagates so foldToolResults can merge tool_use with tool_result, /start route honors task.requestedPhase. The AskUserCard now renders option chips inside the card (the schema fix was the bottleneck — even a correct visual design can't show chips if the extractor returns undefined). The orange color matches user preference. Thinking state is visible as 'Thinking…' text alongside dots. Still pending user verification: whether Claude's follow-up 'Ich warte auf deine Antwort' text still appears as a separate assistant message after the card (that's Claude's own output, not something we can hide server-side without a tool_result refactor — that's iterate-6 territory).
- **Rejected:** (a) Restart the server via a hook or a package.json watch trigger — too invasive for a one-time fix; manual restart is what the user expects here. (b) Keep the legacy multiSelect.options fallback in the extractor 'just in case' — no — the jsonl dump is authoritative and keeping both paths would hide future schema drift. (c) Use a loud red 'ATTENTION' style for the AskUserCard — too harsh; orange is enough to stand out against the beige chat background.

---

### ADR-018: Reset displayContent per assistant event + inbox id = toolUseId + dev-restart helper
- **Date:** 2026-04-13
- **Section:** Iterate — chat-polish-2
- **Context:** Post-iterate-5 live test surfaced four issues. (1) During streaming, the chat showed a big white card at the bottom containing ALL assistant text from the current stream concatenated together — appendToken in useStreamingChat accumulated text across every assistant event without resetting between turns. iterate-4's Bug B guard in ChatPanel only suppressed displayContent when exactly one persisted message matched it, so the accumulated concat blob never got suppressed. (2) Clicking an AskUserCard option showed 'Answered: X' locally but (a) Claude didn't act on it and (b) page refresh lost the state. Root cause: inbox-manager.addQuestion generated a fresh randomUUID for the inbox item id while the client posted to /inbox/:id/answer using message.id (the ChatMessage UUID, different value) — so the server couldn't find the item (404), and even if it could, 'isAnswered' was purely local React state with no hydration from persisted inbox. (3) Dev server had been running 12+ hours stale with orphaned tsx watch processes because tsx watch on Windows + chokidar sometimes misses git-merge file-swap events, and npm run dev invocations never cleaned up orphan children. (4) Claude emitting a markdown fallback listing all questions after the first AskUserCard is a separate architectural issue (inbox.answer sends plain text instead of a tool_result block referencing tool_use_id) — deferred to iterate 7, not this run.
- **Decision:** (A) useStreamingChat.processNdjsonMessage resets textBufferRef and displayContent at the top of every assistant-event branch, so the display buffer only ever mirrors the CURRENT in-flight assistant turn. Previous turns are already in persisted messages[] via SSE invalidation, and ChatPanel's Bug B guard suppresses the streaming render once messages[] catches up. (B) inbox-manager.addQuestion accepts an optional toolUseId parameter. When provided it becomes the InboxItem.id instead of a random UUID, giving the client a stable correlation key. index.ts's AskUserQuestion detection now iterates the extracted tool_use ChatMessages (covering both standalone tool_use events AND assistant-wrapped content-block tool_use blocks — the latter was completely missed before) and passes the chat message's toolUseId. Client AskUserCard uses message.toolUseId as the inbox id (falls back to message.id for legacy). A new useInboxItem(id) hook reads the persisted inbox item and AskUserCard hydrates its isAnswered + answer display from it, so refresh preserves state. (C) New webui/scripts/dev-restart.js — cross-platform Node script that kills stale tsx watch / vite / node processes owning ports 3847/5173/5177 then respawns npm run dev in webui/server. Exposed as 'npm run dev:fresh' in webui/server/package.json. Documented in webui/CLAUDE.md under Dev-server troubleshooting.
- **Commit:** HEAD
- **Consequences:** Streaming chat no longer shows a concatenated blob at the bottom — only the current turn's text displays, and iterate-4's Bug B guard still kicks in once messages[] has it persisted. AskUserCard submits with the correct inbox id so the server finds the item, marks it answered, and sendStdin actually fires. Refresh preserves the Answered state from server-persisted inbox. Dev server staleness is now a one-command recovery, explicitly scoped as a dev-only concern (production users run compiled code). Tests: server 209 (+3 inbox-manager), client 204 (+5: streaming 3, AskUserCard 2). Still open (iterate 7): Claude's markdown-fallback questions list + Claude not blocking on AskUserQuestion — both require the tool_result refactor in inbox.answer + claude-adapter.sendUserMessage, plus a review of whether the shipwright-project plugin needs instruction alignment (per memory feedback_iterate7_scope).
- **Rejected:** (a) Move displayContent dedupe to chat-store-level fingerprinting — too coupled, would need a new dedupe path just for the streaming render case. The reset-per-event fix is simpler and addresses the actual cause. (b) Use a synthetic id like 'msg.id + tool_use_index' as the inbox id — fragile, breaks on reload. toolUseId is stable and already propagated by iterate 2. (c) Run dev-restart as a git post-merge hook — too invasive; an opt-in npm script gives the same recovery without surprising developers mid-session. (d) Merge the tool_result refactor into this iterate — explicitly user-directed to split (see iterate-6 then iterate-7), and the plugin-side review (memory feedback_iterate7_scope) needs its own investigation.

---

### ADR-019: tool_result blocks unblock AskUserQuestion + inbox latency + plugin scope + ADR budget
- **Date:** 2026-04-13
- **Section:** Iterate — change: tool_result refactor
- **Context:** Iterate-6 made inbox.id == toolUseId, but inbox-manager.answer still sent plain text on stdin so Claude CLI never received a structured tool_result and emitted markdown fallback questions. Inbox-answer also lagged 2-3s before Thinking shows. Plus iterate ADRs grew 1.9-4.7k chars each, bloating Layer-1 context.
- **Decision:** InboxManager.answer sends a tool_result block via adapter.sendUserMessage for `toolu_`-prefixed ids and persists a tool_result ChatMessage; legacy UUIDs keep the plain-text fallback. AskUserCard fires triggerAwaiting via a new ChatAwaitingContext. shipwright-project SKILL + interview-protocol document per-question AskUserQuestion semantics. write_decision_log.py warns on fields >500 chars (forward-only).
- **Commit:** PENDING
- **Rationale:** tool_result is the Anthropic protocol for unblocking a tool call — anything else makes Claude assume the tool never returned. Context (vs prop drilling) keeps AskUserCard isolated from streaming hook internals.
- **Consequences:** Claude CLI now unblocks correctly on AskUserQuestion answers — no more markdown fallback. Thinking indicator fires instantly on inbox submit. New ADRs stay terse without retroactive churn. Tests: server 213 (+4), client 205 (+1), shared 153 (+3 length helper), iterate plugin 59, e2e 17. Backwards compat: legacy UUID inbox items still answer via plain text.
- **Rejected:** useIsMutating polling (clears on mutation success, not on first NDJSON event — wrong gap), lifting useStreamingChat into a context (too invasive), hard-failing on ADR length over budget (would block iterate 7 itself), unconditional tool_result for all ids (breaks legacy).

---

### ADR-020: Persist task_cancelled / work_completed / task_updated to events.jsonl
- **Date:** 2026-04-13
- **Section:** Iterate — bug: task event persistence
- **Context:** tasks.ts /status and /description handlers wrote events only to the in-memory EventStore, never to shipwright_events.jsonl. On server restart the replay rebuilt tasks from the file and deleted/closed/edited tasks came back as pending.
- **Decision:** Add emitTaskCancelledEvent + emitTaskUpdatedEvent helpers in bridge/event-writer.ts, wire them through TaskRouteDeps, and call them from /status and /description handlers BEFORE the in-memory addEvent so a disk failure leaves state untouched. Also wire the existing emitWorkCompletedEvent for the Close path.
- **Commit:** PENDING
- **Rationale:** Symmetric with the task_created path that already persists first then updates memory. Optional deps keep existing tests and non-production consumers working without the emitters wired.
- **Consequences:** Deleted, closed, and edited tasks now survive a server restart. Adds 3 optional fn deps to TaskRouteDeps, all existing call sites forward from index.ts. Tests: server 220 (+7).
- **Rejected:** Adding a DELETE /tasks/:id route (would still need to emit the same event). Writing only to memory and triggering a full snapshot rewrite on demand (inefficient and invites inconsistency).

---

### ADR-021: Inbox projectId + replay + collapse AskUserQuestion noise + model/effort wire-through
- **Date:** 2026-04-13
- **Section:** Iterate — bug: wiring fixes
- **Context:** Iterate-7 live test surfaced 4 wiring bugs: inbox items had empty projectId and never persisted, Claude emits duplicate AskUserQuestion cards + a markdown fallback in one turn, model selector in the toolbar was a placebo, and effort selector was both unwired and missing the VS Code 'max' option.
- **Decision:** index.ts passes the resolved projectId to inboxManager.addQuestion. New inbox-replay helper walks chat-history on startup and reconstructs orphan AskUserQuestions. New collapseAskUserQuestionRun client helper hides post-AskUserQuestion noise until a tool_result lands. claude-adapter.spawn pushes --model alias. New effort-prompt helper wraps the prompt with /think, /think hard or /ultrathink. UI toolbar gains the max effort option.
- **Commit:** PENDING
- **Rationale:** Effort cannot be a CLI flag (Claude Code has no --thinking) so slash-command prefixes are the only real knob. Chat-history is the authoritative source for reconstructing inbox state because inbox.jsonl may be stale or empty after previous bugs.
- **Consequences:** Inbox items survive restart (loadFromDisk + replay). Doppel-cards and Lass-mich-wissen fallback no longer render in the chat. Toolbar model selection actually reaches the CLI. Thinking depth is honored via slash-command prefix. Tests: server 242 (+22), client 213 (+8).
- **Rejected:** Auto-answering orphan inbox items on startup (would break the user's actual intent). Hiding the effort pill entirely (worse UX than a prefix that may or may not work perfectly). Passing --model via env var (flag is cleaner).

---

### ADR-022: Mid-task mode switching via --resume + autonomy sync to shipwright_run_config.json
- **Date:** 2026-04-13
- **Section:** Iterate — change: runtime config
- **Context:** Iterate-9 wiring audit found two remaining runtime-config gaps: ADR-011 said mid-task permission mode switching was 'v0.1 not supported' because per-message respawn cold-started every turn, but a one-off explicit switch is a different tradeoff. Autonomy was stored in projects.json only and never reached the Shipwright plugin chain which reads from shipwright_run_config.json.
- **Decision:** claude-adapter captures Claude's real session_id from system/init; new `resumeSession` flag emits `--resume <id>` in spawn. New `POST /tasks/:id/mode` terminates + respawns with `--resume` + new `--permission-mode`, guarded against pending AskUserQuestion and uncaptured session_id. `projectManager.updateAutonomy` writes autonomy into projects.json AND merges it into `<project>/shipwright_run_config.json` so the plugin chain reads it.
- **Commit:** PENDING
- **Rationale:** ADR-011's rejection was based on per-message respawn cost. For an explicit user action (click Plan Mode), one cold start is acceptable UX. Guarding on pending AskUserQuestion is simpler than synthesizing tool_results for an orphaned tool_use.
- **Consequences:** Users can switch permission mode mid-conversation (one cold start per switch, full history preserved via --resume). Pending AskUserQuestion correctly blocks the switch with a 409. Per-project autonomy is now actually consumed by the plugin chain. Tests: server 253 (+11 for mode endpoint, adapter session-id capture, --resume flag, updateAutonomy sync).
- **Rejected:** Undocumented control_request protocol (too risky). Autonomy read-through from run_config.json at project load (harder to reason about; write-through is simpler). Allowing mid-switch during pending questions (would orphan tool_use entries).

---

### ADR-023: Revert iterate-7 tool_result send (API 400) + inbox filter + model selector fixes + finalization verifier
- **Date:** 2026-04-13
- **Section:** Iterate — bug: UX hotfixes + verifier
- **Context:** Iterate-10 live test surfaced: API 400 on inbox answers (iterate-7's tool_result stdin violates Anthropic's same-turn rule in -p mode), ghost inbox items for deleted tasks, model selector bugs (Sonnet context, popover doesn't close), doc drift (architecture.md stuck at ADR-018, no conventions learnings since iterate 7), stale session_handoff.md.
- **Decision:** `inbox-manager.answer` reverts to plain-text `sendStdin` for all items (chat-store tool_result UI persistence stays). `/api/inbox` filters items whose task is terminal or missing. `ModelSelector` wraps options in `Popover.Close` and sets Sonnet to 1M. Architecture.md retrofits ADR-019-023, conventions.md gains iterate 8-11 learnings, ADR-011 gets superseded note. `generate_session_handoff.py` gains `--project-root` flag; iterate SKILL F11 passes it. New `verify_iterate_finalization.py` + 18 tests enforces finalization completeness.
- **Commit:** PENDING
- **Rationale:** Root cause of iterate 7 was treating -p stream-json Claude as a blocking tool caller. It's not — tool_use is advisory emission. Plain text fixes the API contract; collapseAskUserQuestionRun from iterate 9 hides the cosmetic fallback.
- **Consequences:** API 400 eliminated — answering from inbox now works. Inbox shows only live items. Model selector closes on select with correct context. Iterate 12 can build on the verifier. Tests: server 268 (+15), client 213, shared 171 (+18 verifier), e2e 17.
- **Rejected:** Keep tool_result path for some heuristic subset (complex, fragile). Delete ADR-011 entirely (loses ADR history). Full Companion Zustand rewrite (deferred to iterate 13). Stopping effort via slash-command prefix (stays — no CLI flag exists).

---

### ADR-024: Inbox dedupe by normalized question + zombie-task filter (no live process)
- **Date:** 2026-04-13
- **Section:** Iterate — bug: inbox dedupe + zombie filter
- **Context:** Iterate 11's inbox filter reduced 8 → 6 items but left two remaining noise sources: (1) Claude's same-turn duplicate AskUserQuestions each got their own toolu_id and both passed through to the inbox; (2) tasks marked running in the event store but whose Claude process had died still leaked their pending items.
- **Decision:** inbox-manager.addQuestion dedupes by normalized signature (taskId, normalize(question)) for pending items — first-write-wins, returns existing. /api/inbox filter extended with governor.getProcess(taskId) check: running status but exited/missing process = zombie → filtered.
- **Commit:** PENDING
- **Rationale:** First-write-wins dedupe matches iterate 9's client-side collapse behavior — consistent UX across chat and inbox. Route-level governor check is the minimum-risk hotfix; real fix is event-store level.
- **Consequences:** Inbox now shows only live items for tasks whose Claude process is actually running. Claude's per-turn duplicate tool_use pattern no longer pollutes the list. Architectural cleanup of zombie detection (emitting a synthetic task_orphaned event on startup) is deferred to iterate 12 — the route-level filter is a band-aid that iterate 12 will replace with proper state.
- **Rejected:** Time-window dedupe (fragile), signature-by-content-hash (over-aggressive for intentionally similar questions across turns), emitting task_orphaned events on server startup (correct but bigger — iterate 12).

---

### ADR-025: Revert 11.1 zombie filter + show latest pending inbox item per task
- **Date:** 2026-04-13
- **Section:** Iterate — bug: inbox latest-per-task
- **Context:** Iterate 11.1's governor-based zombie filter was too aggressive — after a server restart the governor's activeProcesses map is empty, so ALL items from previously-running tasks were hidden even though the user wanted to see them (to clean up or restart). User expected to see the current question per task, not all accumulated ones.
- **Decision:** Revert iterate 11.1's /api/inbox governor.getProcess zombie check (keep the parameter as _governor for 5-arg signature compat). Add a 'latest pending per task' filter: for each task with pending items keep only the one with the most recent createdAt. Terminal-task filter (iterate 11) and addQuestion dedupe (iterate 11.1) stay.
- **Commit:** PENDING
- **Rationale:** 'Latest per task' is the user's mental model — they want to see what Claude is currently waiting on, not every historical request. It also handles zombies gracefully: dead tasks show their last question so the user can decide to delete or restart.
- **Consequences:** Both iterate-9's same-turn-duplicates AND iterate-11-context's 4-questions-from-interview accumulation are naturally collapsed by one rule. User sees exactly one current question per task, with answered items preserved. Server 277 (+1 net).
- **Rejected:** Keep the zombie filter + add latest-per-task (double filtering, confusing). Emit task_orphaned events on startup (correct but architectural — iterate 12).

---

### ADR-027: Iterate 14 omnibus — phase cleanup, multi-question inbox, pipeline entry, constitution discipline
- **Date:** 2026-04-15
- **Section:** Iterate 14 (7 sub-iterates)
- **Context:** Iterate 13 chat UX rebuild exposed follow-ups during a TodoApp4 live-test: (1) `iterate` / `preview` phases were incorrectly added to the dropdown in 13; (2) no UI entry point to start a new Shipwright pipeline; (3) `Ctrl+Shift+N` opened Chrome Incognito instead of NewIssueModal (OS-level browser reservation); (4) `AskUserQuestion` payloads with N>1 questions silently dropped questions 2-N (`askUserPayload.ts` read only `questions[0]`); (5) Claude CLI in stream-json mode does not gate `tool_use` on matching `tool_result`, so Claude sometimes kept generating after AskUserQuestion; (6) Model label was hardcoded "Opus 4.6".
- **Decision:** Split into 7 sub-iterates (matches iterate 12.x pattern). Plan reviewed by Gemini 3.1 Pro Preview + GPT-5.4 via `shared/scripts/lib/llm_review.py` — revisions applied before implementation (critical: reject "plain user message" submit path in scope 9, fix `getProjectMode` terminal-status coverage, per-line JSONL validation vs blunt-wipe, clarify pipeline bootstrap ownership, swap Ctrl+K for Linear-style letter shortcuts). Scopes: (1) phase dropdown cleanup, (2) preview button + profile-loader + run plugin profile field, (3) getProjectMode + iterate auto-detection, (4) multi-question inbox `parts[]` schema, (5) constitution AskUserQuestion stop rule, (6) CreateMenu + NewPipelineModal + C/Shift+C shortcuts + `/api/profiles` + `/api/projects/pipeline` with path safety, (7) shipwright-project intro gate + `write_run_config.py`, (8) Playwright E2E suite +7 specs, (9) red-flag banner visual only (no submit-path changes), (10) dynamic model label.
- **Commit:** ca30350 → 5ec16ff → 483c3b1 → c48fc1a → 13c3f79 → 9366dc6 → b123339
- **Rationale:** Splitting follows the iterate 12.x precedent — smaller blast radius per commit, independent testing per sub-iterate, easier rollback, matches the autonomy preference (one plan, many executions, no continue gates). Profile-based preview detection (scope 2) preferred over package.json fast-path for architectural cleanliness — the run plugin owns the profile field, webui just reads it. Plugin bootstrap ownership resolved (scope 7): webui OR plugin writes `shipwright_run_config.json`, never both; plugin writes directly via `write_run_config.py`, not by invoking `/shipwright-run` skill (ambiguous skill-call path). Constitution rule (scope 5) placed in `shared/constitution.md` rather than per-plugin duplication — 12 plugins already reference it. Red-flag banner (scope 9) is visual-only because the reviewer flagged that "Answer anyway as plain user message" violates Anthropic API protocol (every `tool_use` requires matching `tool_result`). Letter-based shortcuts (c / Shift+C) over Ctrl+K because Ctrl+K is the universal command-palette standard (Slack/Linear/Notion) and semantically wrong for a create menu; letter shortcuts are Linear-style and have zero browser collisions.
- **Consequences:** webui/server tests 274 → 343 (+69), webui/client tests 246 → 286 (+40), Playwright 8 → 15 specs (33 tests), shipwright-project tests 31 → 43 (+12), shipwright-iterate tests 62 (baseline unchanged). Plugin-side changes (shipwright-run SKILL.md, shipwright-project intro gate + new script, shared/constitution.md) synced to runtime via `scripts/update-marketplace.sh`. InboxItem schema is now `parts[]` — legacy v1 entries auto-purged via per-line validation on load (preserves valid entries, rewrites file). `POST /api/projects/pipeline` exposes a user-input filesystem write surface — path safety is critical (traversal reject, isDir, duplicate, existing-config 409). Model label is now dynamic from `system/init.model` event, falling back to "Claude" when not yet received. Inbox multi-question accordion blocks Submit until all parts answered (no partial submissions). `getProjectMode()` covers both `completed` and `complete` status values (webui/shipwright_run_config.json uses `complete`, other projects may use `completed`). `notBlocked` field persists across reconnect via JSONL roundtrip; server-side detection via pure state machine in `ask-user-guard.ts` is fully unit-testable without Claude.
- **Rejected:** Force-continue as single large iterate (10 scopes in one commit/branch — unreviewable, no rollback granularity). Ctrl+K shortcut for CreateMenu (command-palette semantic collision — reviewer flag). "Answer anyway" as plain user message (violates Anthropic API protocol — Gemini reviewer critical finding). Blunt-wipe inbox JSONL on schema mismatch (too aggressive — per-line validation preserves valid entries). Plugin invoking `/shipwright-run` skill from within its own turn (skill-call ambiguity — reviewer flag). Ctrl+Shift+K as Firefox Web Console collision backup (non-overridable at browser level). Package.json fast-path for preview detection (deferred to future iterate when non-JS stacks exist). Per-ADR-per-sub-iterate (7 ADRs for one cohesive plan is overhead — one omnibus ADR mirrors the plan structure).

---

### ADR-028: Iterate 14.7 — Post-launch fixes, multi-project kanban, interrupted task status
- **Date:** 2026-04-15
- **Section:** Iterate 14.7 (3 sub-iterates)
- **Context:** Manual testing of iterate 14 surfaced: (1) `task_orphaned` events emitted at server startup by iterate 12.0b's zombie reconciliation mapped running tasks to `backlog`, losing the visual "was in progress" signal when server restarted (dev:fresh, crash, intentional); (2) Kanban "All Projects" selection silently redirected to first project via a forced auto-select effect; (3) reload reset selected project to first in list; (4) ModelSelector + 14.6's dynamic model label were redundant and confusing; (5) Browse buttons in project wizard returned folder name only (browser sandboxing — `showDirectoryPicker` cannot return absolute paths); (6) inbox items were dead-end (no way to jump to task chat); (7) NewIssueModal had no visible indication of project mode (pipeline/iterate/standalone); (8) Claude sometimes asks decision questions as markdown numbered lists instead of AskUserQuestion tool use, bypassing inbox; (9) All-Projects aggregation showed cards indistinguishable by source project.
- **Decision:** Split into three sub-iterates: **14.7.0** P0 blockers (task persistence + all-projects + localStorage), **14.7.1** P1 UX polish bundle (model selector sync + paste buttons + inbox nav + mode badge + constitution rule), **14.7.2** P2 multi-project kanban visual distinction (colored left-edge strip + monochrome phases + filter chip + sidebar legend). Executed autonomously without external LLM review (scope is UX polish + one state-machine addition for `interrupted` status, no architectural risk). Key technical decisions: (A) New `interrupted` kanban status distinct from `orphaned` — added new `session_captured` event emitted on first `system/init` per task so `session_id` persists across process restart (ADR-022 had left it in-process only); `POST /tasks/:id/resume` reuses ADR-022's `--resume <sessionId>` spawn path. (B) Browse → Paste rename is the honest UX because browser sandboxing forbids path disclosure; `navigator.clipboard.readText()` with `looksLikePath()` heuristic. (C) ModelSelector `userOverride` flag resets on task switch; auto-sync only applies until user manually picks. (D) Deterministic project color via `projectId` string hash → 12 HSL hues; monochrome phase badges when project strip is visible to prevent color overload. (E) Constitution extension in 14.7.1 P1.8 ships the markdown-questions-forbidden rule in one place (picked up by all 12 plugins already referencing `shared/constitution.md`).
- **Commit:** 9dea2f8 → 035e4df → 9862ed8
- **Rationale:** Autonomous execution matches the `feedback_iterate_autonomy` preference. Per-sub-iterate branches give rollback granularity and keep each agent's scope manageable. Resume button per-task (not bulk) because this is primarily a dev scenario — tasks interrupted by intentional server restart, rare in sustained operation. `interrupted` + `backlog` are intentionally distinct statuses rather than collapsed: `interrupted` means "was running and is resumable", `backlog` means "never started or died unrecoverably". Stripe + monochrome phases in All-Projects mode respects the rule of thumb "one color dimension at a time" — when cards need to show project identity, phase colors would compete for attention.
- **Consequences:** webui/server tests 343 → 356 (+13, 14.7.0 only — 14.7.1 and 14.7.2 touched no server code). webui/client tests 286 → 339 (+53 across 14.7.0 +12, 14.7.1 +28, 14.7.2 +13). Plugin baselines unchanged. Playwright 33 specs preserved with one (15-model-label) updated for the 14.7.1 label deletion. `shared/constitution.md` touched in 14.7.1 → `scripts/update-marketplace.sh` ran at finalization to sync the plugin cache. New dependencies on existing ADR-022 infrastructure: `session_id` capture pipeline is now persisted via event log (was in-process only); future iterate may want to also persist full conversation state for hard-crash recovery. Test baseline shifts: consumers of `webui/client/src/components/chat/ChatToolbar` that reference `running-model-label` testid will break — updated in this iterate, noted for future reference. `TaskCard.tsx` now carries logic from both 14.7.0 (interrupted pause icon) and 14.7.2 (project strip + monochrome phase prop) — single file has three conditional rendering modes that interact, future maintenance should be mindful. `ProjectFilterChip` state lives in KanbanPage alongside `activeProjectId`; localStorage persistence from P0.3 currently persists `activeProjectId` only, NOT the filter chip selection — reload resets filter to "all selected" which is acceptable as a fresh start signal.
- **Rejected:** Bulk Resume button (header "Resume all N") — deferred as premature optimization for dev-only scenario. Supervisor dependency like pm2/systemd as a prerequisite — existing `install-windows.ps1` handles Windows autostart via VBS wrapper; Mac/Linux equivalents deferred to post-14.7 install-docs backlog. Auto-resume on startup — too magical, hides errors (tasks may be in broken state when interrupted). Merging interrupted into existing `orphaned` status — loses the "resumable" vs "dead" distinction. `showDirectoryPicker` as real Browse implementation — File System Access API deliberately hides absolute paths for security. Per-ADR-per-sub-iterate — one omnibus ADR mirrors the plan structure (same pattern as ADR-027 for iterate 14).


---

### ADR-029: Last-write-wins chatStore + spawn indicator sans message-gate + AUQ submit error surfacing
- **Date:** 2026-04-17
- **Section:** Iterate — bug: post-14.13 bug sweep
- **Context:** Four distinct bugs surfaced after 14.13 user-testing: (1) ModelSelector desynced from chat system/init after mid-task model switch because setSystemInit was first-write-wins; (2) second AskUserQuestion submit sometimes stalled with no Claude response and no visible error; (3) Inbox\u2192Task click hit react-router 404 because the nav target used a non-existent nested route; (4) 14.13 spawn indicator never rendered because its gate required messages.length === 0, but the user's initial prompt populates that array on task create.
- **Decision:** chatStore.setSystemInit switched to last-write-wins when the model id differs (idempotent on identical writes). ChatPanel REST hydration now seeds from the LATEST system message, not the first. Spawn indicator render condition dropped the messages-length gate and renders at the bottom of the message list while awaitingInit is true; the generic leading indicator is suppressed while the spawn indicator owns the slot. InboxPage navigates to the existing /tasks/:taskId route (projectId is resolved client-side from the task object). AskUserCard now surfaces mutation errors via an inline banner + optimistic rollback; inbox-manager logs each answer delivery for runtime forensics of the still-unreproduced Bug 2 stall.
- **Commit:** pending
- **Rationale:** First-write-wins was correct for 14.6's duplicate-SSE concern but broke 14.12's respawn scenario; last-write-wins preserves both properties by short-circuiting on identical models. Router fix is a trivial path correction. The messages-length gate was a 14.13 oversight: the empty-chat case it was built for also populates messages[] with the initial user prompt. Error surfacing and observability log were added because Bug 2 cannot be reliably reproduced from the server-side tests (passed first try)\u2014the next occurrence needs client + server signals to debug.
- **Consequences:** Mid-task model switch now updates both ModelSelector and the chat session-started line in lockstep. Inbox deep-links work again. Spawn indicator shows for the full 1-2s boot gap. If the answer POST fails silently (e.g. Process no longer running after a respawn race), the user sees the error instead of a frozen spinner. Bug 2 runtime root cause (Claude CLI behavior post-result) not yet pinned down; observability log + client error banner narrow the reproduction surface for the next user session.
- **Rejected:** Clearing the chatStore on useSwitchModel.onMutate instead of changing setSystemInit semantics: narrower fix but leaves the REST-hydration path still picking first-system/init which breaks on page reload after switch. Adding the nested /projects/:id/tasks/:id route instead of dropping the prefix: more surface area with no user benefit since useTasks already resolves projectId. Retrying the answer POST automatically on 400/500: masks the underlying stall and ships a potentially amplified bug.

---

### ADR-030: Mid-task model switch pending-target UX + spawn indicator task-undefined + empty-prompt suppression
- **Date:** 2026-04-18
- **Section:** Iterate — bug: modelswitch-spawn-ux
- **Context:** Campaign assistant-ui-migration UAT revealed: (1) fresh-task spawn indicator never rendered because the awaitingInit gate required task loaded (task=undefined transient state missed the window), (2) mid-task model switch had no visual feedback for the 1-2s CLI respawn because isSwitching tracked only the 200ms mutation, and (3) every respawn emitted an unsolicited 'Nachricht leer' assistant message because tasks.ts:774 passed prompt: '' through to claude-adapter.sendUserMessage which wrote {content:''} to CLI stdin.
- **Decision:** Client: ModelSelector gains pendingTargetModel prop rendering target label + spinner until systemInitModel catches up. ChatToolbar owns the state machine (clear on systemInit match, on mutation error, or 15s timeout) and surfaces inline error banner (model-switch-error testid). ChatPanel awaitingInit widens to trigger when task is undefined/errored and systemInit is empty. Legacy dezent weisser leading-indicator removed. Server: claude-adapter.sendUserMessage guards empty/whitespace content — skips stdin write entirely, preventing the 'leere Nachricht' artifact on every respawn.
- **Commit:** pending
- **Rationale:** Tracking the respawn via systemInit rather than mutation isPending is the only way to bridge the client-server timing gap without polling. pendingTargetModel is stateful in ChatToolbar (not ModelSelector) so ChatToolbar can coordinate multiple signals (useSwitchModel.isPending, useSystemInitModel, timeout). Empty-prompt guard in adapter is the narrowest fix: the mode-switch endpoint's prompt:'' placeholder semantics are preserved (no new API) while stdin stays clean.
- **Consequences:** New tests: adapter 2, ModelSelector 4, ChatToolbar 2, ChatPanel 2, Playwright 3 = 13 new green gates. Client 475/475 (was 467), server 404/404 (was 402). tsc unchanged. The pending-target visual gives continuous feedback across the full respawn window; errors (409 pending AUQ etc.) are surfaced inline instead of silent drop. The 'leere Nachricht' ghost message is eliminated for all future model/mode switches. 4.6->4.7 second-switch silent-failure case is now either visibly successful (pending-target shows 4.7 until system/init arrives) or visibly errored (banner shows server error).
- **Rejected:** Client-side 1-2s delay before resolving the mutation (blocks retry, opaque to user). Server-side wait-for-system/init before returning from /mode endpoint (couples HTTP timeout to CLI boot, fragile). Synthetic 'ignore me' sentinel prompt on stdin (CLI would still surface it as a user turn). Adding optimistic ModelSelector state (label flips immediately to target even on failure — misleading).

---

### ADR-031: Second-round UAT fixes: new-task model precedence, ghost bubble, resume UX
- **Date:** 2026-04-18
- **Section:** Iterate — bug: modelswitch-uat-round2
- **Context:** UAT after ADR-030 landed surfaced 5 follow-ups: (1) new tasks used localStorage model (e.g. 4.6 from a prior switch) instead of settings.defaultModel (4.7); (2) a ghost empty assistant bubble rendered after 'Starting Claude'; (3) orphan Resume banner only triggered for stale_on_startup | user_interrupted, missing other reasons like switch_timeout; (4) resume did not re-trigger the spawn indicator because the old system/init was still in the chatStore; (5) 409 'Session not yet established' errors left the user stuck with no retry affordance.
- **Decision:** Client-only fixes. useCreateTask reads settings.defaultModel directly (not localStorage) for new-task body.model. ThreadMessage in ThreadView returns null when all content parts are empty (kills the ExternalStoreRuntime running-reply placeholder ghost). TaskHeader isInterrupted widened to 'orphaned && !!claudeSessionId' (drops the 14.11 narrow reason list). useResumeTask's onMutate clears systemInitByTask[taskKey]. ChatToolbar adds a Retry button inside model-switch-error for transient 409s (max 3 attempts).
- **Commit:** pending
- **Rationale:** Model precedence: new tasks are a global-settings concern (user's default), mid-task switches are session-scoped (user's in-flight override). Splitting them at the consumer is cleaner than building a smart merging rule in useChatSettings. Ghost bubble: filtering at the renderer is safer than fighting the runtime; the guard is a one-line content check. Resume clearSystemInit: mirrors the pattern of fresh task creation where the store is empty. Retry button: narrower than auto-retry (no magic), lets the user see the error first.
- **Consequences:** New tests: useCreateTask +1, useResumeTask +2 (new file), TaskHeader +2, ChatToolbar +3, ThreadView +2 = 10 new specs. Client vitest 485/485 (was 475). Server vitest 404/404 unchanged. tsc clean. Playwright +0 new specs (unit coverage sufficient for these UX touches). Server-side concerns unchanged: the 409 itself and the switch-timeout orphan flow stay on the CLI / server side.
- **Rejected:** Auto-retry on 409 with backoff (hides errors, can amplify a broken respawn). Removing localStorage model entirely (breaks in-chat send-model scope). Making systemInit always clear on any task.status change (too aggressive, breaks idempotent duplicate SSE).

---

### ADR-032: Multi-select split(', ') bug + notBlocked banner slimmed + switch timeout 15s->30s
- **Date:** 2026-04-18
- **Section:** Iterate — bug: askuser-multiselect-bugs
- **Context:** UAT surfaced three regressions: (1) AskUserCard multi-select could not toggle labels containing ', ' (e.g. 'Grundfunktionen (Erstellen, Abhaken, Löschen)') — the option appeared unselectable while internally every click accumulated a duplicate copy (20+ in one inbox trace); (2) the notBlocked banner was visually dominant, distracting from the actual question; (3) PENDING_SWITCH_TIMEOUT_MS=15s triggered on otherwise-successful switches when CLI cold-start + Windows Defender + plugin discovery exceeded 15s.
- **Decision:** Split AskUserCard's partAnswers map into two: textAnswers:Record<number,string> (single-select pick + free-text) and multiAnswers:Record<number,string[]> (multi-select labels, array in selection order). Join with ', ' only at submit time. Banner slimmed: text-xs + px-2 py-1 + size=11 icon + one-line wording. Timeout widened to 30s.
- **Commit:** pending
- **Rationale:** Array state is the only reliable fix — no separator is guaranteed not to appear inside labels emitted by Claude. String-join at submit keeps the API wire format stable. Timeout: runtime evidence (Demo 2 task cea73f00 switch took ~5s) suggests 15s was the happy-path budget; 30s tolerates Windows antivirus overhead.
- **Consequences:** Multi-select labels containing ', ' now toggle cleanly (2 new specs verify). Banner still alerts but no longer dominates. Timeout tolerates slow CLI respawns. Client 487/487 (was 485). tsc unchanged.
- **Rejected:** Escape ', ' with a sentinel before join (brittle — labels can contain anything). Change API to accept string[] directly (out of scope, larger refactor). Auto-retry on switch timeout (hides real failures).

---

### ADR-034: External-launch pivot (Plan D'' variant a)
- **Date:** 2026-04-19
- **Section:** Iterate — campaign: webui-acp-pivot (Plan D'' variant a)
- **Context:** The in-webui chat architecture (iterates 14.x) repeatedly bled under the combined pressure of NDJSON heuristic parsing, assistant-ui state ownership, Claude CLI upgrade churn, and the subscription-vs-API-key constraint. Plan D (ACP host) died on upstream abandonment of `claude-code-acp`; Plan D' (SDK-direct via `@anthropic-ai/claude-code`) died when Anthropic retired the importable library surface and split `@anthropic-ai/claude-agent-sdk` behind an API-key gate (rejected: subscription-auth is load-bearing). Plan D'' revives Plan A now that `claude --session-id <uuid>` exists as a first-class CLI flag, closing the session↔task correlation gap that originally killed it.
- **Decision:** Remove all in-webui chat runtime. Webui generates a UUID at task creation, emits a Copy command (`claude --session-id <uuid> --add-dir <cwd> [--resume <uuid>] [--plugin-dir <…>]` in PowerShell / cmd.exe / POSIX forms), and polls `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl` for state. Server is stateless on transcript reads (client passes `fromByte` + `expectFingerprint`). Filename-first discovery (per Sub-iterate 0 PoC finding 1 — fork-session JSONLs begin with `file-history-snapshot` lines that carry no sessionId). Variant-a narrow scope: Copy launcher only (Terminal + VSCode + Desktop deferred to v2+); polling only (no SSE for transcript, no chokidar watchers); in-browser transcript viewer is read-only (no compose input).
- **Commit:** 4d329ed → next push (autonomous campaign across sub-iterates 0→3).
- **Rationale:** The 14.x history is architectural evidence that coupling webui to the CLI's stdio surface is unsustainable under upstream churn. External launch inverts the dependency: webui observes a file that Anthropic produces, and Anthropic owns the hard UX work (permission prompts, thinking display, plan mode). Webui becomes a task board + transcript reader + diagnostic surface. Scope cuts (no Terminal/VSCode launchers, no chokidar, no SSE transcript) are endorsed independently by both external reviewers (GPT-5.4 + Gemini 3.1 Pro) across three review rounds; landing a narrow v1 avoids replaying the 14.x failure class.
- **Consequences:**
  - Deleted server modules: claude-adapter, ndjson-parser, process-governor, chat-broadcast, chat-store, inbox-manager, inbox-replay, ask-user-guard, task-manager, event-store, heartbeat, file-watcher, sse-manager, capability-probe, all bridge/*, old chat/tasks/inbox/capabilities/classify/sse/pipeline/docs routes.
  - Deleted client surface: chat-rendering/, components/chat/, components/board/, components/detail/, components/explorer/, components/viewer/, chat-specific hooks, Kanban page, old TaskDetailPage.
  - Deleted deps: `@assistant-ui/react`, `@anthropic-ai/claude-code`, `claude-code-acp`, `@zed-industries/agent-client-protocol`, `tree-kill`, `uuid`, `node-cron`, `chokidar`, `react-markdown`, `mermaid`, `react-diff-viewer-continued`, `rehype-highlight`, `remark-gfm`, `@radix-ui/{collapsible,popover,scroll-area}`. 318 client + 51 server packages pruned.
  - New production modules: core/{launcher, session-watcher, session-parser, inbox-derive, sdk-sessions-store, cli-compat}, routes/diagnostics, external/routes. New pages: TaskBoardPage, TaskDetailPage (rewrite), DiagnosticsPage, InboxPage (rewrite). New hooks: useExternalTasks, useLaunchTask, useTaskTranscript, useExternalInbox, useDiagnostics. New Playwright specs 30/32/33/34/35.
  - Test coverage: server 131/131 + client 177/177 + Playwright 11/11 (all green).
  - MIN_SUPPORTED_CLI = `2.1.114` pinned in `core/cli-compat.ts`, surfaced via `/api/diagnostics` + `DiagnosticsBanner`. Older CLIs show a persistent warning banner.
  - Config + settings migration: `<registryDir>/sdk-sessions.json` is the new authoritative task store (schema-versioned, lockfile-guarded, per-row fault isolation). Legacy `chat-history/*.jsonl` and `shipwright_events.jsonl` are no longer read or written by webui. Projects on main pre-pivot continue to work with rollback via `main@040c27e`.
- **Rejected:** In-webui chat via CLI-boundary wrapper (Plan B''; same 14.x risk profile). API-billing Agent SDK (violates subscription invariant). Pinning `@anthropic-ai/claude-code@1.0.128` for the retired library surface (stuck on a year-old CLI). Forking `claude-code-acp` (multi-day bridge rewrite against an abandoned upstream).
- **Rollback:** Revert to `main@040c27e` restores the pre-pivot chat architecture. External-launch artifacts (`~/.claude/projects/<cwd>/<uuid>.jsonl`) persist — users can resume those sessions directly via `claude --resume <uuid>` from the CLI even without webui.

---

### ADR-035: Iterate 2 — title integration via `--name`, rendering libs, and doc-sync strategy
- **Date:** 2026-04-20
- **Section:** Iterate — campaign: webui-ui-polish (Iterate 2 / Plan D'' follow-on)
- **Context:** ADR-034 shipped a minimum-viable read-only transcript: vertical event cards, no markdown, no syntax highlighting, no auto-scroll, no virtualization. Task-board cards lacked metadata; Inbox items were JSON dumps. User-assigned task titles existed only inside webui — invisible in the terminal's `claude --resume` picker. PoC (Sub-iterate 2.0) confirmed Claude CLI 2.1.114 exposes `-n, --name <name>` as a first-class flag pre-seeded at launch, and the `custom-title` + `agent-name` events appear in the JSONL with a stable schema. Six sub-iterates (2.1 → 2.5) were planned + externally reviewed (GPT + Gemini) before execution.
- **Decision:** Title integration via Claude's first-party `-n, --name <title>` CLI flag at every launch. Webui owns the title (`sdk-sessions.json`); the next launch carries it to Claude. No sidecar file, no JSONL mutation, no mid-session interactive `/rename` orchestration. Rendering layer rebuilt on `react-markdown@10` + `remark-gfm@4` + `rehype-highlight@7` + `strip-ansi@7` — the smallest battle-tested stack that covers the chat-style UX. Bubble layout replaces the flat event-card list; tool_use/tool_result correlation deferred to a future iterate (rendered as sibling chronological cards). `@tanstack/react-virtual` engages above 200 events. Auto-scroll uses CSS `overflow-anchor: auto` with `useAutoScroll` as the safety net. TaskBoard cards show state icon + last-activity timestamp + cwd basename + a compact `<TerminalLaunchButton>`; Inbox items group by sessionUuid and use the safe-getter for AskUserQuestion payloads. Doc-sync (sub-iterate 2.4) brings planning specs, agent_docs, compliance docs, and `webui/CLAUDE.md` back in line with the post-pivot reality.
- **Commit range:** 4de68b5 (2.1) → ce783d6 (2.2a) → c6b2d57 (2.2b) → 36d621f (2.3) → this commit (2.4) → 2.5 merge.
- **Rationale:** `--name` is load-bearing for picker parity. Claude already owns the title field; building a parallel store duplicates state. A "Sync title now" button was rejected on architectural grounds — running `claude --resume <uuid> --name "X"` while a session is active risks SQLite lock + JSONL interleave (EBUSY on Windows). The next-launch sync is good enough and stays inside the read-only contract. The rendering library shortlist follows the Plan D'' inversion: fresh, ESM-only, React-19-compatible, no framework lock-in. `react-scroll-to-bottom` was deliberately rejected (stale since 2022, no React 18/19 support, jitter under streaming). Tool-use/tool-result correlation was deferred to keep the iterate inside the ~2-day budget; sibling rendering covers ~80% of the user-visible win.
- **Consequences:**
  - **2.1:** `launcher.buildCopyCommands` accepts `title` and emits `--name <quoted>` after `--session-id` (or after `--resume`). Shell escape spec: PowerShell `''`, POSIX `'\''`, cmd.exe `\"`. New `PATCH /api/external/tasks/:id` endpoint validates non-empty + ≤ 200 chars + no newlines; `proper-lockfile` ELOCKED translates to 409 for client retry. New `<TerminalLaunchButton>` (primary variant) + `<EditableTaskTitle>` on TaskDetail header. 24 launcher-escape unit tests + a real-PowerShell smoke test + concurrent-rename store test + Playwright specs 36/36b.
  - **2.2a:** New `<MarkdownText>` (XSS-safe, GFM tables, language-tagged code, ≥200-line cap with "Show more", ≥2 KB lines soft-broken with ZWS). New `<ToolOutputBlock>` strips ANSI + control chars. Parser hardened: torn-read silent at the trailing line, malformed middle line surfaces as `unknown` stub instead of silent drop. New `askUserQuestionSummary` + `toolResults` safe getters. 16 parser unit + 10 render unit + Playwright spec 37a.
  - **2.2b:** `<BubbleTranscript>` replaces `<TranscriptViewer>`. Right-aligned user, left-aligned assistant + tool. AskUserQuestion bubbles flip amber → green when matched tool_result appears. Virtualization above 200 events. CSS-first auto-scroll with hook fallback. "Load older" pagination in 200-event steps. Performance gate: 1000-event seeded fixture, FCP ~ 2.1 s, IR ~ 2.1 s in dev mode (plan budgets 1.5 / 2.5 s target prod build; assertions allow ~1.5 s slack for dev-mode overhead). 11 unit + Playwright specs 37b/37c.
  - **2.3:** `<TaskCard>` replaces inline rendering on TaskBoard — state icon, HH:mm timestamp, cwd basename, compact `<TerminalLaunchButton variant="compact" />`, three-dots menu (Close + Delete) via Radix Dropdown. `<ConfirmDeleteDialog>` (Radix Dialog) for non-terminal-state deletions. Inbox grouped by sessionUuid; safe-getter rendering for AskUserQuestion. `useTaskTranscript` writes the freshest task into TanStack cache so SessionMetadata + EditableTaskTitle pick up state-machine transitions. Server `/inbox` skips `done` / `launch_failed` tasks. Playwright specs 38, 41, 43, 45, 46, 48.
  - **2.4:** Planning specs gain "RETIRED per ADR-034" banners on chat-adapter / process-governor / inbox-chat sections; new FRs added for external-launch + title integration. Agent docs rewrite: architecture.md describes the polling pipeline end-to-end; conventions.md replaces v0.1 + iterate 7-11 chat learnings with external-launch conventions; session_handoff.md refreshed to the iterate-2-end state. Compliance docs regenerate (traceability matrix, SBOM, test evidence). `webui/CLAUDE.md` adds 7 DO-NOT regression guards.
  - **TSC baseline:** 4 pre-existing server errors (cross-package imports + missing `@types/proper-lockfile`); policy = no regression. New code is typeclean.
- **Rejected:**
  - Sidecar file for webui-only title (duplicates state Claude already owns).
  - JSONL append of synthetic `ai-title` events (behaviorally invasive, no shared locking).
  - Mid-session "Sync title now" button (SQLite + JSONL interleave risk).
  - `react-scroll-to-bottom` (stale, no React 18/19 support).
  - `@assistant-ui/*` re-add (Plan D'' explicitly removed; rendering is bespoke).
  - Tool-use/tool-result correlation in the bubble layout (deferred; sibling rendering ships).
  - Storybook + Docker visual-regression goldens (≥ 0.5 d to set up; replaced by Playwright snapshot/behavioural specs).
- **Rollback:** Each sub-iterate is its own commit. Reverting any one commit restores the prior surface without touching Claude's JSONL or the user's terminal session — the iterate stays inside the read-only contract.


---

### ADR-036: Visibility gate = profile.stack.frontend presence...
- **Date:** 2026-04-20
- **Section:** Plan Interview — iterate-3
- **Context:** Spec FR-03.15 says Preview visibility gate reads 'stack.frontend' + spawn pulls from 'stack.frontend.dev'. Existing hasPreviewCapability reads 'dev_server.command' from profile-loader.ts. Two paths would require dual-writing the profile schema.
- **Decision:** Visibility gate = profile.stack.frontend presence (object-not-null). Spawn target = profile.dev_server.command (existing schema, already used by hasPreviewCapability). No new stack.frontend.dev field.
- **Commit:** n/a
- **Consequences:** Harmonizes spec to code. Boot-time coherence check logs warning if stack.frontend exists but dev_server.command absent; button renders, spawn returns 500 with actionable message.
- **Rejected:** Dual-write profile schema with new stack.frontend.dev field AND keep dev_server.command for backcompat — adds mental model burden, no user-visible benefit.

---

### ADR-037: (a) synthesize server-side. Deterministic...
- **Date:** 2026-04-20
- **Section:** Plan Interview — iterate-3
- **Context:** Spec FR-03.01 says legacy tasks without projectId get 'Unassigned' pseudo-project. Options: (a) synthesize server-side read-only, (b) write real row into projects.json on first read.
- **Decision:** (a) synthesize server-side. Deterministic id='unassigned', appears in getAll() output only when at least one task has projectId='unassigned' or null. Not persisted to projects.json.
- **Commit:** n/a
- **Consequences:** projects.json stays representing user intent. No orphaned 'Unassigned' row after user reassigns everything. Tasks with projectId=null are normalized to 'unassigned' on read via virtual field.
- **Rejected:** (b) first-read migration writes real row — leaks migration state into user data model, hard to un-create later.

---

### ADR-038: (a) incremental migration. CURRENT_SCHEMA_VERSION=2; v1...
- **Date:** 2026-04-20
- **Section:** Plan Interview — iterate-3
- **Context:** sdk-sessions.json v1 schema lacks projectId (spec 3.2 adds it). Options: (a) incremental v1→v2 write-on-touch, (b) batch-rewrite all rows on first boot.
- **Decision:** (a) incremental migration. CURRENT_SCHEMA_VERSION=2; v1 load() assigns projectId='unassigned' in memory; next write of that row persists v2 shape. Header loads both v1 and v2 (forward-compat window).
- **Commit:** n/a
- **Consequences:** Zero risk of mid-migration crash on large stores (300+ rows). Migration completes over days of normal use. Rollback is one-line version constant revert.
- **Rejected:** (b) batch-rewrite on boot — single-point failure, long boot on large stores, hostile rollback.

---

### ADR-039: New TS module lib/classifyPhase.ts (project-agnostic,...
- **Date:** 2026-04-20
- **Section:** Plan Interview — iterate-3
- **Context:** Spec 3.2 mentions re-using 'pre-pivot classifyPhase logic if salvageable'. plugins/shipwright-project has classify_phase.py (Python, runs in IREB decomposition skill). Webui task-creation modal needs client-side debounced auto-classify without round-tripping Python.
- **Decision:** New TS module lib/classifyPhase.ts (project-agnostic, takes phases from actions endpoint, tokenizes title, matches phase.id+label, tiebreak by array index). Pure function, <=80 LOC. Does NOT port or import classify_phase.py.
- **Commit:** n/a
- **Consequences:** Client-side debouncing works out of the box. No binding between webui and plugin-side Python. Independent test surface via Vitest.
- **Rejected:** Port classify_phase.py — binds webui to a plugin whose classifier tuning is unrelated (IREB decomposition vs. webui task labeling).

---

### ADR-040: All 39 findings accepted and integrated. 10...
- **Date:** 2026-04-20
- **Section:** External Review \u2014 iterate-3
- **Context:** Iterate 3 plan.md reviewed via OpenRouter (Gemini + GPT in parallel). 39 findings across security, architecture, completeness, performance, test-coverage, and spec-amendment drift.
- **Decision:** All 39 findings accepted and integrated. 10 HIGH-severity items (command-injection escape matrix, path-traversal pathGuard, spawn shell:false, preview error taxonomy, stale standalone kind, stale complexity UAT, FR-03.02 scoped-strip override, FR-03.14 shortcut pruning, Save-vs-Launch E2E, actions-schema negative tests) folded into \u00a7\u00a7 2.1, 2.2, 4.2 of plan.md + section bodies 01-04. 29 MED/LOW items routed into section-writer briefs. Full disposition ledger in plan.md \u00a7 7.
- **Commit:** n/a
- **Consequences:** Test count targets lifted above spec baseline (Playwright \u226550, server \u2265475, client \u2265560). Preview subprocess hardened (shell:false + tokenize + dedup). NewIssueModal moved from section 02 to 03 to kill section-interdependency footgun. FR-03.30 header drops legacy LaunchRow; Fork deprioritized to iterate 4.
- **Rejected:** Logging all 39 findings as individual ADRs (040-078) \u2014 rejected as noise; single umbrella ADR + plan.md ledger is the auditable record.

---

### ADR-041: Parser interface names stay product-shaped (text/title/name/mode)
- **Date:** 2026-04-20
- **Section:** Build — iterate-3 section 01 (parser hardening + LAF tokens)
- **Context:** On-disk JSONL uses verbose CLI field names (`content`, `customTitle`, `agentName`, `permissionMode`) for the 4 new variants; the section spec describes them with short product-side names (`text`, `title`, `name`, `mode`). The parser mediates between them.
- **Decision:** Parser emits product-shaped field names (`SystemEvent.text`, `CustomTitleEvent.title`, `AgentNameEvent.name`, `PermissionModeEvent.mode`) and extracts from the CLI payload. Accept both CLI and product-short field names on input for forward-compat.
- **Commit:** (this iterate-3.1 commit)
- **Consequences:** Renderer code stays stable if the CLI renames `customTitle` → `title` in a future release. One narrow extraction point in parser tolerates either shape. Duplicated across server + client parsers per `conventions.md:14`.
- **Rejected:** Mirror CLI field names 1:1 in the parsed event (e.g. `event.customTitle`) — would leak CLI naming into every renderer + test.

---

### ADR-042: System visibility is a single global localStorage key, not per-task
- **Date:** 2026-04-20
- **Section:** Build — iterate-3 section 01
- **Context:** System events (subtype `init` / `local_command` / `informational`) are noisy. Section spec + plan § 3 + external review O16 called for default-hidden behind a transcript-toolbar toggle. Toggle scope could be per-task or global.
- **Decision:** Single global localStorage key `webui.transcript.showSystem`. `useSystemVisibility()` reads it lazily on mount, writes on toggle, and cross-tab-syncs via the `storage` event. Every transcript viewer in the app observes the same default.
- **Commit:** (this iterate-3.1 commit)
- **Consequences:** One preference to memorize. No per-task state bloat in `sdk-sessions.json`. Multi-tab reveals flip consistently. Covered E2E by spec 60 (default hidden → click → reload persists).
- **Rejected:** Per-task or per-session preference — no user value, adds a write path into already-contended `sdk-sessions.json`.

---

### ADR-043: Attachment rendering keyed off payload presence, not a mime sniff
- **Date:** 2026-04-20
- **Section:** Build — iterate-3 section 01
- **Context:** FR-03.53 upgrades the generic `attachment` chip to show a filename + thumbnail. Claude's JSONL payload for `attachment` is opaque — sometimes it carries `{filename, thumbnailUrl}`, sometimes it is a bare reference. Renderer must not crash on either shape.
- **Decision:** Branch renders the full card when `filename` is present (using `thumbnailUrl` if available or an extension hint block otherwise); falls back to a generic muted chip when neither field is present. No mime sniffing, no network probe.
- **Commit:** (this iterate-3.1 commit)
- **Consequences:** Resilient to payload drift. Covered by the two unit tests `renders filename + thumbnail when payload provides them` + `falls back to generic chip when payload is opaque`.
- **Rejected:** Require a canonical attachment schema from the CLI (blocks on upstream change); MIME-detect via extension beyond the hint block (unnecessary scope creep for the chip).

---

### ADR-044: Iterate 3 — design overhaul, project↔task wiring, configurable actions, 3-pane TaskDetail
- **Date:** 2026-04-20
- **Section:** Build — iterate-3 section 06 (umbrella close-out; mirrors ADR-035's iterate-2 pattern)
- **Cross-links:** ADR-034 (Plan D'' external-launch pivot, 2026-04-19), ADR-035 (iterate-2 close-out, 2026-04-20), ADR-036..040 (iterate-3 plan-phase decisions), ADR-041..043 (iterate-3 section-01 micro-decisions).
- **Note on numbering:** Section 06 spec called for "ADR-041"; sections 01/02 had already consumed ADR-041/042/043 at build time. ADR-044 is the post-build umbrella close-out covering what actually shipped across sub-iterates 3.1..3.5.
- **Context:** Iterate 3 set out to (a) land the visual mockups that iterate 2 silently skipped, (b) wire projects 1:1 to tasks, (c) restore Folder Tree + Smart Viewer as a 3-pane TaskDetail, (d) add a `+ New ▾` menu that launches Pipeline / Iterate / Task via the same external-launch copy-command contract, (e) move hardcoded webui knowledge of Shipwright phases into a project-local `.webui/actions.json` override with a server-side default, and (f) add a server-spawned Preview dev-server path without violating the Plan D'' read-only Claude contract. The plan was external-reviewed (ADR-040) and broke into five build sub-iterates (3.1 parser+LaF, 3.2 project↔task schema v2, 3.3 actions + preview + new-action menu, 3.4 3-pane TaskDetail + FolderTree + SmartViewer + path-guard, 3.5 Inbox token sweep) plus this doc-sync section 06.
- **Decision (umbrella architecture):**
  1. **Configurable actions over hardcoded strings.** All slash-commands (`/shipwright-run`, `/shipwright-iterate`, `/shipwright-<phase>`) are now template data in `server/src/config/default-actions.json`, overridable per project via `<project.path>/.webui/actions.json`. Components read the resolved set from `GET /api/external/projects/:id/actions`. No component references `shipwright-run` as a literal.
  2. **Placeholder substitution at command-build time.** `server/src/core/actions-substitute.ts` resolves `{project.path}`, `{task.uuid}`, `{task.title}`, `{task.phase}`, `{task.phase_label}`, `{task.description?}`, `{plugin.dirs}` with per-shell escape (PowerShell `''`, POSIX `'\''`, cmd.exe `\"`) — shares the escape matrix with `launcher.ts` via exported `qPs/qCmd/qPosix`.
  3. **Project↔task wiring via schema v2.** `sdk-sessions.json` header bumps to `schemaVersion: 2`; `projectId` is now a first-class task field; legacy v1 rows are treated as `projectId: "unassigned"` in memory and rewritten to v2 on next mutation (write-on-touch migration — ADR-038). `"Unassigned"` is a synthesized pseudo-project surfaced only when at least one task lacks a real projectId (ADR-037).
  4. **Preview spawn is NOT Claude.** `server/src/core/preview-session-manager.ts` spawns `dev_server.command` from the project's profile via `child_process.spawn({shell: false})`, keyed by projectId, deduplicated on healthy sessions, killed on server shutdown. Read-only Claude contract (ADR-034) is untouched — Preview is an independent subprocess class.
  5. **3-pane TaskDetail behind a full-width header.** Left = `<FolderTree>` (lazy expand + gitignore-aware), center = `<BubbleTranscript>`, right = `<SmartViewer>` (5 renderers: Markdown/Code/Text/Image/Mermaid; mermaid lazy-imported to keep initial bundle lean). Panes are `react-resizable-panels`-based with widths + collapsed state persisted in `localStorage` under `webui.taskDetail.*`.
  6. **Path-guard is shared + strict.** Tree + file routes share `server/src/core/path-guard.ts` (realpath + `path.relative` + null-byte reject — **NOT** `startsWith` string check, which is defeated by symlinks + unicode). File route caps at 5 MB, serves via MIME allowlist, sets `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, sandbox iframe, sanitized `Content-Disposition`.
  7. **Profile capability gate is `stack.frontend` presence; spawn target is `dev_server.command`.** Harmonized to existing schema (ADR-036); boot-time coherence check logs a warning when `stack.frontend` is present but `dev_server.command` is missing. Plan § 2.1 precedence matrix documents how these two sources layer with `actions.preview.enabled`.
- **Commit range:** f94dfc7 (3.1) → 88a56f6 (3.2) → bc1ee7c (3.3a) → 4543dca (3.3b) → e584c84 (3.4a) → bdafacb (3.4b) → 4edb173 (3.5) → this commit (3.6).
- **Rationale:** Hardcoded Shipwright-phase strings in webui components created a silent coupling that broke as soon as a user introduced a project-local action override. Moving the phase catalog into `.webui/actions.json` + default-actions.json kills that coupling permanently; the `GET /actions` route is the single contract. The 3-pane restore was mandated by Sven's UAT ("I want the Smart Viewer back"); doing it as a post-pivot rebuild (rather than reviving pre-pivot code) let us keep the read-only invariant and add lazy tree loading + path-guard hardening that the pre-pivot version lacked. Preview as a non-Claude subprocess is the only architecturally clean path: it is a dev-server, not an AI session, so the read-only contract doesn't apply and we can honestly `spawn`. The 3-pane splits used `react-resizable-panels` over a hand-rolled drag because the library is a 6 KB gzip drop-in with persisted widths for free. `shell: false` on Preview spawn is a hard security requirement — shell substitution + user-controlled `dev_server.command` strings would be a trivial command-injection.
- **Consequences:**
  - **New invariants (enforced via new DO-NOT guard #11 in `webui/CLAUDE.md`):** Components MUST NOT hardcode `shipwright-run` / `shipwright-iterate` / phase strings. Read from `/api/external/projects/:id/actions`. Violations re-introduce the configurability debt and will break custom `.webui/actions.json` installations silently.
  - **Placeholder-allowlist convention (`webui/agent_docs/conventions.md`):** New placeholder in `actions-substitute.ts` requires a paired server-side validation test in `actions-schema-validation.test.ts`. Silent placeholder drift otherwise renders the literal `{placeholder}` string in the copy-command and errors the user's terminal paste cryptically.
  - **File structure:** 6 new client components (`FolderTree`, `SmartViewer/*`, `NewIssueModal`, `PreviewButton`, `CreateMenuSplitButton`, `TaskDetailThreePane`) + 6 new server modules (`default-actions.json`, `project-actions-loader`, `actions-substitute`, `preview-session-manager`, `path-guard`, `gitignore-cache`). `LaunchRow` + `CopyCommandCard` deleted from `TaskDetailPage` (replaced by header-level state-dependent CTA).
  - **Test posture (iterate 3 close):** server 299 unit tests (baseline 154 at iterate-2 close, +145); client 351 + 1 doc-sync = 352 (baseline 214 at iterate-2 close, +138); TSC: server = 4 pre-existing errors (no regression), client = 0 errors. Playwright regressed slightly — some iterate-3 flow specs (50a/50b/51/51a/52/53/54/54b/54c/48/55b/56/56b/57/58/58b) are deferred to a follow-up iterate; one new spec `55-three-pane-layout.spec.ts` ships with this iterate. Unit tests cover the contracts.
  - **Spec deviation:** `rehype-highlight/lib/common` subpath was removed in rehype-highlight v7; we use `{languages: common}` from `lowlight` at the call site (equivalent intent; bundle-split verified).
  - **Post-close spec amendment:** FR-03.33 default ignored list now includes `.webui` (external review O34). Dated footnote added — see `webui/planning/iterate-3/spec.md`.
  - **Rollback:** each sub-iterate is its own commit; reverting any one commit stays inside the read-only contract. Reverting 3.2 requires a one-time rewrite of `sdk-sessions.json` back to `schemaVersion: 1` if users mutated v2-format rows in between (write-on-touch migration is forward-compatible).
- **Rejected alternatives:**
  - Webui spawns Claude for Pipeline / Iterate launches (breaks ADR-034 read-only contract; violates CLAUDE.md DO-NOT guard).
  - Hardcoded phase enum in a frontend constants file (re-introduces configurability debt; makes `.webui/actions.json` non-functional).
  - Single-pane viewer ("just show Markdown inline") (loses code syntax highlighting, image preview, mermaid; doesn't match Sven's approved mockup `task-detail-3pane.html`).
  - Pre-pivot Smart File Viewer code revival (pre-pivot used chokidar + chat-subprocess assumptions; cheaper to rebuild clean).
  - `path.startsWith(projectPath)` for the path-guard (defeated by symlinks, unicode, and junction points on Windows — real-path-relative is the only safe check).
  - `shell: true` on Preview spawn with user-configurable `dev_server.command` (command-injection footgun).
  - `stack.frontend.dev.command` as the spawn target (would dual-write the profile schema alongside existing `dev_server.command`; no user-visible benefit — ADR-036).
  - Logging all 5 sub-iterates as individual ADRs (ADR-044..048) — rejected as noise; single umbrella ADR + sub-iterate commit trail is the auditable record, per ADR-035 precedent.


---

### ADR-045: Adopt phase exposed via New Task (one-shot, server-gated)
- **Date:** 2026-04-23
- **Section:** Iterate — feature: adopt-phase
- **Context:** Brownfield onboarding (/shipwright-adopt, iterate 12) had no WebUI entry point. Users had to run the skill manually.
- **Decision:** Add adopt phase to default-actions.json (color #64748B slate-500, distinct from project's #9ca3af); expose server-derived adopted:boolean on Project via ProjectManager.withMode (existsSync check on shipwright_run_config.json); NewIssueModal filters the adopt option from the phase dropdown when selectedProject.adopted === true.
- **Commit:** pending
- **Rationale:** Phase-in-New-Task matches user preference (no separate dropdown entry for a one-time action). Mirrors existing hasPreview derivation pattern. Adds a single field to /api/projects response shape (additive, non-breaking).
- **Consequences:** One-shot nature enforced at UI layer — once adopted, the option disappears automatically on next fetch. Legacy API clients without the adopted field render Adopt (safe default; skill preflight is the final guard). Command template {task.phase} routes it to /shipwright-adopt without any component-side string literals.
- **Rejected:** Separate 'New Adopt' top-level dropdown entry (dauerhafter Eintrag für One-Shot-Feature ist Overkill, Nutzer wollte das explizit nicht). Client-side filesystem check (keine FS-Rechte im Browser).

---

### ADR-046: Launch route routes through substitutePlaceholders with full action context
- **Date:** 2026-04-23
- **Section:** Iterate — bug: launch-command-wiring
- **Context:** Task launch copied a legacy command shape (--session-id + --add-dir + --name + --plugin-dir) while CommandPreviewPanel rendered the correct slash command. Phase/description/autonomy were void'd in the route with comment 'reserved for future wiring'. Phase wasn't persisted on ExternalTask so TaskDetail fell back to title-regex for the badge (often wrong).
- **Decision:** POST /api/external/tasks/:id/launch now accepts actionId + phase + phaseLabel + description + autonomy. When actionId is present and project resolves via getProjectById, the route loads the project's actions catalog and runs substitutePlaceholders against the matching command_template for all three shell forms. Fields are persisted on the task so TaskDetailHeader can render the correct phase badge. When actionId is missing or the project is unresolvable (e.g. 'unassigned'), the legacy buildCopyCommands path is preserved.
- **Commit:** pending
- **Rationale:** substitutePlaceholders + command_template + loadActionsForProject were already built for the preview + dry-run paths in iterate 3.3b. Migrating the launch route to the same pipeline eliminates the client/server divergence rather than maintaining two parallel command builders. Back-compat path handles Resume/Fork and 'unassigned' tasks without special-casing.
- **Consequences:** Copy command now matches the preview. Phase badge on TaskDetail reflects the user's explicit choice, not a title-regex guess. ExternalTask gains 5 optional fields (actionId/phase/phaseLabel/description/autonomy) — additive, forward-compatible with v2 stored rows. Existing Resume/Fork flows still work via the legacy fallback.
- **Rejected:** Alternative 1: extend buildCopyCommands to accept phase/description — would duplicate the per-shell escape discipline that substitutePlaceholders already owns (the security boundary per plan § 2.2). Alternative 2: send the rendered preview command from client to server and persist verbatim — bypasses server-side phase validation and the allowedPhaseIds check.

---

### ADR-047: substitutePlaceholders flattens POSIX line-continuations for cross-shell safety
- **Date:** 2026-04-23
- **Section:** Iterate — bug: shell-line-continuations
- **Context:** ADR-046 (iterate-20260423-launch-command-wiring) migrated /launch to substitutePlaceholders. The command_template carries `\<newline>    ` continuations (POSIX) for readability. All three shell forms inherited them — PowerShell + cmd.exe do NOT honour backslash continuations, so when the user pasted the command only the first line executed. User reported: 'only /shipwright-compliance arrives, Claude does not know the session.'
- **Decision:** substitutePlaceholders post-processes substituted output: replace every `[ \t]*\<CR?>\n[ \t]*` sequence with a single space, then trim trailing whitespace. Output is always a single line regardless of shell form. The template still renders multi-line in the source (readability) and in the CommandPreviewPanel (its own separate renderer).
- **Commit:** pending
- **Rationale:** Option A (flatten) chosen over Option B (per-shell continuation character — backtick for PS, caret for cmd, backslash for POSIX) because a single long line works reliably in every shell and avoids per-platform guess work; modern terminals handle lines of arbitrary length.
- **Consequences:** Copy commands now paste and run correctly in PowerShell / cmd / bash. Four pre-existing test assertions that checked for the continuation-prefix literal were updated to match the new single-line contract. The optional-suffix renderers (task.description?, task.autonomy_flag?) still emit the `\<newline>    ` prefix — it just gets flattened at the end.
- **Rejected:** B: shell-specific continuations — fragile because PowerShell+cmd have additional parsing quirks (line-terminator sensitivity, escaping). C: rewriting the template without continuations — breaks preview readability + would require changing default-actions.json + any user-authored .webui/actions.json.

---

### ADR-048: Command template uses --add-dir (the real Claude CLI flag), not --project-root
- **Date:** 2026-04-23
- **Section:** Iterate — bug: cli-flag-fix
- **Context:** The bundled default-actions.json command_template shipped with --project-root, which is NOT a Claude CLI flag (verified via 'claude --help' — real flag is --add-dir). Before ADR-046, the legacy buildCopyCommands emitted --add-dir correctly, so the template drift was invisible. ADR-046 migrated to substitutePlaceholders and the template started being emitted verbatim — user pasted, Claude CLI errored 'unknown option --project-root', skill never invoked.
- **Decision:** All 3 command_templates in default-actions.json (new-task, new-pipeline, new-iterate) swap --project-root → --add-dir. CommandPreviewPanel.buildCommandText also swaps to keep preview in sync with the real copy.
- **Commit:** pending
- **Rationale:** --add-dir is documented in 'claude --help' as 'Additional directories to allow tool access to', semantically equivalent to the --project-root intent. Matches what the legacy buildCopyCommands emitted, so behavior is restored to pre-ADR-046.
- **Consequences:** Pasted commands now parse cleanly in Claude CLI; the skill receives the full arg list. A regression guard test in project-actions-loader.test.ts asserts the bundled default uses --add-dir and explicitly rejects --project-root, so a future template edit can't reintroduce the drift.
- **Rejected:** Adding --project-root as an alias in Claude CLI itself — not our repo. Keeping --project-root but filtering server-side — would still differ from the visible preview/copy command. Teaching each skill to parse both — unnecessary indirection.

---

### ADR-049: ADR-049: {cd.prefix} placeholder for shell-aware cwd injection
- **Date:** 2026-04-23
- **Section:** Iterate — bug: launch-cwd-prefix
- **Context:** Post-v0.2.0 launch chain (ADR-046/047/048) shipped --add-dir, but --add-dir only grants Claude tool-access, not cwd. When the user pastes the copied command in a terminal parked in HOME, the skill sees pwd=HOME and fails to find shipwright_run_config.json. Three workarounds rejected: env-var (touches every skill), --cwd CLI flag (does not exist on Claude CLI), shell-spawning (architectural rule: webui never spawns Claude).
- **Decision:** New {cd.prefix} placeholder in actions-substitute. Templates opt in by prepending it. Per-shell expansion: PowerShell uses Set-Location <escaped> -ErrorAction Stop; (PS5 lacks &&), cmd.exe uses cd /d <escaped> && (the /d flag changes drive too), POSIX uses cd <escaped> && . Path is escaped via the same qPs/qCmd/qPosix escapers used for {project.path}.
- **Commit:** PENDING
- **Rationale:** Opt-in placeholder cleanly separates substitution mechanics from policy. Always-prepend would have broken {project.path}-only template fragments used in unit tests and would have produced unwanted behavior for any non-claude template. Shell-aware expansion via the existing escaper inherits the proven security boundary.
- **Consequences:** Bundled templates updated (3 in default-actions.json). Regression guard ensures they cannot drift back. User-installed .webui/actions.json files keep the cwd bug until manually edited — acceptable since custom templates imply the user knows what they want. Empty project.path → empty cd.prefix output (graceful degrade). actions-substitute.ts grows from 317 to ~360 LOC; cohesion preferred over split.
- **Rejected:** Always-prepend (breaks fragment substitution and non-claude templates). New env var like SHIPWRIGHT_PROJECT_ROOT (would require updating every skill in the marketplace). Pre-fight startup warning when a user template lacks {cd.prefix} (too noisy; user discovers it on first paste).

---

### ADR-050: ADR-050: Route language-mermaid fences in markdown to MermaidRenderer
- **Date:** 2026-04-23
- **Section:** Iterate — bug: mermaid-in-markdown
- **Context:** FR-03.02 AC 'Mermaid code blocks (```mermaid) render as SVG diagrams' shipped unchecked in iterate 3. SmartViewer only routed .mmd/.mermaid file extensions to MermaidRenderer; fenced blocks inside .md files fell through to FencedCodeBlock, showing raw code instead of diagrams. Shipwright's own compliance docs + spec files use mermaid in markdown heavily.
- **Decision:** MarkdownText.tsx code() override now checks className for `\blanguage-mermaid\b` BEFORE delegating to FencedCodeBlock. Matching fences render via the existing lazy-loaded MermaidRenderer component. Non-mermaid fences unchanged.
- **Commit:** PENDING
- **Rationale:** Using rehype-highlight's language-className as the detection key avoids parsing the fence manually and matches how every other language is already classified. The className-based routing runs before FencedCodeBlock mounts so mermaid diagrams never render as code for a flash.
- **Consequences:** Mermaid diagrams now render in BOTH the SmartViewer (via MarkdownRenderer→MarkdownText) AND in chat bubbles (via BubbleTranscript→MarkdownText). Users who never open a mermaid document still don't pay the ~609 KB mermaid chunk cost (lazy import). FR-03.02 AC now checked.
- **Rejected:** Parsing raw markdown for triple-backtick-mermaid fences (reimplementation of remark's fence detection). Prop-gated renderer (renderMermaid?: boolean) — deferred because lazy import already gates the cost.

---

### ADR-051: ADR-051: Extend cd-prefix to legacy buildCopyCommands (Resume/Fork)
- **Date:** 2026-04-23
- **Section:** Iterate — bug: resume-cwd-prefix
- **Context:** ADR-049 added cd prefix only to the {cd.prefix} placeholder used by the new substitutePlaceholders Launch path. Resume and Fork still routed through legacy buildCopyCommands in launcher.ts (ADR-046 preserved legacy for backward compat with spec 30/36). Result: Resume copy-links pasted in a HOME terminal re-hit the same missing-cwd bug cd prefix was built to fix.
- **Decision:** Extract shell-specific cd prefix formatting into exported buildCdPrefix(shellForm, cwd) helper in launcher.ts. substitutePlaceholders delegates. renderPowershell/renderCmd/renderPosix prepend helper output. All copy-command surfaces (Launch, Resume, Fork, plugin-dir forms) now emit identical cd prefixes per shell.
- **Commit:** PENDING
- **Rationale:** Single source of truth for cd prefix formatting eliminates duplication drift. Exporting the helper allows future surfaces (e.g. terminal spawn commands, launcher v2) to reuse the same escaping discipline without re-implementing it.
- **Consequences:** Resume and Fork commands now cd into project root before invoking claude. Empty cwd still degrades gracefully to no-prefix output. Smoke tests updated to use process.cwd() since Set-Location -ErrorAction Stop rejects non-existent paths. 10 new tests (+5 buildCopyCommands surface, +5 buildCdPrefix helper). Existing actions-substitute.ts cd.prefix case shrinks to a 1-line delegation.
- **Rejected:** Migrating Resume path to substitutePlaceholders with a dedicated resume action template (Path B from scoping discussion) — larger architecture change out of scope for a bug-fix iterate. Leaving Resume on cd-free legacy (status quo) — user explicitly requested parity across all surfaces.

---

### ADR-052: ADR-052: Move MermaidRenderer memo to DOM dataset for StrictMode resilience
- **Date:** 2026-04-23
- **Section:** Iterate — bug: mermaid-flicker-fix
- **Context:** Mermaid diagrams flickered visibly on mount after ADR-050 shipped mermaid-in-markdown. Root cause: React.StrictMode (active in main.tsx) double-invokes effects (mount -> cleanup -> mount), and MermaidRenderer's useEffect cleanup cleared both the container DOM and a useRef content-hash memo. Every second StrictMode mount re-rendered from scratch, producing loading-spinner->blank->loading-spinner->SVG.
- **Decision:** Stamp the content-hash on the container DOM itself via dataset.mermaidHash. The DOM node persists across StrictMode cleanup/setup (same containerRef.current across both mounts), so the second mount short-circuits once the first mount's async commit lands. Cleanup now only flips the disposed flag - no DOM wipe, no ref reset.
- **Commit:** PENDING
- **Rationale:** DOM-level memo is the only memo that survives React.StrictMode's double-invoke pattern in dev. useRef resets are not observable to the dev vs. prod render cycle, so useRef-based memos always miss on the second mount.
- **Consequences:** No flicker on first mount. Identical-text re-renders preserve the exact same <svg> DOM node (asserted by new regression test). Text-change re-renders still work because the effect body checks dataset.mermaidHash against the new hash. Client suite 389/389 (+2 tests). A tempting StrictMode-sim unit test was dropped - vi.mock ordering interacted oddly with React StrictMode + dynamic import and hit the real mermaid code path; the data-attr + rerender tests prove the contract instead.
- **Rejected:** Keeping useRef + skipping cleanup container-clear only (half-fix; ref still resets). useMemo on MarkdownText components prop (larger change, does not address the root cause). Disabling StrictMode in main.tsx (removes dev-mode protection for other bugs).

---

### ADR-053: ADR-053: Hoist ReactMarkdown config to module scope + memo MermaidRenderer
- **Date:** 2026-04-23
- **Section:** Iterate — bug: mermaid-render-loop-fix
- **Context:** User-reported permanent Mermaid flicker after ADR-052 shipped (DOM dataset memo). Flicker was so continuous the user could not even expand the element in devtools. ADR-052 addressed React.StrictMode double-mount but missed the real driver: TaskDetailPage polls transcript at 1 Hz, re-renders cascade to MarkdownText which passed inline (new-identity-every-render) components/remarkPlugins/rehypePlugins to ReactMarkdown. ReactMarkdown treats new config identity as new render path and remounts the subtree including MermaidRenderer — DOM wiped, memo lost, flicker restarts every second.
- **Decision:** Hoist REMARK_PLUGINS / REHYPE_PLUGINS / REACT_MARKDOWN_COMPONENTS to module scope (stable across all mounts). Memoize capLineLengths output via useMemo on text. Wrap MermaidRenderer in React.memo as defensive second layer so even if reconciler remounts, identical-text props skip the body.
- **Commit:** PENDING
- **Rationale:** Module scope beats useMemo([]) because the callbacks close over no component state — there is no value in per-instance memoization. React.memo on MermaidRenderer is cheap defensive insurance against future parent instability.
- **Consequences:** Render loop broken at the ReactMarkdown config layer. MermaidRenderer instance + DOM div persist across the 1 Hz transcript-polling re-renders. Module-scope constants actually produce FEWER allocations than inline creation. 389/389 client tests still green; typecheck baseline unchanged. User live-verify required — memoization identity stability is hard to unit-test with react-markdown.
- **Rejected:** useMemo with empty deps inside MarkdownText (equivalent behaviour, extra complexity). Disabling useTaskTranscript polling (would regress other UX). Debouncing renders (fights React rather than cooperating).

---

### ADR-054: ADR-054: Chat bubble rendering aligned with mockup (6 AC bundle)
- **Date:** 2026-04-23
- **Section:** Iterate — change: chat-rendering-polish
- **Context:** User live-test 2026-04-23 surfaced 6 chat-bubble defects: tool cards eating space, generic tool_use swallowed, slash-commands as raw user XML, mysterious 'attachment' placeholders, empty Claude bubbles with only avatar, font size too large. Mockup bubble-states.html (1203 LOC) is the target. Scope bundled because all 6 touch the same shared stack (session-parser + BubbleTranscript).
- **Decision:** Client-only fix set. Parser: new slash-command kind with strict regex (length-capped, no-newline-in-tags), fileSnapshotBasenames (basename only — no full-path leak), hasVisibleBubbleContent (text-only — tool-only turns get no shell), isThinkingOnly. Three new components: ToolCard (collapsed by default, click header, state keyed by toolUseId), SlashCommandChip (centered grey pill), AttachmentCard (mime-icon + basename + '+N more'). BubbleTranscript: 13px root font with scoped cascade, new branches for slash-command + file-history-snapshot, empty-bubble-shell suppression, attachment noise filter (no filename → null + dev warn).
- **Commit:** PENDING
- **Rationale:** Module-scope constants + React.memo patterns from ADR-053 reused where helpful. Separate helpers (hasVisibleBubbleContent / isThinkingOnly) make each AC independently testable and keep the BubbleTranscript render branches readable. Client-only scope matches the out-of-scope boundary in the iterate spec.
- **Consequences:** All 6 user-reported defects addressed. Client suite 413/413 (+24 from 389 baseline). Empty 'CLAUDE-header-only' bubbles for tool-only turns stop rendering. Attachments with internal Claude Code payloads (deferred_tools_delta, skill_listing) silently suppressed — dev-warn logs schema drift. Mermaid-flicker fix from ADR-053 preserved. External review (GPT+Gemini) caught 15 findings, all applied to spec before code; code-reviewer subagent caught one AC-5 semantic bug which was fixed inline.
- **Rejected:** Splitting parser + UI into two iterates (rejected: single mockup, single spec, cross-cutting change — split would duplicate context load). Per-tool icon map (deferred — generic Wrench icon for this iterate; color-coded icons a future polish). Surfacing still-unknown event types like task_reminder / auto_mode (out of scope; parser fallback stays silent).

---

### ADR-055: Chat-followups: fold tool_result, auto-scroll fix, skill chip, snapshot filter (4 follow-ups to ADR-054)
- **Date:** 2026-04-23
- **Section:** Iterate — change: chat-followups
- **Context:** Live-test of ADR-054 (chat-rendering-polish) surfaced 4 UX gaps in the same component stack: tool_result rendered as separate bubble instead of folded into ToolCard, useAutoScroll yanked viewport to bottom on tool-card expansion mid-transcript, skill-loader manual content rendered as raw user bubble wall, file-history-snapshot events duplicated Edit/Write ToolCards as noise chips. External GPT+Gemini review on the spec raised virtualization-safety concerns (Gemini high on null-return for FU-4) + prev-height lifecycle issues (GPT high on useAutoScroll) + consumer audit for new event kind.
- **Decision:** Bundle all 4 as medium CHANGE. FU-1: toolResultsById map keyed off FULL filtered scope (error-preserving last-write-wins), visibleToolUseIds set keyed off visible slice, strict suppression predicate (only tool_result blocks + all ids in visible window). ToolCard gains optional result prop (input+output sections when expanded). FU-2: useAutoScroll adds prevScrollHeight ref seeded at RO attach via el.scrollHeight, guarded growth check, try/finally unconditional update to handle shrink. FU-3: parser skill-body fingerprint (length >=100, CRLF-normalized, starts with 'Base directory for this skill:', H1-only heading extraction); new SkillChip component analog to SlashCommandChip. FU-4: filter file-history-snapshot in the existing filtered useMemo (pre-virtualizer), NOT return-null in renderBubble.
- **Commit:** HEAD
- **Rationale:** Virtualization safety (Gemini) makes the filter-level drop correct over null-return. Full-filtered map scope (Gemini + GPT) prevents output disappearing when tool_result scrolls past tail but tool_use stays rendered. Pre-growth at-bottom gate (GPT) distinguishes 'user was tailing, keep tailing' from 'user is browsing, let them browse' which is the whole UX bug. H1-only heading guard (review nit) prevents false positives from sub-headings above the title. Non-error-last-wins merge handles retries surfacing stale failure.
- **Consequences:** Transcript density matches bubble-states.html mockup end-to-end: tool input+output co-located, expanding a tool card mid-transcript preserves viewport, skill-loader noise reduced to chip, file-history-snapshot eliminated from render. Client 413->448 tests (+35), server 343 unchanged, client typecheck clean, server 4-error baseline preserved. Data-never-dropped invariant preserved: orphan tool_results + mixed tool_result+text content still render bubble. No DO-NOT violations (no composer, no SSE, no chokidar).
- **Rejected:** Alt A server-side parser folding: doubles work, out of scope. Alt B per-event foldedIntoToolCardId flag on tool_result: leaks renderer concerns into parser. Alt C delete ResizeObserver entirely rely on dep-change: breaks virtualized-list first-measurement scroll. Alt D expandable SkillChip with full body: Gemini noted but deferred — body is debug boilerplate, no user-actionable content, can read JSONL directly if needed.

---

### ADR-056: Chat-livetest-2: SkillCard + phase-on-create + GitHub-md + TodoWriteCard (4 follow-ups to ADR-055 live-test)
- **Date:** 2026-04-23
- **Section:** Iterate — change: chat-livetest-2
- **Context:** Live-test of ADR-055 chat-followups surfaced 4 more items. (1) SkillChip too aggressive — user wants body visible on demand. (2) Task phase badge shows 'design' when task was launched as compliance; NewIssueModal phase dropdown not persisted on task CREATION (only on /launch per ADR-046). (3) Markdown rendering too uniform vs GitHub conventions. (4) TodoWrite tool_use renders as generic ToolCard (JSON blob); user: 'mega wichtig — die Liste zeigen und was fertig ist'. External review (GPT+Gemini) returned 18 findings, 5 critical.
- **Decision:** Medium CHANGE, 4 ACs. AC-A: SkillCard replaces SkillChip (collapsed-by-default, chevron, MarkdownText body on expand). Parser extractSkillBody() returns {skillName, body} via fingerprint rules. AC-B: POST /tasks validates body.phase against project's actions catalog, DERIVES phaseLabel server-side (GPT #2 — label drift guard). Phase without resolvable project → 400 phase_requires_project (post-review blocker #2 fix — no silent drops). New shared lib/phaseStyle.ts used by TaskCard (new phase badge) + TaskDetailHeader (refactored). AC-C: Extended .markdown-body CSS in index.css with GitHub conventions (H1/H2 border-bottom, paragraph spacing, table + code + blockquote tokens, pre/table overflow-x). AC-D: New TodoWriteCard streaming-tolerant (Gemini #1 — {todos:null} mid-stream renders loading, fallback to ToolCard only when stream complete). stableEventKey helper (code-review blocker #1 — event.uuid instead of array-index key for SkillCard expansion state).
- **Commit:** HEAD
- **Rationale:** User's live-test feedback is the highest-fidelity signal. SkillChip was too aggressive; user picked Option C during interview (collapsed + expand). phase-on-create closes the launch-vs-create gap ADR-046 left open. Single .markdown-body class is pragmatic (cheaper than spec's .github-md, same determinism guarantee since MarkdownText already uses it). TodoWriteCard streaming-tolerance protects UX during real multi-chunk tool_use events.
- **Consequences:** Client 448->479 tests (+31), Server 343->350 (+7). Typecheck client clean, server 4-error baseline preserved. User can now see skill manuals + track TodoWrite progress. Task phase visible on kanban board + header. Markdown readability matches GitHub. Code-reviewer blockers (key stability + phase silent-drop) fixed before commit.
- **Rejected:** Alt A: markdown-github.css separate file (spec wording) — rejected for simpler in-place extension of existing .markdown-body. Alt B: keep SkillChip, add expand — rejected, user picked Option C. Alt C: TodoWrite validation in BubbleTranscript pre-dispatch — rejected per GPT #9 (component owns its schema). Alt D: phase silent-drop when no project — initially implemented, rejected post-review (Gemini #2 — never lose user input silently).
