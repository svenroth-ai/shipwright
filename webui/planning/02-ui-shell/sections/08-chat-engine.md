# Section 08: Chat Engine — Messages, Tools, Diffs & Input Toolbar

## Goal

Build the complete chat experience for the Task Detail view: user and assistant message bubbles with Markdown rendering, AskUserQuestion interactive cards, tool-call cards (Bash, Read, Grep, Edit, Write) that are collapsible with code diffs for Edit/Write, streaming with a 100ms render buffer, auto-scroll with manual scroll detection, and a chat input area with a toolbar row containing model selector, permission mode, effort level, autonomy toggle, slash-command trigger, and file-reference trigger with autocomplete popups.

## FRs Covered

- **FR-02.25** — User messages right-aligned, assistant messages left-aligned with Markdown (react-markdown + remark-gfm + rehype-highlight).
- **FR-02.26** — AskUserQuestion cards with option buttons and freetext input.
- **FR-02.27** — Tool-call cards (Bash, Read, Grep, Edit, Write) as collapsible cards, collapsed by default.
- **FR-02.28** — Code diffs for Edit/Write via react-diff-viewer (split or unified view).
- **FR-02.29** — Streaming with 100ms render buffer.
- **FR-02.30** — Auto-scroll to latest message unless user scrolled up.
- **FR-02.31** — Chat input with send button, Shift+Enter for newlines, toolbar with model/mode/effort/autonomy/slash/file controls.
- **FR-02.32** — Slash-command autocomplete popup on `/` trigger.
- **FR-02.33** — File-reference autocomplete popup on `@` trigger.

## Files to Create

| File | Purpose |
|------|---------|
| `client/src/components/chat/ChatPanel.tsx` | Chat container: message list + input area + auto-scroll |
| `client/src/components/chat/ChatMessage.tsx` | Message router: delegates to type-specific components |
| `client/src/components/chat/UserMessage.tsx` | Right-aligned user bubble |
| `client/src/components/chat/AssistantMessage.tsx` | Left-aligned assistant bubble with Markdown |
| `client/src/components/chat/AskUserCard.tsx` | Interactive AskUserQuestion card |
| `client/src/components/chat/ToolCallCard.tsx` | Collapsible tool-call card |
| `client/src/components/chat/ToolIcon.tsx` | Icon mapping for tool types |
| `client/src/components/chat/DiffView.tsx` | Code diff wrapper around react-diff-viewer |
| `client/src/components/chat/ChatInput.tsx` | Input area: textarea + send + keyboard handling |
| `client/src/components/chat/ChatToolbar.tsx` | Toolbar row: model, mode, effort, autonomy, /, @ |
| `client/src/components/chat/ModelSelector.tsx` | Model dropdown pill (Opus/Sonnet/Haiku) |
| `client/src/components/chat/PermissionMode.tsx` | Permission mode dropdown pill |
| `client/src/components/chat/EffortPill.tsx` | Effort cycling pill (Low/Med/High) |
| `client/src/components/chat/AutonomyPill.tsx` | Autonomy toggle pill (Guided/Autonomous) |
| `client/src/components/chat/SlashCommandPopup.tsx` | Autocomplete for / commands |
| `client/src/components/chat/FileReferencePopup.tsx` | Autocomplete for @ file references |
| `client/src/components/chat/StreamingIndicator.tsx` | Typing indicator (pulsing dots) |
| `client/src/hooks/useStreamingChat.ts` | SSE streaming hook with 100ms buffer |
| `client/src/hooks/useAutoScroll.ts` | Auto-scroll with manual scroll detection |
| `client/src/hooks/useChatSettings.ts` | Chat settings state (model, mode, effort, autonomy) |
| `client/src/lib/chatCommands.ts` | Available slash commands definition |
| `client/src/components/chat/ChatPanel.test.tsx` | Integration test: chat renders messages |
| `client/src/components/chat/UserMessage.test.tsx` | User bubble rendering |
| `client/src/components/chat/AssistantMessage.test.tsx` | Markdown rendering |
| `client/src/components/chat/AskUserCard.test.tsx` | Option buttons, freetext, submit |
| `client/src/components/chat/ToolCallCard.test.tsx` | Collapse/expand, tool info display |
| `client/src/components/chat/ChatInput.test.tsx` | Send, Shift+Enter, empty validation |
| `client/src/components/chat/SlashCommandPopup.test.tsx` | Popup open/close, filtering |
| `client/src/hooks/useStreamingChat.test.ts` | Buffer timing, token accumulation |
| `client/src/hooks/useAutoScroll.test.ts` | Auto-scroll on/off based on scroll position |

