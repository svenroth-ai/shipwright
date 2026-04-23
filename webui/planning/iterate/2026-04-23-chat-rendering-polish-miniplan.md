# Mini-Plan: chat-rendering-polish

## Files to touch

**Parser (client-side only per out-of-scope)**
- `webui/client/src/external/session-parser.ts`
  - Add `SlashCommandEvent` kind + matcher: detect UserEvent whose `content` (string) starts with `<command-message>` and extract `<command-name>` tag payload.
  - Add `fileName` extraction to `FileSnapshotEvent` — walk `snapshot.trackedFileBackups` keys, return first filename (or all for multi-file snapshots). If empty, emit event but let renderer show a compact "No file changes in snapshot" chip.
  - Add `isEmpty` derived helper to `AssistantEvent` — true when content yields no text blocks and no tool_use blocks (only `thinking` or empty array).

**Rendering**
- `webui/client/src/components/external/BubbleTranscript.tsx`
  - Switch tool-card default to collapsed (`expanded: false` state per card, click header toggles).
  - Emit status badge (✓ success / ⏳ pending / ✗ error / i info) in collapsed header, derive from `tool_result.is_error` / pending flag.
  - Suppress empty assistant bubbles (AC-5). If assistant has only `thinking`, render `.thinking-card` per mockup.
  - Hook in new `<SlashCommandChip>` render path for `kind: "slash-command"`.
  - Hook in new `<AttachmentCard>` render path for `attachment` + `file-history-snapshot` kinds.
  - Set root `font-size: 13px; line-height: 1.6`.

**New components**
- `webui/client/src/components/external/SlashCommandChip.tsx` — centered grey pill with `/command-name`.
- `webui/client/src/components/external/AttachmentCard.tsx` — filename + mime-matched icon (reuse `lib/image.ts` mime helpers if present, else simple extension map: .md / .tsx / .json / .png etc. → lucide icons).

**Tests**
- `session-parser.test.ts` — add 3 new cases: (a) slash-command detection with command-name extraction, (b) file-history-snapshot fileName extraction from trackedFileBackups, (c) empty assistant content classification.
- `BubbleTranscript.test.tsx` — add 4 cases: (a) tool-card renders collapsed by default + click expands, (b) slash-command-chip rendered (not user-bubble), (c) AttachmentCard rendered for attachment event, (d) empty assistant bubble suppressed.
- `AttachmentCard.test.tsx` NEW — 2 cases: filename display, mime icon selection.
- `SlashCommandChip.test.tsx` NEW — 1 case: command name display.
- Fixture file `client/src/test/fixtures/session-f7d59820-slice.jsonl` — 10 representative events from the live session (one of each type from the 13 observed) for parser integration test.

## Work breakdown
1. Parser: `SlashCommandEvent`, `fileName` extraction, `isEmpty` helper + unit tests (RED → GREEN).
2. Two new components (SlashCommandChip, AttachmentCard) + their tests.
3. BubbleTranscript: collapsed-by-default tool cards + status badge + font-size + new render paths for slash + attachment + empty suppression. Update existing tests.
4. Design Check Tier 2: visual comparison to mockup for all affected sections.
5. Browser Verify: hard refresh, re-open the compliance-audit task, confirm all 6 ACs visually.

## Test strategy
- Unit: parser detection (RED-first), component rendering (RED-first).
- Integration: BubbleTranscript rendering a full slice-fixture from f7d59820 — asserts no empty bubbles, tool cards collapsed, slash chip visible.
- Full client suite (touches_shared_infra → mandatory full).
- TSC baseline preserved.
- Browser verify is the UX sign-off — user live-tests.

## Alternative approach considered
**Split into 2 sub-iterates** (parser-only + UI-only). Rejected because:
- Parser changes (new kinds) require matching renderers; splitting means AC-3/4/5 are each half-done for one merge.
- User explicitly framed as one unified brief with mockup reference.
- Single design-check pass is cheaper than two.

## Risks
- BubbleTranscript is 1119 LOC; edits touch a load-bearing render path. Mitigation: keep existing tests passing, add new ones, Browser Verify catches subtle regressions (e.g. scroll anchoring, auto-scroll).
- Slash-command detection by string prefix is brittle if Claude Code changes the XML format. Mitigation: detection regex is strict (`^<command-message>` and paired `<command-name>` tag); if unmatched, user content falls through to normal user-bubble rendering (no silent drop).
- `thinking-card` mockup state is for standalone thinking-block rendering; empty-assistant suppression is different. Keep them distinct in code.
