# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Inbox dedupe + zombie-task filter** — iterate 11 reduced visible inbox items from 8 to 6 but two noise sources remained: (1) Claude emits duplicate `AskUserQuestion` tool calls within the same assistant turn (observed in the iterate-9 live test) and each got its own `toolu_*` id, so both persisted as separate inbox entries even though iterate-9's `collapseAskUserQuestionRun` already hid them in the chat panel; (2) tasks marked `running` in the event store but whose Claude CLI process had since died (no `work_completed` / `work_failed` emitted) still leaked their pending items through iterate-11's task-status filter. `inbox-manager.addQuestion` now dedupes by a normalized question signature (`(taskId, normalized_question)`) for pending items — first-write-wins. `/api/inbox` filter extends with a `governor.getProcess(taskId)` live check, treating running-but-dead tasks as zombies. Architectural cleanup of zombie detection (emitting a synthetic `task_orphaned` event at startup) is deferred to iterate 12. (ADR-024)
- **API 400 on inbox answers eliminated** — iterate 7 shipped a `tool_result` content-block delivery path via `claude-adapter.sendUserMessage` on the assumption that Claude CLI was blocked on the pending `tool_use AskUserQuestion` and would unblock on the matching `tool_result`. In `-p` + `--input-format stream-json` mode that assumption is WRONG: Claude does NOT block on tool_use, the turn just keeps generating. By the time the user clicks the answer, the conversation has moved past the tool_use, and sending a `tool_result` violates Anthropic's API rule ("tool_result must be in user message immediately after the assistant message containing the matching tool_use"). Observed as `400 invalid_request_error: "unexpected tool_use_id found in tool_result blocks"`. **Iterate 11 reverts to plain-text `sendStdin`** for all inbox answers. The synthetic `tool_result` ChatMessage persistence to chat-store stays — that's local UI state for folded tool-card rendering, not an API call. (ADR-023, partially reverts ADR-019)
- **Inbox no longer shows ghost items for deleted / closed tasks** — `/api/inbox` now joins against `taskManager` and filters out items whose task doesn't exist or is in a terminal status (`done` / `cancelled` / `failed` / `orphaned`). Inbox chat-history replay at startup also skips terminal tasks so it doesn't resurrect items the user already dismissed. (ADR-023)
- **Model selector closes on select + correct context labels** — options are now wrapped in `Popover.Close asChild` (same pattern as `PermissionMode`). Sonnet 4.6 context label updated to `1M` (was incorrectly `200K`); Haiku stays at `200K`. (ADR-023)

### Added
- **Deterministic iterate finalization verifier** — new `shared/scripts/tools/verify_iterate_finalization.py` runs as the final F11 step of every iterate run. Checks `iterate_history` contains the run_id, `shipwright_events.jsonl` has the commit, ADR in decision_log.md matches the one recorded in run_config.json, CHANGELOG [Unreleased] has bullets, `session_handoff.md` is fresh. Exit 0 = green (or warnings), exit 1 = required artifact missing. Iterate 11 ran against itself as the first real test. Added after four iterates in a row silently skipped F3a reflection and F11 session_handoff. Iterate 12 (Plan Mode) will expand this into a full cross-plugin sync verifier. (ADR-023)

### Changed
- **Mid-task permission mode switching** — clicking a different mode in the chat toolbar while a task is running now respawns the Claude CLI process with `--resume <realSessionId> --permission-mode <newMode>`, preserving the full conversation history. Guarded against switching while a pending AskUserQuestion exists (409 "Answer pending question first") or before Claude has emitted the first `system/init` event (409 "Session not yet established — try again"). Supersedes the "v0.1 not supported" stance in ADR-011 — a one-off cold start for an explicit user action is an acceptable trade-off (the original rejection was about per-message respawn cost). New endpoint `POST /api/projects/:id/tasks/:taskId/mode`. (ADR-022)
- **Project autonomy now reaches the plugin chain** — autonomy set via the Settings page was previously a silent placebo: the webui stored it in `projects.json` but the Shipwright plugins (shipwright-project, shipwright-build, etc.) read their autonomy setting from `<project>/shipwright_run_config.json`, which the webui never touched. New `projectManager.updateAutonomy` method writes into both stores, merging with existing run_config fields so nothing else is clobbered. Missing run_config files are created fresh; write failures are non-fatal. (ADR-022)