## Implementation Steps

1. **Create `client/src/hooks/useChatSettings.ts`**:
   - Manages chat toolbar state persisted in localStorage:
     - `model: "opus" | "sonnet" | "haiku"` (default "sonnet")
     - `mode: "auto" | "ask" | "edit" | "plan" | "bypass"` (default "auto")
     - `effort: "low" | "medium" | "high"` (default "medium")
     - `autonomy: "guided" | "autonomous"` (default "guided")
   - Uses `useLocalStorage` for each setting
   - Export `useChatSettings()` returning all values + setters

2. **Create `client/src/hooks/useAutoScroll.ts`**:
   - Props: `containerRef: RefObject<HTMLElement>`, `dependencies: unknown[]`
   - Logic:
     - Track `isAtBottom: boolean` — true when scrollTop + clientHeight >= scrollHeight - threshold (50px)
     - On scroll event: update `isAtBottom`
     - On dependency change (new messages): if `isAtBottom`, scroll to bottom
     - Export `scrollToBottom()` for manual scroll-to-bottom button
   - Return `{ isAtBottom, scrollToBottom }`

3. **Create `client/src/hooks/useStreamingChat.ts`**:
   - Export `useStreamingChat(projectId: string, taskId: string)`:
     - Connects to SSE endpoint for chat streaming when a message is being generated
     - 100ms render buffer: accumulate tokens in a ref, flush to state every 100ms via `setInterval`
     - `streamingContent: string` — current partial message being streamed
     - `isStreaming: boolean` — true while receiving tokens
     - On stream end: clear buffer, set `isStreaming = false`, invalidate chat query to fetch complete message
   - Buffer implementation:
     ```typescript
     const bufferRef = useRef<string>("");
     const [displayContent, setDisplayContent] = useState("");
     
     useEffect(() => {
       if (!isStreaming) return;
       const interval = setInterval(() => {
         if (bufferRef.current) {
           setDisplayContent(prev => prev + bufferRef.current);
           bufferRef.current = "";
         }
       }, 100);
       return () => clearInterval(interval);
     }, [isStreaming]);
     ```

4. **Create `client/src/components/chat/UserMessage.tsx`**:
   - Props: `message: ChatMessage`
   - Render: right-aligned bubble
   - Styling: `ml-auto max-w-[80%] bg-[var(--color-primary)] text-white rounded-2xl rounded-br-sm px-4 py-2`
   - Text: `text-sm whitespace-pre-wrap`

5. **Create `client/src/components/chat/AssistantMessage.tsx`**:
   - Props: `message: ChatMessage`, `isStreaming?: boolean`
   - Render: left-aligned bubble with Markdown
   - Styling: `mr-auto max-w-[80%] bg-[var(--color-background)] text-gray-900 rounded-2xl rounded-bl-sm px-4 py-2`
   - Use `react-markdown` with `remarkGfm` and `rehypeHighlight` plugins
   - Custom components for code blocks: syntax-highlighted `<pre><code>` with copy button
   - When `isStreaming`: append `<StreamingIndicator />` at end
   - GFM features: tables, task lists, strikethrough all render correctly

