# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Iterate shell-line-continuations (2026-04-23, post-v0.2.0, follow-up to launch-command-wiring)** — copy commands were unusable on Windows because `substitutePlaceholders` emitted POSIX `\<newline>    ` continuations for all three shell forms. PowerShell and cmd.exe do NOT honour backslash line-continuations — they treat the `\` as a literal token, drop everything after the newline. User pasted the copied command and only `claude /shipwright-<phase>` (with a stray `\` arg) reached Claude Code — session-id, project-root, name, description, autonomy were all silently dropped. Matches exactly the symptom "only /shipwright-compliance arrives, Claude does not know the session". Fix: `substitutePlaceholders` now post-processes the substituted output — every `[ \t]*\<CR?LF>[ \t]*` sequence collapses to a single space, trailing whitespace trimmed. Output is a single line regardless of shell form. The template in `default-actions.json` still renders multi-line for readability; the CommandPreviewPanel has its own display renderer that stays multi-line for the user-facing preview. Four pre-existing assertions that checked for the continuation-prefix literal were updated to the new single-line contract. **Test coverage:** 5 new tests in `actions-substitute.test.ts` (flatten in PS/cmd/POSIX, empty-plugin-dirs gap collapses without double-backslash artefact, absent description suffix produces no trailing continuation). **Test totals:** webui/server 320 (+5), webui/client 384 (unchanged). tsc baselines unchanged. Live smoke confirmed posix/powershell/cmd all emit single-line `claude /shipwright-compliance --autonomous --project-root '...' --session-id <uuid> --name "..." 'desc'`. (ADR-047)
- **Iterate launch-command-wiring (2026-04-23, post-v0.2.0)** — `POST /api/external/tasks/:id/launch` copied a legacy command shape (only `--session-id + --add-dir + --name + --plugin-dir`) while the live `CommandPreviewPanel` rendered the correct `claude /shipwright-<phase> --project-root ... <description>` form. Phase, description, and autonomy were explicitly void'd in the route with comment "reserved for future NewIssueModal → launch wiring". Phase was not persisted on `ExternalTask`, so `TaskDetailHeader` fell back to a title-regex guess — often the wrong badge (e.g. title "audit drift" under phase=compliance got no badge; title "Testing foo" under phase=compliance showed Test). **Fix:** launch route now accepts `actionId` + `phase` + `phaseLabel` + `description` + `autonomy` in the body. When actionId is present AND the task's projectId resolves via `getProjectById`, the route loads the project's actions catalog via `loadActionsForProject` and runs `substitutePlaceholders` against the matching `command_template` for all three shell forms (the same pipeline the preview + dry-run paths already used in iterate 3.3b). Substitution errors (unknown phase, newline in description, unknown placeholder) surface as 400 `command_substitution_failed` with the placeholder/phase detail. On success, all five fields are persisted on `ExternalTask`. When actionId is missing or the project is unresolvable (e.g. `projectId === "unassigned"`) or `resume=true`, the legacy `buildCopyCommands` path is preserved — Resume/Fork flows and spec 30/36 stay intact. `ExternalTask` gained `actionId` / `phase` / `phaseLabel` / `description` / `autonomy` as five optional fields (additive, v2 forward-compatible). `TaskDetailHeader.phase` derivation switched to prefer `task.phaseLabel` + `task.phase` (with a color-style map keyed by phase id covering all 10 phases), falling back to the legacy title-regex only when no phase is persisted. **Test coverage:** 7 new server tests in `actions-routes.test.ts` (phase substitution, description substitution, --autonomous on/off, full persistence, legacy back-compat, unknown-phase 400), 3 new client tests in `TaskDetailHeader.test.tsx` asserting the badge prefers the persisted phase over the title regex. **Test totals:** webui/server 315 (+7), webui/client 384 (+3). tsc baselines unchanged (server 4, client 0). Live API smoke confirmed the command now contains `/shipwright-compliance` + `--autonomous` + `--project-root <webui>` + description trailer, and the task persists `phase=compliance, phaseLabel=Compliance, actionId=new-task`. (ADR-046)

## [0.2.0] - 2026-04-23

