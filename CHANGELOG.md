# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Phase dropdown selection is now honored** — `POST /api/projects/:id/tasks/:taskId/start` no longer hardcodes `phase=build`; it reads `task.requestedPhase` (persisted via the `task_created` event) and falls back to `classifyPhase(title+description)` → `"project"`. (ADR-013)
- **NewIssueModal auto-suggest race** — a late-arriving classify response could overwrite a manual phase pick. Fixed via `phaseIsAutoRef` + an effect-level `aborted` guard; manual selections always win.
- **Tool call cards stop saying "Running" forever** — `tool_use` and `tool_result` are now folded together by `toolUseId` at render time via a new `foldToolResults` helper. Tool cards transition from "Running" → "Done" / "Error" in place as soon as the matching result arrives, both for live streaming and persisted chat history. (ADR-014)
- **AskUserQuestion prompts now render properly** — the card used to show an empty yellow box with no question text and no suggestion chips because it read `toolInput.question` / `toolInput.options` as flat keys, but Claude Code's built-in `AskUserQuestion` tool emits a nested shape `{ questions: [{ header, question, multiSelect: { options: [{ label, description }] } }] }`. New `extractAskUserPayload` helper flattens both the nested and legacy schemas so `AskUserCard` and the server inbox path see the same `{ question, header, options }` payload. (ADR-015)
- **AskUserQuestion prompts no longer render twice** — the chat panel used to show two identical yellow cards because every `chat:message` SSE event invalidates the chat query (causing a refetch into `messages`) while the same event also lands in `streaming.streamingMessages`, and both lists were rendered sequentially. New `dedupeStreamingMessages` helper drops streaming entries whose stable signature (`tool:<toolUseId>` or `<type>:<content-prefix>`) is already present in the persisted list. This also fixes double-rendering for tool calls, assistant text, and thinking blocks during the streaming → persisted handoff window.
- **Chat duplication root cause — kill `content_block_*` persistence** — the server's NDJSON parser was extracting ChatMessages from both `content_block_start`/`content_block_delta` events (with *partial* tool_input/text while Claude was still generating the block token-by-token) AND from the final `assistant` event (with the *completed* content block array). Both paths persisted, producing two almost-identical rows in `chat-history/*.jsonl` — e.g. a tool_use with option label `"todoappdemo/planning"` followed ~4.6 s later by the same tool_use with `"todoappdemo/planning (Recommended)"`. The client's `useStreamingChat` hook never consumed `content_block_*` anyway, so deleting the server handler is a pure fix. (ADR-016)
- **`displayContent` no longer renders next to its persisted copy** — during streaming, `useSSE` invalidates the chat query on every `chat:message`, so `messages` quickly catches up with the text in `streaming.displayContent`. ChatPanel now checks if any persisted assistant message already contains that exact text and skips the streaming `<AssistantMessage isStreaming />` render when it does. No more duplicate text bubbles in the invalidation window.
- **Defensive chat-store dedupe** — belt-and-suspenders: `ChatStore.append` keeps an 8-entry, 10-second rolling window of recent message signatures (type + toolName + content + JSON.stringify(toolInput) + isError) per task and drops exact structural duplicates. Shields the persisted log from any future parser regression or Claude CLI stream quirk.
- **Kanban phase badge on create-a-new-app tasks** — `classify_phase.py` used to classify `"Build a ToDo-App"` as `build` because both `project` (via `app`) and `build` (via `build`) scored 1 and the tiebreaker favored build. The word "build" in a user task title almost always means "create", not the Shipwright build phase, so it's been removed from the build keyword set. `PHASE_PRIORITY` also reorders so `project` wins any residual ties over `build`. The kanban phase badge now shows `project` for `"Build a ToDo-App"` and similar phrasings.