6. **Create `client/src/components/chat/AskUserCard.tsx`**:
   - Props: `message: ChatMessage` (type includes question, options, inbox item ID)
   - State: `selectedOption: string | null`, `freetext: string`, `isAnswered: boolean`
   - Layout: left-aligned card with border
   - Styling: `mr-auto max-w-[80%] border border-amber-200 bg-amber-50 rounded-xl p-4`
   - Content:
     - Question text (prominent, semibold)
     - Option buttons: horizontal row of pills, each clickable
       - `bg-white border border-gray-300 px-3 py-1 rounded-full text-sm hover:border-[var(--color-primary)]`
       - Selected option: `bg-[var(--color-primary)] text-white border-[var(--color-primary)]`
     - Freetext input: `<textarea>` below options, placeholder "Type your answer..."
     - Submit button: sends answer via `useAnswerInbox()` mutation
   - After answer: card transitions to "answered" state — shows selected response, options disabled, subtle green check

7. **Create `client/src/components/chat/ToolIcon.tsx`**:
   - Props: `toolName: string`
   - Map tool names to lucide icons:
     - `Bash` -> `Terminal`
     - `Read` -> `FileText`
     - `Grep` -> `Search`
     - `Edit` -> `Pencil`
     - `Write` -> `FileEdit`
     - Default -> `Wrench`
   - Render icon at 16px with muted color

8. **Create `client/src/components/chat/ToolCallCard.tsx`**:
   - Props: `message: ChatMessage`
   - Use `@radix-ui/react-collapsible` for expand/collapse
   - Collapsed (default): `<ToolIcon />` + tool name + summary line (first arg or file path)
   - Styling: `bg-gray-100 rounded-lg border border-gray-200`
   - Header: `flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-150`
   - Expand chevron: rotates on open
   - Expanded content:
     - Input parameters: rendered as key-value pairs or code block
     - Output content: rendered in `<pre>` with max-height 300px and scroll
     - Long output: truncated at 50 lines with "Show more" toggle that reveals all
   - For Edit/Write tools: render `<DiffView />` instead of plain output

9. **Create `client/src/components/chat/DiffView.tsx`**:
   - Props: `oldContent: string`, `newContent: string`, `fileName?: string`
   - Use `react-diff-viewer-continued` library
   - Default to split view, toggle to unified via button
   - Styling: contained within the ToolCallCard expanded area
   - File name shown above diff when available
   - Syntax highlighting based on file extension

10. **Create `client/src/components/chat/StreamingIndicator.tsx`**:
    - Three pulsing dots animation
    - Styling: `inline-flex gap-1` with three `<span>` dots that pulse via CSS animation
    - CSS: `@keyframes pulse { 0%, 100% { opacity: 0.3 } 50% { opacity: 1 } }` with staggered delay

11. **Create `client/src/components/chat/ChatMessage.tsx`**:
    - Props: `message: ChatMessage`, `isStreaming?: boolean`
    - Routes to appropriate component based on `message.type`:
      - `"user"` -> `<UserMessage />`
      - `"assistant"` -> `<AssistantMessage />`
      - `"tool_use"` or `"tool_result"` -> `<ToolCallCard />`
      - Messages with AskUserQuestion context -> `<AskUserCard />`

12. **Create `client/src/components/chat/ChatPanel.tsx`**:
    - Props: `projectId: string`, `taskId: string`
    - Fetch messages via `useChat(projectId, taskId)`
    - Use `useStreamingChat(projectId, taskId)` for live streaming
    - Use `useAutoScroll(containerRef, [messages, streamingContent])`
    - Layout: `flex flex-col h-full`
      - Message list: `flex-1 overflow-y-auto p-4 space-y-4` with scroll ref
      - Chat input area: `border-t` at bottom
    - Render each message via `<ChatMessage />`
    - If streaming: render partial `<AssistantMessage />` with streaming content appended
    - If `!isAtBottom`: show "scroll to bottom" floating button

13. **Create `client/src/lib/chatCommands.ts`**:
    - Export `CHAT_COMMANDS` array of `{ command: string, description: string }`:
      - `/shipwright-project` — "Decompose requirements"
      - `/shipwright-design` — "Generate UI mockups"
      - `/shipwright-plan` — "Create implementation plan"
      - `/shipwright-build` — "Implement from plan"
      - `/shipwright-test` — "Run tests"
      - `/shipwright-deploy` — "Deploy application"
      - `/shipwright-iterate` — "Iterate on changes"
      - `/shipwright-changelog` — "Generate changelog"