### Fixed
- **Inbox items have real `projectId` + survive restart** — the AskUserQuestion detection in `server/src/index.ts` used to pass `""` as projectId with a stale "resolved by task lookup" TODO. There was no such resolver, so `inbox.jsonl` was never written and the InboxPage grouped every item under "Unknown" when they happened to render at all. Now uses the real projectId from the existing `taskManager.getTaskById` walk, plus a new `inbox-replay` helper that reconstructs orphan `AskUserQuestion` entries from `chat-history/*.jsonl` on startup so open questions from before a restart come back visible. (ADR-021)
- **No more duplicate AskUserQuestion cards + markdown fallback** — Claude Code CLI in `-p` stream-json mode doesn't actually block on `tool_use AskUserQuestion`, so the model keeps generating and typically emits a second AskUserQuestion variant plus a "Lass mich wissen…" numbered-list fallback in the same assistant turn. New `collapseAskUserQuestionRun` pure helper in `client/src/lib/` suppresses those extras for display while the first card is still pending, so the user sees exactly one card to answer. (ADR-021)
- **Model selector in the chat toolbar actually reaches Claude** — was a visual placebo before: `body.model` was sent from the client but `tasks.ts` and `claude-adapter.ts` never read it, so Claude CLI ran with its compiled-in default. Now `claude-adapter.spawn` pushes `--model <alias>` when set, and `tasks.ts` coerces `body.model` to the valid `opus | sonnet | haiku` set. (ADR-021)
- **Effort (thinking depth) selector actually reaches Claude + adds "Max"** — Claude CLI has no `--thinking` / `--effort` flag, but the VS Code extension maps its Max level to `/ultrathink`. New `effort-prompt` helper prepends `/think`, `/think hard`, or `/ultrathink` depending on the selected level. The toolbar pill now cycles through all four levels to match the VS Code Claude extension. (ADR-021)

### Fixed (iterate 8)
- **Deleted, closed, and edited tasks survive server restart** — `PATCH /api/projects/:id/tasks/:taskId/status` and `PATCH .../description` used to write `task_cancelled` / `work_completed` / `task_updated` events only to the in-memory `EventStore`, so the JSONL event log never saw them. On restart the replay rebuilt tasks from disk and resurrected everything the user had just deleted. Both handlers now call new `emitTaskCancelledEvent` / `emitWorkCompletedEvent` / `emitTaskUpdatedEvent` helpers (plus the previously-unused `emitWorkCompletedEvent` is finally wired) before the in-memory update, symmetric with the `task_created` path. (ADR-020)

### Fixed (iterate 7)
- **AskUserQuestion answers actually unblock Claude CLI** — `inbox-manager.answer` used to send the user's reply as plain text on stdin, leaving Claude blocked on the AskUserQuestion call (the markdown fallback question list). It now sends a structured `{type:"tool_result", tool_use_id, content}` content block via `claude-adapter.sendUserMessage` whenever the inbox item id is a real Anthropic `toolu_`-prefixed id (which it is since iterate-6). The synthetic `tool_result` is also persisted to chat-store so the folded tool card transitions to "Done" and the "Answered: X" state survives a refresh. Legacy random-UUID inbox entries still fall through to the plain-text path. (ADR-019)
- **"Thinking…" indicator fires immediately on AskUserCard submit** — previously waited 2-3 s for Claude's first NDJSON event because `ChatPanel.isAwaitingResponse` only watched `sendChat.isPending`, not the inbox-answer path. New `ChatAwaitingContext` lets `AskUserCard.handleSubmit` flip a local `awaitingFromInbox` flag in `ChatPanel` synchronously; cleared once the stream actually starts. (ADR-019)