### Changed
- **AskUserCard visual redesign** — switched from solid `bg-amber-50` to a white card (`bg-white`) with an `amber-200` border and a thick `amber-400` left accent bar (`border-l-4 border-l-amber-400`) plus a soft card shadow. Aligns chrome with the other white Claude cards in the chat panel while keeping the "needs attention" amber signal concentrated in the left accent.

### Changed
- **`task_created` event gains optional `phase` field** — server persists the originally requested phase so deferred `/start` calls can restore it without re-classifying. `EventStore` reads `event.phase` into the new `task.requestedPhase` field.
- **`ChatMessage.toolUseId`** — new optional field propagating Anthropic's `tool_use_id` so the frontend can match `tool_result` back to its originating `tool_use`. Extracted by both the NDJSON parser and `useStreamingChat`.

## [0.1.3] - 2026-04-13

WebUI Command Center — phase detection for task creation. The New Task
modal now auto-suggests a pipeline phase from the task description, and
the server emits `phase_started` events with the detected phase instead
of a hardcoded `"build"`.

### Added
- **Phase detection for task creation** — new rule-based classifier
  `classify_phase.py` (keywords + priority tie-break) exposed via
  `classifyPhase()` in `intent-classifier.ts`. Deterministic, offline,
  no external dependencies.
- **Phase field on `POST /api/projects/:id/classify`** — response now
  includes `phase` and `phase_confidence` alongside `intent` and
  `complexity`.
- **Phase dropdown in `NewIssueModal`** — 8 options (project, design,
  plan, build, test, deploy, changelog, compliance) with a debounced
  auto-suggest (400ms) that calls `/classify`, shows a Sparkle "auto"
  indicator when suggested, and turns manual the moment the user picks
  a value.

### Changed
- **`POST /api/projects/:id/tasks` accepts `body.phase`** — when
  omitted, `classifyPhase()` is invoked against the title+description
  and the result is used in the `phase_started` event (fallback:
  `project`). Previously the event was hardcoded to `"build"`.

## [0.1.2] - 2026-04-12

WebUI Command Center — v0.1 triage second round. Three thematic iterate
runs (retroactively documented): persistent Claude process architecture,
chat rendering redesign via companion port, and VS Code permission modes.
Eliminates the 5–10s cold-start penalty on every chat follow-up (6× speedup
measured), fixes broken markdown tables, and aligns the permission UX with
the VS Code Claude extension.

### Fixed
- **Cold-start eliminated on chat follow-ups** — switched from spawn-per-message
  to a single persistent Claude CLI process per task using `--input-format
  stream-json`. Measured: initial task 15.35s (cold, one-off) → follow-up
  chat 2.57s (warm). ~6× speedup. (commits 97f10bd, 17be46a, 60167fa, ec9b0e1)
- **Markdown tables render correctly** — previously collapsed into garbage
  like `"SpieleTordiff.Punkte"` due to `@tailwindcss/typography` cell
  handling. Replaced with explicit `react-markdown` component overrides
  ported from companion (MIT). (commit 15928b8)
- **Horizontal scroll bar in chat** — long Bash commands and JSON tool
  inputs pushed the chat container wider than viewport. Fixed via
  `min-w-0 overflow-x-hidden` on flex containers and `max-w-full
  break-words` on `<pre>` elements. (commit 840e888)
- **SSE named events never received by client** — pre-existing bug where
  `EventSource.onmessage` was used instead of `addEventListener(eventType,
  handler)`. Server emits `event: chat:message\n...` which onmessage does
  NOT catch. Fixed all named SSE events at once. (commit 97f10bd)
- **Streaming indicator appeared too late** — only fired after Claude's
  first NDJSON event (~5–10s delay). Now fires immediately on user-send
  via `isAwaitingResponse` helper combining `streaming.isStreaming ||
  lastMessageIsUser || sendChat.isPending`. (commit f2c0032)
- **Task Kanban status stuck in backlog** — `/tasks` and `/tasks/:id/start`
  spawned Claude but never emitted `phase_started` events. Kanban board
  now transitions to "In Progress" immediately. (commit 17be46a)