14. **Create `client/src/components/chat/SlashCommandPopup.tsx`**:
    - Props: `query: string`, `onSelect: (command: string) => void`, `onClose: () => void`, `visible: boolean`
    - Filter `CHAT_COMMANDS` by query (case-insensitive prefix match)
    - Use `@radix-ui/react-popover` positioned above the input
    - Each item: command name (mono font) + description
    - Keyboard: arrow keys to navigate, Enter to select, Escape to close
    - Styling: `bg-white border rounded-lg shadow-lg max-h-60 overflow-y-auto`

15. **Create `client/src/components/chat/FileReferencePopup.tsx`**:
    - Props: `query: string`, `projectId: string`, `onSelect: (filePath: string) => void`, `onClose: () => void`, `visible: boolean`
    - Fetch file list from `GET /api/projects/:id/docs` (or from a cached query)
    - Filter files by query (path match)
    - Same popup pattern as SlashCommandPopup
    - Each item: file icon + relative path

16. **Create toolbar pill components**:

    **`client/src/components/chat/ModelSelector.tsx`**:
    - Props: `model: string`, `onChange: (model: string) => void`
    - Pill button showing current model name
    - Radix Popover dropdown with Opus, Sonnet, Haiku options
    - Each option: model name + brief description

    **`client/src/components/chat/PermissionMode.tsx`**:
    - Props: `mode: string`, `onChange: (mode: string) => void`
    - Pill showing mode name
    - Dropdown with 5 options: Auto ("Let Claude decide"), Ask ("Ask before actions"), Edit ("Only edits, no commands"), Plan ("Planning only"), Bypass ("Skip all checks")
    - Each with description text

    **`client/src/components/chat/EffortPill.tsx`**:
    - Props: `effort: string`, `onChange: (effort: string) => void`
    - Pill showing "Low" / "Med" / "High"
    - Click cycles: Low -> Medium -> High -> Low

    **`client/src/components/chat/AutonomyPill.tsx`**:
    - Props: `autonomy: string`, `onChange: (autonomy: string) => void`
    - Pill with colored dot: green = Guided, amber = Autonomous
    - Click toggles between the two modes
    - Tooltip explains current mode

17. **Create `client/src/components/chat/ChatToolbar.tsx`**:
    - Props: all settings from `useChatSettings()`
    - Layout: `flex items-center gap-2 px-3 py-2`
    - Left group: `<ModelSelector />`, `<PermissionMode />`, `<EffortPill />`, `<AutonomyPill />`
    - Right group: `/` icon button (opens slash popup), `@` icon button (opens file popup)
    - Pill styling: `px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer`

18. **Create `client/src/components/chat/ChatInput.tsx`**:
    - Props: `onSend: (message: string, settings: ChatSettings) => void`, `isStreaming: boolean`, `projectId: string`
    - State: `input: string`, `showSlashPopup: boolean`, `showFilePopup: boolean`, `slashQuery: string`, `fileQuery: string`
    - Textarea:
      - Placeholder: "Send a message..."
      - Auto-grows up to 6 lines (max-height), then scrolls
      - Enter sends (when not empty and not streaming)
      - Shift+Enter inserts newline
      - `/` at start of line or after whitespace triggers slash popup
      - `@` triggers file popup
    - Send button: `<button>` with `Send` icon, disabled when input empty or streaming
    - Layout: `<ChatToolbar />` above, textarea + send button below
    - Integrate `useChatSettings()` and pass settings with message on send

19. **Wire ChatPanel into TaskDetailPage**:
    - Replace chat placeholder div with `<ChatPanel projectId={projectId} taskId={taskId} />`

## Test Strategy

### Unit Tests