### Added
- **Iterate adopt-phase (2026-04-23)** — exposes `/shipwright-adopt` via the existing New Task phase dropdown, closing the last gap between the 12 Shipwright SDLC skills and the WebUI. **Change 1 (config):** `adopt` added as a 10th phase in `webui/server/src/config/default-actions.json` with color `#64748B` (slate-500 — visibly distinct from `project`'s `#9ca3af` so the one-shot nature reads at a glance). Command template `claude /shipwright-{task.phase}` routes it to `/shipwright-adopt` without any component-side string literals — honors the ADR-044 rule against hardcoded skill names. **Change 2 (server):** `ProjectManager.withMode()` now derives a server-side `adopted: boolean` by `existsSync('<path>/shipwright_run_config.json')` — no file read, no cache needed (cheap probe). `Project.adopted` added to the shared TS type as optional so legacy API clients stay forward-compatible. **Change 3 (client):** `NewIssueModal` filters `adopt` out of the phase dropdown when the currently-selected project reports `adopted === true`. A missing `adopted` field renders as not-adopted (safe default; the skill's own pre-flight check refuses re-adoption if run_config already exists, so false positives are recoverable). **One-shot enforcement is now UI-level, not just skill-level** — users can't pick Adopt on a project that's already onboarded, because the option disappears automatically on next `/api/projects` fetch. **Test coverage:** 5 new server tests in `project-manager.test.ts` (adopted=true when run_config exists, false when missing, visible on create+getById+getAll, synthesized "Unassigned" row does NOT carry adopted=true), 3 new client tests in `NewIssueModal.test.tsx` asserting on the phase trigger's visible label (Radix DropdownMenu.Content doesn't open under JSDOM+fireEvent, so the menu-open path is covered by the existing Playwright spec `70-h-actions-endpoint.spec.ts` which already scans `[data-testid^="new-issue-phase-option-"]`). Two fixture tests (`project-actions-loader.test.ts`, `actions-routes.test.ts`) updated from `phases.length === 9 → 10`. **Test totals after adopt-phase:** webui/client 381 (+3 from the 378 baseline after the 14.0–14.8 counter reset), webui/server 308 (+4 from baseline). Pre-existing tsc baselines unchanged (server 4, client 0). Spec: new FR-03.31 in `webui/planning/03-features/spec.md`. (ADR-045)