- **Permission popover stayed open after select** — wrapped each mode
  button in `Popover.Close asChild` so clicking commits AND closes.
  (commit 265ec07)
- **`result` + `assistant` duplicate rendering** — Claude CLI emits both
  with identical content at end of each turn. Deduped in `ChatPanel` via
  `dedupeMessages` helper. (commit f2c0032)
- **`system/init` NDJSON blob rendered as giant text wall** — now collapsed
  to `"Session started · claude-opus-4-6"` one-liner. (commit 840e888)

### Added
- **Image upload in chat** via paperclip button (file picker) and clipboard
  paste. Attached images shown as 48×48 thumbnails above the textarea with
  remove button. Sent to Claude CLI as multimodal content blocks (`{type:
  "image", source: {type: "base64", media_type, data}}`). Persisted on
  user messages, shown as thumbnails on reload. (commit 15928b8)
- **VS Code-style permission modes** — 4 modes with icons and descriptions
  matching the VS Code Claude extension: Ask before edits (Hand icon) /
  Edit automatically (Code2) / Plan mode (ClipboardList) / Bypass
  permissions (Link2, default). Wired to `--permission-mode <mode>` or
  `--dangerously-skip-permissions` on spawn. Legacy localStorage values
  auto-migrated. (commit 27fce3a)
- **MarkdownContent component** ported from The-Vibe-Company/companion
  (MIT) — full artifact support: headings h1–h4, paragraphs, lists,
  tables with borders, blockquotes, hr, links, inline code, fenced code
  blocks with language header. (commit 15928b8)
- **Task lifecycle events** — `phase_started` emitted on task creation
  (Kanban transitions to "In Progress"), `work_completed` / `work_failed`
  emitted on Claude CLI exit via adapter `onExit` callback. (commit 17be46a)
- **`useStreamingSSE` hook** — consumes named SSE events and feeds NDJSON
  messages into the streaming chat UI state in real time. (commit 97f10bd)
- **`ThinkingBlock` component** — collapsible block for Claude's thinking
  output with character count. (commit 97f10bd)
- **`ToolIconTile` component** — colored icon tiles per tool type (blue
  for Read/Grep/Glob, amber for Edit/Write, green for Bash, purple for
  Agent/Task). (commit 840e888)
- **`PermissionMode.tsx` rewrite** with Radix Popover + Lucide icons +
  descriptions + active checkmark. (commit 27fce3a)
- **`readFileAsBase64` helper** (ported from companion MIT). (commit 15928b8)

### Changed
- **Claude CLI process model**: one persistent process per task instead
  of spawn-per-message. stdin=pipe, NDJSON user messages written via new
  `sendUserMessage(proc, content)` API. Process stays alive throughout
  the conversation. (commit ec9b0e1)
- **Default permission mode** is now `bypassPermissions` (was `default`).
  Matches VS Code extension default. (commit 27fce3a)
- **Claude messages** render as white rounded cards with subtle shadow
  on the beige chat background. **User messages** render as left-aligned
  grey bubbles (`#d4cbbc`), no longer right-aligned primary-brown bubbles.
  (commits 840e888, 27fce3a, 265ec07)
- **All NDJSON message types persisted** in chat-store (assistant, tool_use,
  tool_result, thinking, system, result) — previously only assistant text
  was saved, tool calls were lost on reload. Legacy JSON-blob rows
  auto-migrated on read. (commit 97f10bd)
- **`useCreateTask`** forwards `mode` + `model` in the POST `/tasks` body.
- **`useChat`** forwards `images` in the POST `/chat` body.
- **SSE `chat:message` payload** now includes `projectId` so the client
  can invalidate the correct query cache key. (commit 97f10bd)