| Test File | What It Tests |
|-----------|---------------|
| `client/src/components/chat/ChatPanel.test.tsx` | Message list renders; auto-scroll; streaming indicator |
| `client/src/components/chat/UserMessage.test.tsx` | Right-aligned rendering; text content |
| `client/src/components/chat/AssistantMessage.test.tsx` | Markdown renders (headers, code, lists); GFM features |
| `client/src/components/chat/AskUserCard.test.tsx` | Options render; click selects; freetext input; submit calls API |
| `client/src/components/chat/ToolCallCard.test.tsx` | Collapsed by default; expands on click; shows tool info |
| `client/src/components/chat/ChatInput.test.tsx` | Enter sends; Shift+Enter newline; disabled when empty |
| `client/src/components/chat/SlashCommandPopup.test.tsx` | Filters commands; keyboard nav; select inserts |
| `client/src/hooks/useStreamingChat.test.ts` | Buffer flushes at 100ms intervals; isStreaming state |
| `client/src/hooks/useAutoScroll.test.ts` | Scrolls on new message; stops when scrolled up |

### Test Details

- **ChatPanel**: MSW returns mock chat messages array. Assert user and assistant messages render. Assert auto-scroll fires on new messages.
- **AssistantMessage**: Render with Markdown content including `# Heading`, `**bold**`, `` `code` ``, fenced code block. Assert heading, bold, code elements in DOM.
- **AskUserCard**: Render with options ["Redis", "Postgres"]. Click "Redis", assert selected state. Type in freetext "Both with fallback", submit. Assert `POST /api/inbox/:id/answer` called with answer. Assert card shows "answered" state.
- **ToolCallCard**: Render with Bash tool message. Assert collapsed: tool name visible, output hidden. Click header, assert expanded: output visible. For Edit tool: assert DiffView renders.
- **ChatInput**: Type "hello", press Enter. Assert `onSend` called with "hello". Type "line1", Shift+Enter, type "line2". Assert input contains both lines (not sent). Empty input, assert send button disabled.
- **SlashCommandPopup**: Render with `query="ship"`. Assert filtered commands visible. Press ArrowDown, Enter. Assert `onSelect` called with command.
- **useStreamingChat**: Mock SSE events. Assert buffer accumulates tokens. After 100ms, assert `displayContent` updated. On stream end, assert `isStreaming` false.

## Dependencies

- **Section 03** — `useChat`, `useSendChat`, `useAnswerInbox`, `useSSE`, SSE integration
- **Section 07** — `TaskDetailPage`, `PanelLayout` (chat panel plugs into left side)

## Acceptance Criteria

From spec:
- [ ] User messages right-aligned with distinct background color
- [ ] Assistant messages left-aligned with Markdown formatting (headings, lists, bold, links)
- [ ] Code blocks have syntax highlighting via rehype-highlight
- [ ] GFM features render correctly (tables, task lists, strikethrough)
- [ ] AskUserQuestion card displays question, option pills, freetext input
- [ ] Clicking option or submitting freetext sends POST /api/inbox/:id/answer
- [ ] After answering, card shows "answered" state
- [ ] Tool-call cards show icon + label for tool type
- [ ] Cards collapsed by default, showing only tool name + summary
- [ ] Expanding reveals input parameters and output
- [ ] Long output truncated with "Show more" toggle
- [ ] Edit/Write tool calls show code diff via react-diff-viewer
- [ ] Streaming tokens buffered and flushed every 100ms
- [ ] Partial Markdown renders correctly during streaming
- [ ] Typing indicator visible during streaming
- [ ] Chat auto-scrolls to latest message on new content
- [ ] Auto-scroll stops when user scrolls up manually
- [ ] Enter sends message, Shift+Enter inserts newline
- [ ] Send button disabled when input empty
- [ ] Input auto-grows up to 6 lines
- [ ] Toolbar shows model, mode, effort, autonomy, / commands, @ files
- [ ] Model selector opens dropdown with Opus/Sonnet/Haiku
- [ ] Permission mode shows all 5 modes
- [ ] Effort click cycles through Low/Med/High
- [ ] Autonomy shows colored dot (green=guided, amber=autonomous), click toggles
- [ ] `/` in input opens command autocomplete, filtered as user types
- [ ] Selecting command inserts into input; popup closes on Escape
- [ ] `@` in input opens file picker, filtered as user types
- [ ] Selecting file inserts reference into input
