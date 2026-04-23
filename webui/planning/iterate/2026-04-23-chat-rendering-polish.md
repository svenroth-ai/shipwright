# Iterate Spec: chat-rendering-polish

- **Run ID:** iterate-20260423-chat-rendering-polish
- **Type:** change
- **Complexity:** medium
- **Status:** draft
- **Mockup:** `webui/designs/screens/bubble-states.html`
- **Reference session JSONL:** `~/.claude/projects/C--Users-SvenRoth-.../f7d59820-982c-41d7-ac4f-c72b8670f2d5.jsonl` (199 lines, 13 distinct event types)

## Goal
Align BubbleTranscript + session-parser rendering with the `bubble-states.html` mockup, eliminating six concrete user-visible defects surfaced during the 2026-04-23 live compliance-audit test. Chat becomes scannable (tool-cards collapsed by default, smaller font, slash-commands as compact chips, attachments as cards with filename) and complete (TaskCreate tool-uses visible, empty assistant bubbles suppressed).

## Acceptance Criteria (post-external-review, 2026-04-23)
- [ ] **AC-1 Tool cards collapsed by default + stable expansion state.** Every tool_use renders as a collapsed card (icon + title + status badge). Click header to expand/collapse. **Expansion state keyed by `toolUseId`** (NOT by array index) so streaming updates don't reset user toggles. Extract a standalone `<ToolCard>` component so BubbleTranscript stays an orchestrator and card re-renders don't ripple through the transcript.
- [ ] **AC-2 TaskCreate / generic tool_use end-to-end preservation.** Any `tool_use` block with `name` and `input` surfaces as a tool card, regardless of tool name — unknown tools get a neutral icon + `name` as title. **Integration test required:** real TaskCreate event from `f7d59820` fixture must survive parser → ChatMessage → BubbleTranscript → ToolCard with no silent drop.
- [ ] **AC-3 Slash-command chip (strict match).** Parser emits `slash-command` kind ONLY when the user content is EXCLUSIVELY `<command-message>NAME</command-message>\n<command-name>/NAME</command-name>` (whitespace allowed around tags; both tags present and well-formed). Mixed user text + command tags → fall back to normal user-bubble. Renders as centered grey pill with `/command-name`. `commandName` rendered as React text node only (no `dangerouslySetInnerHTML`).
- [ ] **AC-4 AttachmentCard with filename + thumbnail.** `attachment` and `file-history-snapshot` events render as `.attachment-card` per mockup — **basename only** (path.basename, no full paths → avoids leaking user filesystem structure). Multi-file snapshot: show first basename + `+N more` suffix (not silent first-only drop). Mime icon via shared helper (image / doc / code / unknown variants). Non-interactive for now — SmartViewer wire-up deferred.
- [ ] **AC-5 Empty-assistant suppression (completed turns only).** Suppress empty assistant bubbles ONLY for completed turns. During active streaming the bubble must still render (typing/generating indicator) — otherwise users see nothing until first token. Derived helper `hasVisibleBubbleContent(assistantMsg)`: false when all text-block `text.trim()` is empty AND no tool_use blocks. Thinking-only turns get the `.thinking-card` state. Whitespace-only text ("\n\n", "   ") counts as empty after trim.
- [ ] **AC-6 Chat body font-size 13px, explicit-scope cascade.** Body `font-size: 13px; line-height: 1.6`. Explicitly re-declare font-sizes for nested `code`/`pre` (12px), chips (11px), tool-card-title (12.5px), tool-card-body (12px) per mockup tokens so the body change does NOT cascade unintended. Add one integration snapshot test covering mixed content (text + code + chip + tool-card) to catch cascade regressions.

## Review findings applied (external LLM review, 2026-04-23)
Both GPT and Gemini highlighted streaming-state edge case for AC-5 (critical), slash-command over-matching (AC-3), toolUseId-based state keying (AC-1), multi-file snapshot handling (AC-4), font-size cascade (AC-6), and basename sanitization (AC-4). All incorporated above. See `2026-04-23-chat-rendering-polish-external-review.json` for full transcript.

## Affected FRs
- FR-03.50 / FR-03.51 / FR-03.52 (Session init — already covered by Iterate 2 but referenced by mockup section)
- FR-03.53 (Attachments — filename + thumbnail) — formalized here by AC-4
- FR-CHAT-01 / FR-CHAT-02 (chat rendering — tightened by AC-1 / AC-3 / AC-5 / AC-6)

## Out of Scope
- Themes / dark mode
- New bubble states beyond those already in `bubble-states.html` (no speculative render paths)
- Server-side parser changes (webui/server/src/core/session-parser.ts stays as-is — the client renders the derived events; if a server change is absolutely necessary, flag mid-flight and descope)
- SmartViewer wire-up from AttachmentCard click (deferred)
- New event types the parser currently classifies as `unknown` (skill_listing, deferred_tools_delta, task_reminder, auto_mode, command_permissions) — keep the `unknown` fallback silent; surfacing these is a separate iterate
- TaskCreate-specific visualization (rich Linear-style) — just render as generic tool card

## Design Notes
Filled during Design Check. Affected mockup sections:
- `#messages` — user/assistant bubbles (font-size, avatar alignment)
- `#tools` — `.tool-card` collapsed/expanded states + status badges
- `#attachments` — `.attachment-card` with filename + thumbnail
- (NEW) `slash-command-chip` — not in mockup yet; design locally as a centered grey pill with `/command-name` text; document in iterate ADR so future mockup updates reflect it
