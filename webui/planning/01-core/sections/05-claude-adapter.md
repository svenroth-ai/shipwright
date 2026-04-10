# Section 05: Claude CLI Adapter

## Goal

Implement the adapter that spawns Claude CLI as a child process with proper flags, parses the NDJSON output stream in real-time, manages sessions (new vs. resume), delivers stdin input, and tracks process lifecycle states.

## FRs Covered

- **FR-01.07** — The system SHALL spawn Claude CLI as a child process with --output-format stream-json and --plugin-dir flags for all registered Shipwright plugins.
- **FR-01.08** — The system SHALL parse the NDJSON stream from Claude CLI, handling assistant, tool_use, tool_result, and result message types.
- **FR-01.09** — The system SHALL manage Claude sessions using --session-id for new sessions and --continue for session resumption.
- **FR-01.10** — The system SHALL deliver user input to a running Claude subprocess via stdin when responding to AskUserQuestion prompts.
- **FR-01.11** — The system SHALL track process lifecycle states (spawning, running, exited) and capture the exit code on process termination.
- **FR-01.12** — The system SHALL forward parsed NDJSON events to the SSE Manager for real-time streaming to the frontend.
- **FR-01.13** — The system SHOULD skip malformed NDJSON lines without crashing the stream parser.

## Files to Create

| File | Purpose |
|------|---------|
| `server/src/core/ndjson-parser.ts` | Standalone NDJSON line parser (pure function) |
| `server/src/core/claude-adapter.ts` | Claude CLI spawn, NDJSON stream parser, session management |
| `server/src/core/ndjson-parser.test.ts` | Unit tests for parser |
| `server/src/core/claude-adapter.test.ts` | Unit tests for adapter |

## Implementation Steps

1. **Create `server/src/core/ndjson-parser.ts`**:
   - Export `parseNdjsonLine(line: string): NdjsonMessage | null`:
     - Trim the line. If empty, return null
     - Try `JSON.parse(line)`. If fails, log warning and return null (FR-01.13)
     - Validate result has a `type` field (string). If missing, return null
     - Return typed `NdjsonMessage`
   - Export `isAskUserQuestion(msg: NdjsonMessage): boolean`:
     - Returns true when `msg.type === "tool_use"` and `msg.tool_name === "AskUserQuestion"` (or check `msg.message?.tool_name`)

2. **Create `server/src/core/claude-adapter.ts`**:
   - Export `ProcessState` as const union: `"spawning" | "running" | "exited"`
   - Export interface `ClaudeProcess`:
     - `pid: number`, `taskId: string`, `projectId: string`, `sessionId: string`
     - `state: ProcessState`, `exitCode?: number`, `process: ChildProcess`
   - Export interface `SpawnDeps`: `{ spawn: typeof child_process.spawn }` — injectable (QR-01.09)
   - Export interface `ClaudeSpawnOptions`:
     - `projectDir: string`, `projectId: string`, `taskId: string`
     - `sessionId?: string`, `resume: boolean`, `pluginDirs: string[]`
     - `prompt: string`, `claudeCliPath?: string`
   - Export class `ClaudeAdapter`:
     - Constructor takes `SpawnDeps` and an `onEvent: (taskId: string, msg: NdjsonMessage) => void` callback (for SSE forwarding, FR-01.12)
     - **`spawn(options: ClaudeSpawnOptions): ClaudeProcess`**:
       - Build args array: `["--output-format", "stream-json"]`
       - For each `pluginDir` in options: add `["--plugin-dir", dir]`
       - If `options.resume` is true: add `["--continue"]`. Else: add `["--session-id", options.sessionId]`
       - Add `["-p", options.prompt]` for the initial prompt
       - Spawn `claude` (or `options.claudeCliPath`) with args, `cwd: options.projectDir`, `stdio: ["pipe", "pipe", "pipe"]`
       - Set state to `spawning`, transition to `running` on first stdout data
       - Attach stdout line-by-line reader (split on `\n`), parse each line with `parseNdjsonLine()`, call `onEvent` callback for valid messages (FR-01.08, FR-01.12)
       - Attach stderr handler — log errors with context (QR-01.08)
       - Attach `close` handler — update state to `exited`, capture exit code (FR-01.11)
       - Return `ClaudeProcess` object
     - **`sendStdin(process: ClaudeProcess, input: string): void`**:
       - If `process.state === "exited"`, throw `AppError(400, "Process has exited")`
       - Write `input + "\n"` to `process.process.stdin` (FR-01.10)
     - **`terminate(process: ClaudeProcess): void`**:
       - Send SIGTERM, set state to `exited`
     - **Private `createLineReader(stream: Readable): AsyncIterable<string>`**:
       - Split stream on newline boundaries, handle partial chunks