### Fixed
- **Model switch UX stabilization day (2026-04-18)** — three sequential hotfix rounds on top of iterate 14.14, all targeting the mid-task model switch + spawn UX flow. **Morning (modelswitch-spawn-ux, ADR-030):** ModelSelector gains `pendingTargetModel` prop so the TARGET model label + spinner render during the full 1-2s CLI respawn window (was reverting to stale label after `isPending` cleared at ~200ms); new `model-switch-error` banner surfaces server errors inline instead of silent drop; `sendUserMessage` guards empty content so the `/mode` endpoint's `prompt:""` placeholder no longer triggers a "leere Nachricht" ghost reply from Claude CLI 2.1.1 on every respawn; `awaitingInit` widened to cover the task=undefined transient so the "Starting Claude…" spinner shows on fresh tasks. +3 Playwright specs in `17-model-switch-ux.spec.ts`. **Afternoon (modelswitch-uat-round2, ADR-031):** 5 UAT findings fixed — new tasks now use `settings.defaultModel` directly instead of leaking through `useChatSettings.model` (the session-scoped localStorage override was persisting mid-task switches into every subsequent fresh spawn); empty `MessagePrimitive.Root[data-role=assistant]` ghost bubble suppressed (`ThreadMessage` returns null when all content parts are empty); Resume banner gate widened from `orphanReason in [stale_on_startup, user_interrupted]` to `task.status === 'orphaned' && !!claudeSessionId` so switch-timeout crashes also get the button; `useResumeTask.onMutate` clears systemInit so resume-boot spinner fires; new **Retry** button on `model-switch-error` for the transient 409 "Session not yet established" (CLI respawn's first system/init takes 200-500ms), max 3 attempts. **Evening (askuser-multiselect-bugs, ADR-032):** 3 further UAT findings — AskUserCard multi-select no longer shreds labels containing `", "` (split into `textAnswers:Record<number,string>` + `multiAnswers:Record<number,string[]>` maps; array state is round-trip-safe for any label content, joined at submit time so API payload shape stays unchanged); notBlocked banner visually slimmed ~60% (`p-3 text-sm` → `px-2 py-1 text-[11px]`) so it no longer dominates the real question; `PENDING_SWITCH_TIMEOUT_MS` widened `15_000 → 30_000` for Windows Defender cold-start. **Net test totals after the day:** webui/client 487 (+20), webui/server 404 (+2), Playwright 38/39. Specs: `webui/planning/iterate/2026-04-18-*.md`.
- **Iterate 14.14 — Post-14.13 bug sweep (4 bugs, 1 medium iterate)** — fixes four regressions / missing behaviors found during user-testing immediately after 14.13 shipped. **Bug 1 (ModelSelector desynced after mid-task switch):** `chatStore.setSystemInit` was first-write-wins (14.6 duplicate-SSE guard), so the second `system/init` NDJSON event fired by a respawn after 14.12's mid-task model switch was silently ignored. The ModelSelector kept showing the old model while the chat's "Session started · {model}" line rendered the new one. Fix: last-write-wins **when the model id differs** (idempotent on identical writes to preserve 14.6's guard). ChatPanel REST-hydration path switched from `find` (first match) to a `for`-loop that keeps the latest, so page reload after a respawn seeds the store with the newer model. **Bug 2 (second AskUserQuestion submit stalled):** after two AUQs in a single turn (both flagged `notBlocked` by the 14.5 guard because Claude kept generating), submitting the newest via the card left the chat in an "awaiting model" spinner forever with no visible reason. The server-side `inbox-manager.answer` path passed a regression test first try — the joined markdown still reaches `sendStdin` even when `pendingAskUserPerTask` has already cleared via `turn_ended`. Runtime root cause (Claude CLI's behavior with new user input post-`result` when the assistant history has unclosed tool_uses) not yet pinned down; added `console.info` on every answer delivery (taskId, itemId, notBlocked, partCount, processState, processPid) for the next occurrence. **AskUserCard now surfaces POST errors** via an inline red banner + optimistic-state rollback so a silent "Process no longer running" 400 after a respawn race is visible instead of a frozen spinner. **Bug 3 (Inbox → Task 404):** `InboxPage.handleOpenTask` navigated to `/projects/:projectId/tasks/:taskId?focus=chat-bottom` but the router only defines `/tasks/:taskId` (TaskDetailPage resolves `projectId` from the task object). Clicking any inbox item hit react-router's default ErrorBoundary with "Unexpected Application Error! 404 Not Found". Trivial path correction — drop the `/projects/:id` prefix. **Bug 4 (14.13 spawn indicator never rendered):** the 14.13 `messages.length === 0 && awaitingInit` gate suppressed the "Starting Claude…" spinner in the exact case it was built for — when the user creates a task with an initial description, the prompt already lives in `messages[]` by the time TaskDetailPage mounts. Dropped the length gate; the spinner now renders at the bottom of the message list while `awaitingInit` is true (task status pending/running, no system/init yet). The generic leading thinking indicator is suppressed while the spawn indicator owns the slot to avoid double-rendering. **Test totals after 14.14:** webui/client 417 (+9 from 14.13's 408), webui/server 402 (+1 from 14.13's 401). Pre-existing tsc baselines unchanged (server 14, client 0). No new Playwright specs — bugs covered at unit level. No external LLM review (pure bugfixes, no architecture). Plan: `webui/planning/iterate/2026-04-17-post-14.13-bugs.md`. (ADR-029)

### Added
- **Iterate 14.9–14.13 — Model switching + permission-mode stabilization** — four sub-iterates that collectively shipped (a) Opus 4.7 (1M context) support as the new default model, (b) working mid-task model switching via the ModelSelector dropdown, (c) the new `auto` permission mode, and (d) Settings-defaults that actually reach the CLI. **What changed for users:** a mid-task model switch now respawns Claude via `/mode` endpoint with `--resume <sessionId> --model <new>` (14.12 wired the prior stub `handleSwitchModel` TODO to a real `useSwitchModel` hook + server-side `/mode` accepting either `mode`, `model`, or both in one request); concrete CLI ids (`claude-opus-4-7` etc.) are sent verbatim instead of coarse aliases (14.13 — 14.12's `opus` alias was silently resolved to 4.5/4.6 by CLI 2.1.1, creating the "stayed at 4.5" closed loop); server-side model validation relaxed from a hardcoded allowlist to shape-regex `^[a-z0-9][a-z0-9-]*[a-z0-9]$` so future Claude models don't require a webui bump; `--permission-mode auto` correctly maps to CLI `dontAsk` via a single `modeForCli()` chokepoint in `ClaudeAdapter.spawn()` (14.10 hotfix — 14.9 assumed `auto` was a valid CLI value and every Auto-mode task since 14.9 had been failing silently at spawn); `Settings → Default Model` + `Default Permission Mode` dropdowns now hydrate through to fresh spawns (14.12 fixed `useChatSettings` reading stale localStorage over `settings.defaultMode`); ChatPanel renders a `Loader2` spinner + "Starting Claude…" during the 1-2s spawn window (14.13); ModelSelector shows "Switching…" while `useSwitchModel.isPending` with trigger disabled to prevent double-fire; AskUserCard gains Resume button when the task is interrupted while a pending AUQ exists (14.10, matching the TaskCard affordance); chat Stop button now correctly reverts to Send on interrupt (14.9 — SSE broadcast was missing `status` field, `TERMINAL_TASK_STATUSES` extended with `"orphaned"`). Structured `claude.spawn` log event now emits `{ uiMode, cliMode, model, taskId }` on every spawn so the CLI call is auditable. **Net test totals at end of 14.13:** webui/server 401 (+15 across the four sub-iterates), webui/client 408 (+25). Commits: aace0bb (14.9) → 956d8e6 (14.10) → 69bbd42 (14.12) → d55bfb4 (14.13). (ADR-029 + ADR-030)

- **Iterate 14.11 — Task Detail header pause indicator + Resume button (commit f9549d1)** — closes the third visibility gap for interrupted tasks. Pause/Resume affordance now exists in three places: TaskCard in the kanban (14.7.0), AskUserCard in the chat panel (14.10), and now the TaskHeader at the top of the task detail page. When viewing an interrupted task's detail page, the header shows an amber banner with a Pause icon and Resume button below the status row — always visible regardless of whether the user has scrolled into the chat or not. Same `isInterrupted` derivation everywhere: `task.status === "orphaned"` AND `orphanReason` is `stale_on_startup` OR `user_interrupted` AND `claudeSessionId` is set. Reuses existing `useResumeTask` hook from 14.7.0. Single file changed: `webui/client/src/components/detail/TaskHeader.tsx` (+39/-4). +4 tests in TaskHeader.test.tsx. Total client tests 393.

- **Iterate 14.8 — Kanban mapping, Settings expansion, Stop button, ModelSelector redesign (4 sub-iterates)** — addresses Flow A (running tasks showing in Backlog), Flow D (ModelSelector reverting to default), Flow I (FilterBar phase drift), and adds Settings defaults, project color picker, and chat composer Stop button. **14.8.0 (f07ec4b):** DEFAULT_PHASE_TO_STATUS_MAPPING rewritten: project/design/plan/build → in_progress; test/security/compliance/changelog/deploy → in_review. No phase maps to done or backlog — Done column populated only by terminal task.status, Backlog for tasks without a currentPhase. Wired existing Settings → Phase Mapping tab through task-manager: GET /tasks routes now read global phaseToStatusMapping from settings and pass as customMapping. resolveMapping already merged custom over default per-phase. **14.8.1 (585f4b5):** PhaseFilter imports PIPELINE_PHASES from phaseMapping.ts as single source of truth, removing own hardcoded array with obsolete 'iterate' and missing phases. Priority filter deleted entirely (dead UI, task.priority never populated). ModeBadge now inline-flex next to NewIssueModal title instead of diagonal absolute. Standalone projects show "No pipeline config — tasks run as standalone phases." hint below the title. **14.8.2 (e646b67):** Settings → Global gains Default Model (default: Opus 4.6) and Default Permission Mode (default: Edit automatically / acceptEdits) dropdowns. POST /tasks and POST /projects/pipeline read defaults from settings for fresh spawns only. Settings → Project gains Color picker (persists to project.settings.color, overrides deterministic hash in TaskCard's project strip). Settings page reads ?projectId=X&tab=project query params for deep-link; gear icon on ProjectsPage navigates with these params. **14.8.3 (cd3ebab):** New POST /api/projects/:id/tasks/:taskId/interrupt calls adapter.terminate + emits task_orphaned with detail 'user_interrupted'. deriveKanbanStatus treats as resumable (same path as stale_on_startup), interrupted tasks get 14.7.0 Resume/Cancel actions. ORPHAN_REASONS named constants. ChatInput Send toggles to Stop (Square icon, red bg) while isStreaming; click fires interrupt mutation, no Enter shortcut. ModelSelector redesigned: removed userOverride/displayedId/taskKey-reset local state. Now purely props-driven from systemInitModel via chatStore. Dropdown click calls onSwitchModel triggering /mode endpoint. REST-to-chatStore hydration: ChatPanel scans loaded history for first system message with model, fills chatStore gap that caused ModelSelector to show wrong label after page reload. Plan: `~/.claude/plans/lantern-pebble-wake.md`. **Test totals after 14.8:** server 380 (was 356 after 14.7, +24), client 369 (was 339, +30). (ADR-029)

- **Iterate 14.7 — Post-launch fixes + multi-project kanban polish (3 sub-iterates)** — addresses bugs and UX gaps found during manual testing of iterate 14. No external LLM review this round (scope is UX polish + one state machine addition, no architectural risk). **14.7.0 (P0 blockers, commit 9dea2f8):** new `interrupted` kanban status for tasks orphaned by server restart — `deriveKanbanStatus` now branches on `task_orphaned` detail: `stale_on_startup` WITH captured `session_id` → `interrupted` (distinct from `backlog`), otherwise keeps existing `orphaned → backlog`. Added new `session_captured` event (emitted on first `system/init` per task) so `session_id` survives process restart, plus `task_resumed` event. New `POST /api/projects/:id/tasks/:taskId/resume` spawns Claude with `--resume <sessionId>` mirroring ADR-022 mode-switch path. TaskCard renders `⏸️` pause icon + Resume/Cancel actions for interrupted tasks (card stays visually in "In Progress" column). Kanban "All Projects" view actually aggregates tasks across projects now — removed forced auto-select-first-project effect that was silently collapsing the view on mount. Active project id persists to localStorage key `shipwright.activeProjectId` (null is a valid "all projects" state); reload preserves selection and falls back to null when stored id no longer exists. New `lib/localStorage.ts` helper (SSR-safe, JSON.parse error recovery, quota-exceeded tolerance). **14.7.1 (P1 UX polish, commit 035e4df):** ModelSelector now lists all CLI-supported concrete model ids (`opus-4-5`, `opus-4-6`, `sonnet-4-5`, `sonnet-4-6`, `haiku-4-5`) via `formatModelLabel()`; auto-syncs to `chatStore.systemInit.model` on first event per task with a local `userOverride` flag that respects manual selection afterwards; unknown CLI models render as `Other: {id}` to prevent crash. Deleted the redundant 14.6 model-label-next-to-selector element. Browse buttons renamed to "Paste" in New Project wizard AND NewPipelineModal — uses `navigator.clipboard.readText()` with a `looksLikePath()` heuristic (accepts `/`, `\`, drive-letter prefix); honest UX given browser sandboxing prevents `showDirectoryPicker` from returning absolute paths. Inbox items are clickable — navigate to `/projects/:projectId/tasks/:taskId?focus=chat-bottom`; TaskDetailPage reads the query param and ChatPanel's new `focusBottomOnMount` prop auto-scrolls on arrival. Inner Submit button stopPropagations so it doesn't bubble to item click. New `ModeBadge` component in `components/common/` renders diagonal (12° rotation) top-right of NewIssueModal, color-coded: blue Pipeline / amber Iterate / grey Standalone, driven by `project.mode` from 14.0's `getProjectMode()`. `shared/constitution.md` gains "When to use AskUserQuestion vs plain text" subsection — decision questions MUST use the tool, not markdown numbered lists; explains that markdown questions bypass the inbox system and stall silently. **14.7.2 (P2 multi-project kanban, commit 9862ed8):** when All Projects view is active, TaskCard renders a 4px colored left-edge strip; color derived deterministically from `projectId` via simple string hash mapping to 12 evenly-spaced hues on the HSL wheel (saturation 65%, lightness 55%). `PhaseTag` gains a `monochrome` prop — phase badges go grey when `showProjectStrip` is active to avoid visual noise from two color dimensions. New `ProjectFilterChip` component (Radix Popover multi-select) lives in KanbanPage alongside FilterBar; only visible when All Projects is active; default = all selected; shows count badge "Projects (N)" or "All"; subset selection filters the aggregated tasks client-side. `ProjectTabs` dropdown items always show a matching color dot next to project names — creates a legend so users can map card colors to project names at a glance. New `lib/projectColor.ts` helper (5 tests covering deterministic hashing, distinct hashes, empty-string edge case). **Test totals after 14.7:** webui/server 356 (baseline 343, +13 from 14.7.0 only — 14.7.1 and 14.7.2 touched zero server code), webui/client 339 (baseline 286, +53 across the three sub-iterates), iterate 62 (baseline unchanged), project 43 (baseline unchanged), Playwright 33 (e2e baseline preserved with one spec updated for the 14.7.1 label deletion). All sub-iterates merged via fast-forward to main and pushed. Plan: `~/.claude/plans/quiet-harbor-fossil.md`. (ADR-028)

- **Iterate 14 — Phase cleanup, multi-question inbox, pipeline entry, constitution discipline (7 sub-iterates)** — addresses live-test follow-ups from iterate 13 on the TodoApp4 test project. Top-level plan went through external Gemini 3.1 Pro Preview + GPT-5.4 review (`shared/scripts/lib/llm_review.py`) before any code; revisions applied across multiple critical findings (Anthropic API protocol violation in red-flag UI, Ctrl+Shift+N OS-level collision, getProjectMode missing terminal-status handling, JSONL blunt-wipe purge, plugin/UI ownership ambiguity in pipeline bootstrap). Implemented as 7 sub-iterates merged sequentially to main: **14.0** removes `iterate` and `preview` from PHASE_KEYWORDS / VALID_PHASES / PIPELINE_PHASES / PHASE_OPTIONS (security stays); adds `getProjectMode()` in [config-reader.ts](webui/server/src/bridge/config-reader.ts) reading `shipwright_run_config.json.status` (terminal statuses `complete`/`completed`/`failed`/`cancelled`/`error` → `iterate` mode); NewIssueModal branches header + dropdown visibility on `project.mode` (`iterate` → "New Iteration" no dropdown, `pipeline` → current, `standalone` → info banner). **14.1** introduces profile-based preview detection: new [profile-loader.ts](webui/server/src/core/profile-loader.ts) with mtime-cached `loadProfile()`; `project-manager.hasPreviewCapability()` reads `run_config.profile` → `shared/profiles/{name}.json` → checks `dev_server.command`; new `POST /api/projects/:id/preview` spawns `/shipwright-preview` task via existing governor path; new [PreviewButton.tsx](webui/client/src/components/board/PreviewButton.tsx) renders in KanbanPage header when `project.hasPreview === true`; `shipwright-run` SKILL.md instructs writing `profile` field to run_config. **14.2** restructures inbox to `parts[]` schema (one tool_use → one inbox item with N parts, each with own question/options/answer); [askUserPayload.ts](webui/client/src/lib/askUserPayload.ts) extracts ALL questions[] entries (legacy flat schema wrapped to single-part); `inbox-manager` does per-line schema validation on JSONL load and rewrites file after purging legacy entries (no blunt wipe — preserves valid v2 entries); deterministic `## {header}\n{answer}` tool_result serialization with fallback headers, multi-line preserved, multi-select comma-joined; AskUserCard renders accordion of N parts, Submit gated until all answered, single tool_result on submit. **14.3** adds Tool Call Discipline rule to [shared/constitution.md](shared/constitution.md) instructing models to STOP generation in the same turn after AskUserQuestion (12 plugins already reference constitution, pick up automatically); shipwright-project SKILL.md gains intro gate that checks for `shipwright_run_config.json` and asks Full Pipeline vs Standalone Spec when missing, ends turn per constitution rule; new [write_run_config.py](plugins/shipwright-project/scripts/write_run_config.py) detects stack profile from package.json (`next` dep → `supabase-nextjs`) and writes initial run_config with `status=pending`. **14.4** replaces NewIssueButton with Radix DropdownMenu split-button [CreateMenu.tsx](webui/client/src/components/board/CreateMenu.tsx) (New Task / New Pipeline…); new [NewPipelineModal.tsx](webui/client/src/components/board/NewPipelineModal.tsx) with name/path/profile dropdown fetching `GET /api/profiles` (sorted alphabetically, ignores `_*.json`, fail-soft on malformed); new `POST /api/projects/pipeline` with full path safety (raw `..` reject, resolve+isDir, duplicate check, existing-config 409 with `?overwrite=true` escape, profile validation) → writes run_config + registers project + spawns initial project-phase task; KanbanPage shortcut handler replaced with Linear-style letter shortcuts (`c` = New Task, `Shift+C` = New Pipeline) with guards against editable-element focus and any-modal-open state; `Ctrl+Shift+N` binding deleted (Chrome Incognito OS-level collision was firing before preventDefault could reach it). **14.5** adds `notBlocked?: boolean` to InboxItem extending 14.2 schema; new pure state machine [ask-user-guard.ts](webui/server/src/core/ask-user-guard.ts) classifies content blocks (register/flag/resolve/turnEnded transitions) — fully unit-testable without Claude; index.ts wires `pendingAskUserPerTask: Map<taskId, Set<toolUseId>>` and invokes guard on every adapter callback, marks `notBlocked` when assistant continues mid-turn or turn ends with unresolved AskUserQuestion; new SSE event `inbox:flag_not_blocked` broadcast to clients; `useSSE` patches inbox query cache; AskUserCard renders amber warning banner above accordion when `notBlocked === true` ("Claude did not wait for your answer and kept generating. Your answer will still be sent as a tool_result…") — **NO submit-path changes**, always sends valid `tool_result` per Anthropic API protocol (the reviewer-flagged "Answer anyway as plain user message" approach was rejected); InboxPage shows ⚠️ icon on flagged items. **14.6** adds dynamic model label: new [formatModelLabel.ts](webui/client/src/lib/formatModelLabel.ts) parses CLI model ids (`claude-opus-4-5-20251101` → `Opus 4.5`); new minimal [chatStore.ts](webui/client/src/stores/chatStore.ts) zustand slice captures `system/init.model` (first-write-wins per task); ChatToolbar renders dynamic label next to existing ModelSelector; 7 new Playwright specs cover post-iterate-14 user flows (`09-phase-dropdown-cleanup`, `10-preview-button`, `11-iterate-mode`, `12-multi-question-inbox`, `13-create-menu` 7 tests for shortcut + menu + guards, `14-red-flag-banner`, `15-model-label`); pre-existing specs 01 + 06 fixed for the 14.4 "New Task" → "New" CreateMenu rename (real drift caught during E2E audit). **Test totals at end of iterate 14:** webui/server vitest 343 (was 274 before iterate 14, +69 across all sub-iterates), webui/client vitest 286 (was 246, +40), Playwright 33 across 15 spec files (was 8 specs, all green), shipwright-project pytest 43 (was 31, +12 for write_run_config), shipwright-iterate pytest 62 (baseline). All sub-iterates merged via fast-forward to main and pushed; commits ca30350 → 5ec16ff → 483c3b1 → c48fc1a → 13c3f79 → 9366dc6 → b123339. Plan: `~/.claude/plans/polymorphic-frolicking-pebble.md`. (ADR-027)

### Fixed
- **Chat panel no longer flip-flops during a turn (iterate 13)** — the root cause was a protocol mismatch between the SSE broadcast and the REST chat history: `server/src/index.ts` emitted the raw `NdjsonMessage` over SSE before `extractContentBlocks` produced the `ChatMessage` objects that got persisted, so the two paths used different id spaces. `dedupeStreamingMessages` + `displayContentIsPersisted` + ADR-018's text-buffer reset all existed to work around this gap, and `useSSE` invalidated the chat query on every `chat:message` event (~8–12× per turn), causing `messages[]` to churn and the render pipeline to flip cards in and out until the turn settled. **Fix:** reorder `index.ts` so `extractContentBlocks` runs first and then each extracted `ChatMessage` is broadcast individually with the same stable id it gets persisted with. The client now merges each incoming message into the `chat.byTask` TanStack Query cache via `setQueryData` + new `mergeCommitted` helper (dedupe by id, sort by `(timestamp, insertion-index)`, dev warning on same-id content diff) — never invalidates. `useStreamingChat`, `useStreamingSSE`, and `dedupeStreamingMessages` are deleted outright. `ChatPanel` renders a single unified list from one source. Plan went through five rounds of external LLM review (Gemini 3.1 Pro Preview + GPT-5.4 via `shared/scripts/lib/llm_review.py`) before any code was written; the server protocol audit in round 3 is what surfaced the real root cause. Resolves ADR-023 (stop refetching on `chat:message`), supersedes ADR-016 (`displayContentIsPersisted` guard) and ADR-018 (text-buffer reset per assistant event). (ADR-026)
- **Turn lifecycle state survives task switch (iterate 13)** — new tiny Zustand store `client/src/stores/turnStatusStore.ts` holds `{ status, lastEventAt, watchdogStale }` per task, keyed by `` `${projectId}::${taskId}` `` so the store outlives `ChatPanel` unmount. The five-state machine `{idle, awaiting_model, streaming, awaiting_user, stalled}` replaces the ad-hoc `isStreaming` boolean and the `awaitingFromInbox` band-aid from iterate 7 (the context still exists but now also drives the store). Watchdog ticks every 5 s: streaming turns with 15 s of silence flip to `watchdogStale` (visual cursor pulse stops, cache untouched); 120 s flips them to `stalled` (honest UI — no longer lies by pretending the turn cleanly finished). Terminal `task:updated` events schedule a 1500 ms grace timer before flipping to `stalled` so the final `result` message has room to land without a bogus interrupted marker. Zustand is the first such dependency in the repo (~1.1 KB min+gz); TanStack Query still owns all server snapshots. (ADR-026)
- **Inbox "latest pending per task" rule (iterate 11.1 → 11.2)** — one principled rule: for each task, keep only the pending inbox item with the most recent `createdAt`; answered items are preserved. Supersedes iterate 11.1's `governor.getProcess` zombie filter which was too aggressive after a server restart (empty in-memory activeProcesses map hid ALL pending items from previously-running tasks). The new rule naturally handles both iterate-9's same-turn duplicate AskUserQuestion emissions AND iterate-11.1-era interview accumulation ("4 questions from the Tech-Stack interview all pending"). The `addQuestion` normalized-signature dedupe from 11.1 stays. Architectural zombie detection (synthetic `task_orphaned` event at startup) moved to iterate 12.0b. (ADR-025 supersedes ADR-024 in part)
- **API 400 on inbox answers eliminated** — iterate 7 shipped a `tool_result` content-block delivery path via `claude-adapter.sendUserMessage` on the assumption that Claude CLI was blocked on the pending `tool_use AskUserQuestion` and would unblock on the matching `tool_result`. In `-p` + `--input-format stream-json` mode that assumption is WRONG: Claude does NOT block on tool_use, the turn just keeps generating. By the time the user clicks the answer, the conversation has moved past the tool_use, and sending a `tool_result` violates Anthropic's API rule ("tool_result must be in user message immediately after the assistant message containing the matching tool_use"). Observed as `400 invalid_request_error: "unexpected tool_use_id found in tool_result blocks"`. **Iterate 11 reverts to plain-text `sendStdin`** for all inbox answers. The synthetic `tool_result` ChatMessage persistence to chat-store stays — that's local UI state for folded tool-card rendering, not an API call. (ADR-023, partially reverts ADR-019)
- **Inbox no longer shows ghost items for deleted / closed tasks** — `/api/inbox` now joins against `taskManager` and filters out items whose task doesn't exist or is in a terminal status (`done` / `cancelled` / `failed` / `orphaned`). Inbox chat-history replay at startup also skips terminal tasks so it doesn't resurrect items the user already dismissed. (ADR-023)
- **Model selector closes on select + correct context labels** — options are now wrapped in `Popover.Close asChild` (same pattern as `PermissionMode`). Sonnet 4.6 context label updated to `1M` (was incorrectly `200K`); Haiku stays at `200K`. (ADR-023)
- **Zombie-task reconciliation (iterate 12.0b)** — webui now emits `task_orphaned` events when the heartbeat detects a dead Claude CLI process (every 30s) AND at startup, between `governor.cleanupOrphans()` and `heartbeat.start()`. Previously, killing a Claude process (crash, `taskkill`, force-quit) left the task wedged in `running` status in the event store forever, so the kanban card stayed in "In Progress" and the inbox stayed populated with questions the user could no longer answer. Iterate 11.1 had a band-aid (`governor.getProcess(taskId)` filter in `/api/inbox`) that was too aggressive after restarts and got reverted in 11.2; 12.0b is the real fix. New event type `task_orphaned` in [webui/client/src/types/event.ts](webui/client/src/types/event.ts); new `case "task_orphaned"` in [event-store.ts](webui/server/src/core/event-store.ts) `processEvent()` with an idempotency guard (only applies when the task is still `running` — prevents double-apply from heartbeat + startup race and late orphan arrivals from clobbering `work_completed`); new `getTaskState(taskId)` public method so the heartbeat can check status without reaching into the private map; dead unused `detectOrphans()` removed. New `emitTaskOrphanedEvent` in [event-writer.ts](webui/server/src/bridge/event-writer.ts) with the reason stored in `detail` (`process_dead` from heartbeat, `stale_on_startup` from the boot reconciliation). [heartbeat.ts](webui/server/src/core/heartbeat.ts) `HeartbeatScheduler` gains an optional `HeartbeatReconcilerDeps` constructor argument (`eventStore`, `resolveEventsPath`, `emitTaskOrphaned`); `check()` is now async, emits before release, and is fail-open on writer errors so a broken append never leaks governor slots. [index.ts](webui/server/src/index.ts) defers heartbeat construction until after `projectManager` is initialised so the reconciler can close over both; between `governor.cleanupOrphans()` and `heartbeat.start()`, a new loop walks every project's event-store tasks and emits `task_orphaned` with `stale_on_startup` for any `running` task without a live PID — and crucially runs AFTER `cleanupOrphans` (GPT review finding) so legitimately running tasks aren't false-positived. `runtime_checks.py` in the shared verifier package is upgraded from a SKIPPED stub (iterate 12.0) to a real check that replays events.jsonl to derive task state (same rules as the TS event-store, including the `task_orphaned` idempotency), cross-checks `pids.json`, and warns (not errors — transient heartbeat races possible) on any running task without a live PID. `verify_phase.py --phase all` now dispatches `runtime` alongside `iterate`; the 12.0 false-green guard is no longer needed. 7 new webui tests (event-store task_orphaned happy+idempotent+late-arrival, event-writer emit with reasons, heartbeat reconciler happy+idempotent+fail-open+unresolved-path) + 15 new Python runtime_checks tests. webui tests: 283 passing. Python tests: 60 green across runtime + common + iterate verifier. No Python type errors introduced (14 pre-existing TS errors on main remain). Downstream impact: `deriveKanbanStatus` in [task-manager.ts](webui/server/src/core/task-manager.ts) already maps `orphaned → backlog`, so orphaned tasks render correctly without client changes; `/api/inbox`'s `isActive()` filter (iterate 11.2) already excludes `orphaned` status, so inbox items for dead tasks disappear automatically when the reconciler fires — no route-level code changes needed. Campaign plan: `~/.claude/plans/purrfect-snuggling-sunrise.md` section "Iterate 12.0b — Zombie-Task Reconciliation (webui TypeScript only)". (ADR-027 continues)

### Added
- **Iterate 12 — Minimum Phase Completion Canon across all plugins** — campaign that brings every shipping phase to full canon coverage (C1 `record_event`, C2 `update_build_dashboard`, C3 `session_handoff` with `canon_generated` frontmatter, C4 `write_decision_log`, C5 `append_changelog_entry`) with per-phase skip criteria, and ships the supporting verifier + helper infrastructure. **Shared infrastructure (12.0):** new `shared/scripts/tools/verifiers/` package (per-phase check modules + common C1-C5 helpers + F1/F2/F3 ADR integrity + runtime stub); new `verify_phase.py --phase <name>|all` dispatcher (feature-complete across iterate + runtime + project + design + plan + build + test + changelog + deploy); cross-platform `file_lock.py` (`fcntl`/`msvcrt`, 5s hard timeout); atomic `append_changelog_entry.py` (Keep-a-Changelog writer with dedupe + lock) + `append_phase_history.py` (RMW on `shipwright_run_config.json::phase_history[<phase>]`, 50-entry retention); `drift_parsers.py` pure-function library factored out of the `check_drift.py` hook + FR-table parser + new ADR-header parser. Earlier monolithic `verify_iterate_finalization.py` (introduced pre-12.0 as the F11 gate) kept working via thin re-export wrapper. **Stop-hook conditional skip (12.1):** `generate_handoff_on_stop.py` parses the YAML frontmatter and skips regeneration when `canon_generated: true` + `run_id` matches `SHIPWRIGHT_RUN_ID` — pure run-id match, no mtime heuristic. Safe degrade: `--canon-marker` without the env var writes the handoff without frontmatter so the hook falls through. **Plugin coverage:** project (12.1) gets full C1-C5; design (12.2) skips C4 (transformation, not decision); plan (12.2) skips C5 (internal decomposition); build (12.3) uses **hybrid timing** — per-section C1/C2/C4, per-split C3/C5 (avoids spam + partial CHANGELOG entries mid-split); test (12.4) skips C4+C5 (events + `shipwright_test_results.json` own the state); changelog (12.4) skips C5 (it OWNS the `[Unreleased]` → version prepend); deploy (12.4) skips C4+C5 (operational history lives in events + phase_history). **Preventive checks adopted** from the separate shipwright-check plan: build gets B3 (every `build_config.sections[].test_file` exists on disk) + B6 (every recorded section commit SHA reachable via `git cat-file -e`); plan gets C2 (FR orphans in plan.md/sections) + C3 (section manifest drift) + C4 (section-id validity `^\d{2}-[a-z0-9-]+$` unique + gap-free); design gets C1 (every FR linked to at least one screen); changelog gets two Sonder-Checks (`check_git_tag_exists` + `check_changelog_version_matches_tag`). **Final audit pass (12.6):** Canon Coverage matrix + Stop-hook Skip section in `docs/hooks-and-pipeline.md`; Chapter 9 + Appendix B in `docs/guide.md`; live runtime smoke on webui proved the verifier detects real historical drift (14 unreachable commits from rebases, 19 sections missing ADR `**Section:**` refs, 24 sections missing CHANGELOG bullets) — all deferred to a 12.7+ backlog, NOT fixed in the campaign. Plan reviewed in three rounds by Gemini 3.1 Pro Preview + GPT-5.4 via `shared/scripts/lib/llm_review.py`. Campaign status: **12.0 + 12.0b + 12.1 + 12.2 + 12.3 + 12.4 + 12.6 all DONE** (12.5 compliance canon struck — compliance became the separate `shipwright-check` plan). Plan: `~/.claude/plans/purrfect-snuggling-sunrise.md`. (ADR-023 introduced the pre-canon F11 verifier; ADR-027 spans the whole campaign.)

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

[Unreleased]: https://github.com/svenroth-ai/shipwright/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.2.0
[0.1.3]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.3
[0.1.2]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.2
[0.1.1]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.1
[0.1.0]: https://github.com/svenroth-ai/shipwright/releases/tag/v0.1.0
