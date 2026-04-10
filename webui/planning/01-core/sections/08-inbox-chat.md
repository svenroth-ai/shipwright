# Section 08: Inbox Manager & Chat Store

## Goal

Implement the inbox aggregation system that collects AskUserQuestion events from all running Claude subprocesses into a unified inbox, delivers user answers back to the correct subprocess via stdin, and provides SSE notifications for new inbox items. Also implement the chat store that persists and replays NDJSON messages per task as JSONL files in the project directory.

## FRs Covered

- **FR-01.27** — Aggregate AskUserQuestion events into a unified inbox
- **FR-01.28** — Inbox item structure (question, context, options, project_id, task_id)
- **FR-01.29** — Answer delivery to correct subprocess via stdin
- **FR-01.30** — SSE notification on new inbox item
- **FR-01.31** — Chat message persistence per task
- **FR-01.32** — Chat history loading and replay

## Files to Create/Modify

| Action | Path |
|--------|------|
| Create | `server/src/core/inbox-manager.ts` |
| Create | `server/src/core/chat-store.ts` |
| Create | `server/src/core/inbox-manager.test.ts` |
| Create | `server/src/core/chat-store.test.ts` |

## Implementation Steps

### Step 1: Implement InboxManager Class

Create `server/src/core/inbox-manager.ts`. Export `class InboxManager`:

- **Constructor** takes:
  - `ProcessGovernor` instance (to find the right process for stdin delivery).
  - `ClaudeAdapter` instance (to call `sendStdin()`).
  - `onNotify: (item: InboxItem) => void` callback (for SSE notification).
- **Private state:** `items: Map<string, InboxItem>` keyed by item ID.

### Step 2: Implement `addQuestion()` Method

```typescript
addQuestion(projectId: string, taskId: string, question: string, context?: string, options?: string[]): InboxItem
```

- Generate UUID for item ID.
- Create `InboxItem` with:
  - `id`: generated UUID
  - `projectId`, `taskId`, `question`, `context`, `options` from params
  - `status`: `"pending"`
  - `createdAt`: `new Date().toISOString()`
- Add to `items` Map.
- Call `this.onNotify(item)` to trigger SSE event.
- Return the created item.