### Removed
- **`SessionRegistry`** (server/src/core/session-registry.ts + tests). It
  was introduced in 60167fa to map our task UUID to Claude's real session
  id for `--resume <sessionId>` respawn support, then deleted in ec9b0e1
  because the persistent process IS the session — no lookup needed.
  ~350 LOC removed. (commit ec9b0e1)
- **`--dangerously-skip-permissions` as unconditional flag** — now
  conditional on mode selection. (commit 27fce3a)

### Attribution
- `MarkdownContent.tsx` and `image.ts` ported from
  [The-Vibe-Company/companion](https://github.com/The-Vibe-Company/companion)
  (MIT license) — `web/src/components/MessageBubble.tsx` and
  `web/src/utils/image.ts` respectively. Same React 19 + remark-gfm
  stack. Company's `cc-*` Tailwind tokens swapped for our `--color-*`
  CSS custom properties; structurally identical.

### Iterate Runs (retroactive backfill)
This v0.1.2 release was made via a retroactive backfill after 12 commits
had already landed on `main` without going through `/shipwright-iterate`.
Three thematic iterate runs were documented retroactively:
- `iterate-2026-04-12-persistent-process` (ADR-009, complexity medium)
- `iterate-2026-04-12-chat-rendering` (ADR-010, complexity medium)
- `iterate-2026-04-12-permission-modes` (ADR-011, complexity small)
See `webui/planning/iterate/` for specs and `webui/agent_docs/decision_log.md`
for the ADRs.

### Tests
- Server: 189 / 189 passing (added tests for persistent adapter,
  multimodal sendUserMessage, permission mode coercion)
- Client: 164 / 164 passing (added tests for markdown tables, image
  upload flow, permission mode component)
- E2E: 17 / 17 passing

## [0.1.1] - 2026-04-12

Focused triage and fix round for the WebUI Command Center. The Kanban board
now reflects real task lifecycle, chat follow-ups actually reach Claude, and
the chat visuals match design mockup 11.

### Fixed

- **Task lifecycle events** — clicking Start (or creating with `startImmediately`)
  now transitions the Kanban card to In Progress and, on Claude CLI exit, to Done
  or Failed. Previously the governor spawned the process but never emitted
  `phase_started` / `work_completed` / `work_failed` events, so tasks stayed in
  Backlog forever.
- **Interactive chat** — chat follow-ups previously returned "Task is not
  running" because Claude CLI was launched in print mode (`-p`) and exited
  after the first response, leaving `sendStdin` writing into `stdio=ignore`.
  Each chat POST now spawns a fresh Claude process with `--resume <sessionId>`
  and the user message as the new prompt.
- **Session ID capture** — Claude CLI ignores the UUID we pass to `--session-id`
  and generates its own internally. New `SessionRegistry` captures the real
  `session_id` from the first `system/init` NDJSON event and persists it to
  `~/.shipwright-webui/sessions.json` so follow-ups can resolve the correct
  session for `--resume`.
- **Chat rendering** — components now match mockup `11-task-detail.html`:
  Claude messages have an avatar + sender label + flat content (no bubble),
  tool cards are white with colored icon tiles (blue Read/Grep/Glob,
  amber Edit/Write, green Bash, purple Agent/Task), monospace titles formatted
  as `Run <cmd>` / `Read <path>`, and a Done/Error status badge.
- **Horizontal scroll** — `min-w-0` + `overflow-x-hidden` on the chat container
  and `max-w-full break-words` on tool card `pre` elements eliminate the
  horizontal scrollbar when long Bash commands or JSON inputs appear.
- **System init noise** — the giant `system/init` NDJSON blob is now collapsed
  to a subtle "Session started · claude-opus-4-6" line.
- **Result deduplication** — Claude CLI emits both an `assistant` and a
  `result` event with identical content; the UI now dedupes them.

### Added

- `SessionRegistry` core module with load/set/get + disk persistence (8 unit tests).
- `ToolIconTile` component with per-tool color mapping matching the mockup.
- `dedupeMessages` helper in ChatPanel.
- `ClaudeSpawnOptions.resume` now supports `"explicit"` mode for
  `--resume <sessionId>`.

### Tests

- Server: 197/197 (added SessionRegistry + chat route tests).
- Client: 164/164 (updated chat component tests for new layout).

## [0.1.0] - 2026-04-12

Initial release of the Shipwright SDLC Framework — an AI-powered development
pipeline built on Claude Code, from project description to deployed application.

### Added

#### Pipeline Plugins
- **shipwright-run** — Orchestrator entry point with phase routing, auto-triggering, and standalone mode
- **shipwright-project** — Requirements decomposition with IREB-aligned specs, chat and inline input modes
- **shipwright-design** — UI mockup generation from IREB specs as standalone HTML
- **shipwright-plan** — Planning with E2E test plans, sprint tracking, and section-based breakdown
- **shipwright-build** — TDD implementation with code review, Conventional Commits, and feature branches
- **shipwright-test** — Unit, E2E (Playwright), and security testing with self-healing for missing artifacts
- **shipwright-changelog** — Git history analysis, Keep-a-Changelog generation, version tagging, and PRs
- **shipwright-deploy** — Jelastic (Infomaniak) deployment with smoke tests and rollback
- **shipwright-compliance** — IREB traceability, RTM, SBOM, and audit-ready reports
- **shipwright-iterate** — Lightweight SDLC for ongoing changes in completed projects
- **shipwright-preview** — Local dev server preview for built applications

#### Shared Infrastructure
- Monorepo scaffolding with stack profiles (Next.js + Supabase, custom)
- Project templates (CLAUDE.md, agent_docs, CI configs)
- Shared Python utilities (config, state, handoff, hooks)
- Constitution with ALWAYS / ASK FIRST / NEVER boundaries
- Plugin marketplace.json for Claude Code discovery
- Setup guide with installation scripts and OpenRouter support

#### Command Center (WebUI)
- **Kanban Board** — Multi-project board with columns, cards, filters, list/card view toggle, and sorting
- **Task Management** — Create, edit, close, delete tasks; New Issue modal with background auto-classification
- **Claude CLI Bridge** — Subprocess spawning (node.exe + cli.js), NDJSON stream parsing, SSE broadcast
- **Chat Rendering** — Typed message persistence (assistant, tool_use, tool_result, thinking, system, result)
- **ThinkingBlock** — Collapsible purple block with character count for Claude's thinking
- **ToolCallCard** — Tool-specific icons (Bash, Read, Write, Edit, Grep, Glob, Agent), error states with red tinting
- **Real-time Streaming** — useStreamingSSE hook for live tool calls and text as they arrive
- **Task Detail** — Resizable two-panel layout with chat engine and Smart File Viewer
- **Smart Viewer** — Tab management with renderers for code, HTML, JSON, Markdown, and diff overlays
- **File Explorer** — Directory tree with git status indicators
- **Settings** — Global + per-project settings, phase-to-status mapping, autonomy modes
- **Model Selector** — Claude Opus 4.6 / Sonnet 4.6 / Haiku 4.5 with context window display
- **Permission Modes** — Default / Plan / Auto-accept with descriptions
- **Inbox** — AskUserQuestion aggregation across projects with option buttons and free-form answers
- **Project Wizard** — 4-step modal with stack profile selection
- **Windows Auto-start** — Install script for system startup

#### Testing
- Server: 185 unit tests
- Client: 161 unit tests
- 5 E2E tests (Playwright)
- Integration tests across pipeline plugins

### Fixed
- SSE named events not received by client (onmessage → addEventListener)
- Legacy JSON-blob chat messages auto-migrated on load
- Bridge cross-platform stability (Windows cmd.exe shim bypass, PID recycling protection)
- Kanban board scroll overflow handling
- Task creation ENOENT and project directory initialization

[0.1.2]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.2
[0.1.1]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.1
[0.1.0]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.0