### Changed
- **shipwright-project SKILL: explicit one-question-per-AskUserQuestion rule** — added a single line to both `SKILL.md` and `references/interview-protocol.md` clarifying that the host blocks on each `AskUserQuestion` call and waits for a `tool_result` reply, so questions must NOT be batched into a markdown list. (ADR-019)
- **shipwright-iterate F3 ADR length budget (forward-only)** — `SKILL.md` F3 section spells out a 1-3-sentence, ~500-character per-field budget for new ADRs. `shared/scripts/tools/write_decision_log.py` emits a non-blocking stderr warning when any field exceeds 500 chars; the entry is still written. Existing ADRs are NOT retroactively shortened. (ADR-019)

### Fixed (earlier in this release)
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
- **AskUserCard visual redesign** — switched from solid `bg-amber-50` to a white card with an **orange** `300` border and a thick **orange** `500` left accent bar (`border-l-4 border-l-orange-500`), orange header chip, plus a soft card shadow. (Initially landed as amber in iterate-4 but read as yellow against the beige chat background — switched to orange per user preference.)
- **AskUserCard schema extractor corrected** — `extractAskUserPayload` now reads options directly from `questions[0].options` as a sibling of `multiSelect` instead of (incorrectly) treating `multiSelect` as an object holding `options`. Verified against a live `chat-history/*.jsonl` dump: the real Claude Code `AskUserQuestion` tool input has `{ questions: [{ question, header, options: [{label, description}], multiSelect: boolean }] }`. Option chips now render inline in the card. Also added an `allowMultiple` flag derived from the boolean for future multi-select rendering. (ADR-017)
- **"Thinking…" text next to the bouncing dots** — `AssistantMessage`'s empty-streaming state was three tiny bouncing dots with no label, which the user described as "just a blinking cursor in the white area". Now shows the dots plus an italic "Thinking…" label in muted gray. Clearer signal that Claude is working, not stuck.

### Fixed
- **Dev-server restart** — iterates 1-4 were all shipped but the webui dev server (`tsx watch`) had never actually picked up the changes due to a 12+ hour stale process from 2026-04-12 22:36. Killed the old process (PID 60252) and restarted. All prior iterate fixes (phase resolution, content_block dedup, toolUseId propagation, `/start` route phase resolution, chat-store defensive dedupe) finally take effect.
- **`displayContent` no longer concatenates across assistant events in a single stream** — the streaming text buffer in `useStreamingChat` used to append every assistant event's text to the same buffer without resetting between turns, so a three-turn Claude response rendered a big white card at the bottom with "text1 + text2 + text3" concatenated together. Now each assistant event resets `displayContent` before writing its own text, so the buffer only ever mirrors the current in-flight turn. iterate-4's persisted-match guard then suppresses even that once `messages[]` catches up. (ADR-018)
- **AskUserCard answers are now actually delivered to the server** — `inbox-manager.addQuestion` used to generate a fresh `randomUUID()` for the inbox item id while the client's `AskUserCard` posted to `/inbox/:id/answer` using `message.id` (the ChatMessage UUID, a different value). The server couldn't find the item, answer was lost. Now `addQuestion` accepts an optional `toolUseId` that becomes the item id, and the inbox-detection path in `index.ts` iterates over the extracted tool_use ChatMessages so it covers **both** standalone `tool_use` NDJSON events and the assistant-wrapped content-block variant (the latter was missed entirely before — that's why Claude never saw answers regardless of the id). `AskUserCard` uses `message.toolUseId` as the inbox id. (ADR-018)
- **AskUserCard state survives page refresh** — new `useInboxItem(id)` hook reads the persisted inbox state, and `AskUserCard` now hydrates its "Answered: X" display from the server instead of local-only React state. Refreshing keeps the answered state.

### Added
- **`npm run dev:fresh` for the webui dev server** — new cross-platform Node script `webui/scripts/dev-restart.js` that kills every `tsx watch` / `vite` / node process owning ports 3847/5173/5177 and respawns `npm run dev` cleanly. Recovers from stale `tsx watch` processes that don't pick up file changes (happens occasionally on Windows after `git merge`). Documented in `webui/CLAUDE.md` under "Dev-server troubleshooting". Dev-only — production users never see the stale-server problem because the code doesn't change under a running production server.

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