This method is the callback target for `ClaudeAdapter.onEvent` when `isAskUserQuestion(msg)` returns true. The coordinator (in Section 10's index.ts) wires this up by extracting the question text, context, and options from the `NdjsonMessage` tool_input.

### Step 3: Implement `answer()` Method

```typescript
answer(itemId: string, answerText: string): InboxItem
```

- Find item by ID. If not found, throw `AppError(404, "Inbox item not found")`.
- If `item.status === "answered"`, throw `AppError(400, "Already answered")`.
- Get the Claude process from governor via `governor.getProcess(item.taskId)`.
- If process not found or exited, throw `AppError(400, "Process no longer running")`.
- Call `adapter.sendStdin(process, answerText)` to deliver the answer to the subprocess.
- Update item: `answer = answerText`, `status = "answered"`, `answeredAt = new Date().toISOString()`.
- Return the updated item.

### Step 4: Implement Query Methods

- `getAll(filter?: { status?: InboxStatus }): InboxItem[]` — return all items from Map as array. If `filter.status` is provided, filter by it. Sort by `createdAt` descending (newest first).
- `getByProject(projectId: string): InboxItem[]` — filter items by `projectId`.
- `getById(itemId: string): InboxItem | undefined` — lookup by ID.

### Step 5: Implement ChatStore Dependencies Interface

Create `server/src/core/chat-store.ts`. Export:

```typescript
export interface ChatStoreDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  appendFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}
```

### Step 6: Implement ChatStore Class

Export `class ChatStore`:

- **Constructor** takes `ChatStoreDeps` with default implementations using `fs/promises`.
- **Private helper:** `basePath(projectDir: string): string` returns `${projectDir}/.shipwright-webui/chat-history/`.

### Step 7: Implement `append()` Method

```typescript
async append(projectDir: string, taskId: string, message: ChatMessage): Promise<void>
```

- Ensure the chat-history directory exists: call `deps.mkdirSync(basePath, { recursive: true })`.
- Serialize `message` as JSON.
- Append the JSON line + `"\n"` to `${basePath}/${taskId}.jsonl` via `deps.appendFile()`.

### Step 8: Implement `load()` Method

```typescript
async load(projectDir: string, taskId: string): Promise<ChatMessage[]>
```

- Compute file path: `${basePath(projectDir)}/${taskId}.jsonl`.
- If file does not exist (`deps.existsSync` returns false), return empty array.
- Read file content via `deps.readFile()`.
- Split by newlines. For each line: try `JSON.parse()`. If parse succeeds and result has `id` and `timestamp` fields, push to result array. Skip malformed lines (same tolerance pattern as event reader).
- Sort result by `timestamp` ascending.
- Return the array.

### Step 9: Implement `exists()` Method

```typescript
exists(projectDir: string, taskId: string): boolean
```

- Return `deps.existsSync(${basePath(projectDir)}/${taskId}.jsonl)`.

### Step 10: Write Unit Tests for InboxManager

Create `server/src/core/inbox-manager.test.ts`:

1. `addQuestion` creates item with correct fields (id, projectId, taskId, question, status "pending", createdAt).
2. `addQuestion` calls `onNotify` callback with the created item.
3. `answer` delivers text to process stdin via `adapter.sendStdin()`.
4. `answer` marks item as answered with `answeredAt` timestamp.
5. `answer` on non-existent item throws 404 error.
6. `answer` on already-answered item throws 400 error.
7. `answer` when process is not running throws 400 error.
8. `getAll()` returns all items sorted by createdAt descending.
9. `getAll({ status: "pending" })` returns only pending items.
10. `getByProject` filters by projectId correctly.

Mock `ProcessGovernor.getProcess()` and `ClaudeAdapter.sendStdin()`.

### Step 11: Write Unit Tests for ChatStore

Create `server/src/core/chat-store.test.ts`:

1. `append` creates directory if missing, appends JSON line with trailing newline.
2. `append` appends to existing file without overwriting.
3. `load` reads and parses all messages, sorted by timestamp ascending.
4. `load` on missing file returns empty array (no throw).
5. `load` with corrupt line in middle skips it, returns valid messages.
6. `exists` returns true when file exists, false otherwise.

Mock all `ChatStoreDeps` methods.

## Test Strategy

### Unit Tests

| File | Coverage |
|------|----------|
| `server/src/core/inbox-manager.test.ts` | Question creation, answer delivery, error cases, filtering |
| `server/src/core/chat-store.test.ts` | Append, load, tolerance, directory creation |

### Integration Tests

No HTTP routes in this section. Integration testing of inbox and chat routes happens in Section 10.

### Mocking Strategy

- `ProcessGovernor` — mock `getProcess()` to return a fake `ClaudeProcess` or undefined.
- `ClaudeAdapter` — mock `sendStdin()` to capture the delivered text.
- `onNotify` callback — jest/vitest mock function to verify it is called with correct args.
- `ChatStoreDeps` — mock all FS operations to use in-memory buffers.

## Dependencies

- **Section 05 (Claude CLI Adapter)** — `ClaudeAdapter` class for `sendStdin()`, `ClaudeProcess` type, `NdjsonMessage` type, `isAskUserQuestion()` function.
- **Section 06 (Process Governor)** — `ProcessGovernor` class for `getProcess()`.
- **Section 07 (Project Registry)** — `ProjectManager` for resolving project paths (used by caller in Section 10).
- **Section 02 (Shared Types)** — `InboxItem`, `InboxStatus`, `ChatMessage`, `ChatMessageType` interfaces.
- **Section 01 (Project Setup)** — `AppError` class from error handler middleware.
- **npm packages:** `uuid`.

## Acceptance Criteria

**FR-01.27: Inbox Aggregation**
- [ ] AskUserQuestion from any active Claude subprocess creates an inbox item
- [ ] Inbox items from multiple projects are accessible via a single global endpoint

**FR-01.28: Inbox Item Structure**
- [ ] Inbox items contain question, context, options, project_id, and task_id
- [ ] Items have a unique ID and timestamp

**FR-01.29: Answer Delivery**
- [ ] POST /api/inbox/:id/answer delivers the answer text to the correct Claude subprocess
- [ ] The inbox item is marked as answered after delivery
- [ ] Answering an already-answered item returns an error

**FR-01.30: Inbox SSE Notification**
- [ ] New inbox items trigger an SSE event of type inbox_new
- [ ] The SSE event includes the inbox item ID and project_id

**FR-01.31: Chat Persistence**
- [ ] NDJSON messages are written to .shipwright-webui/chat-history/{taskId}.jsonl
- [ ] Messages are appended in real-time as the stream progresses

**FR-01.32: Chat Replay**
- [ ] GET /api/projects/:id/chat/:taskId returns the full chronological message list
- [ ] Messages are ordered by timestamp