## Test Strategy

### Unit Tests

**`server/src/core/ndjson-parser.test.ts`**:
- Valid assistant message JSON -> parsed correctly with type `"assistant"`
- Valid tool_use JSON with `tool_name: "AskUserQuestion"` -> `isAskUserQuestion` returns true
- tool_use JSON with different tool_name -> `isAskUserQuestion` returns false
- Malformed JSON string -> returns null (no throw)
- Empty line -> returns null
- JSON without `type` field -> returns null
- Performance: parse 1000 lines in <50ms (QR-01.03)

**`server/src/core/claude-adapter.test.ts`** (mock `spawn` returns a fake ChildProcess with piped streams):
- **Spawn and stream parsing:**
  - Write NDJSON lines to fake stdout -> `onEvent` callback called with parsed messages
  - Multiple NDJSON lines -> `onEvent` called once per valid line
  - Malformed line in stdout stream -> skipped, next lines still parsed
- **Process lifecycle:**
  - Process exit with code 0 -> state becomes `exited`, exitCode is 0
  - Process exit with non-zero code -> state becomes `exited`, exitCode captured
  - State transitions: spawning -> running (on first stdout data)
- **Stdin delivery:**
  - `sendStdin` writes `input + "\n"` to stdin pipe
  - `sendStdin` on exited process -> throws `AppError(400)`
- **Args construction:**
  - New session: verify `--output-format stream-json`, `--session-id <id>`, `-p <prompt>` in args
  - Resume session: verify `--continue` flag present, no `--session-id`
  - Plugin dirs: verify `--plugin-dir <dir>` for each directory
  - Custom CLI path: verify custom path used as command instead of `claude`
- **Terminate:**
  - `terminate` sends signal and sets state to `exited`

### Integration Tests

N/A — subprocess mocked, no HTTP endpoints.

## Dependencies

- **Section 02** — shared types (`NdjsonMessage`, `ChatMessageType`)
- **Section 01** — `AppError` class from `server/src/middleware/error-handler.ts`

## Acceptance Criteria

**FR-01.07: Claude CLI Spawn**
- [ ] Claude CLI is spawned with --output-format stream-json
- [ ] All Shipwright plugin directories are passed via --plugin-dir flags
- [ ] The working directory is set to the project directory

**FR-01.08: NDJSON Stream Parsing**
- [ ] assistant messages are parsed and forwarded
- [ ] tool_use messages are parsed with name and input
- [ ] tool_result messages are parsed with output
- [ ] result messages are parsed and trigger process completion handling

**FR-01.09: Session Management**
- [ ] New tasks generate a unique session ID and pass --session-id
- [ ] Resumed tasks use --continue to continue the existing session
- [ ] Session IDs are persisted for task-to-session mapping

**FR-01.10: Stdin Delivery**
- [ ] User answers are written to the correct subprocess stdin
- [ ] The Claude process resumes processing after receiving stdin input
- [ ] Writing to stdin of a terminated process returns an error

**FR-01.11: Process Lifecycle**
- [ ] Process state transitions are tracked (spawning -> running -> exited)
- [ ] Exit code is captured and stored on process termination
- [ ] Non-zero exit codes mark the associated task as failed

**FR-01.12: NDJSON to SSE Forwarding**
- [ ] Parsed NDJSON events are forwarded to the SSE Manager via the onEvent callback

**FR-01.13: Malformed NDJSON Handling**
- [ ] Malformed NDJSON lines are skipped without crashing the stream parser
- [ ] Subsequent valid lines are still parsed after a malformed line
