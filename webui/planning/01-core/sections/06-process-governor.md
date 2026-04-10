# Section 06: Process Governor — Concurrency & Lifecycle

## Goal

Implement the concurrency semaphore that limits parallel Claude processes to a configurable maximum, PID tracking for orphan detection, orphan cleanup on server startup, a heartbeat scheduler that monitors process health at 30-second intervals, and a task queue for overflow when the concurrency limit is reached.

## FRs Covered

- **FR-01.19** — Configurable concurrency semaphore (default 3)
- **FR-01.20** — PID tracking of all spawned Claude processes
- **FR-01.21** — Orphaned process detection and termination on startup
- **FR-01.22** — Heartbeat scheduler at 30-second intervals
- **FR-01.23** — Task queuing when concurrency limit exceeded

## Files to Create/Modify

| Action | Path |
|--------|------|
| Create | `server/src/core/process-governor.ts` |
| Create | `server/src/core/heartbeat.ts` |
| Create | `server/src/core/process-governor.test.ts` |
| Create | `server/src/core/heartbeat.test.ts` |

## Implementation Steps

### Step 1: Define GovernorDeps Interface

Create `server/src/core/process-governor.ts`. Export an interface `GovernorDeps` with injectable OS-level operations:

```typescript
export interface GovernorDeps {
  isProcessRunning: (pid: number) => boolean;
  kill: (pid: number, signal?: string) => void;
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}
```

Provide a default implementation where `isProcessRunning` uses `process.kill(pid, 0)` wrapped in try/catch (returns true if no error, false on ESRCH), and `kill` uses `process.kill(pid, signal)`.

### Step 2: Implement ProcessGovernor Class

In the same file, export `class ProcessGovernor`:

- **Constructor** takes `maxConcurrent: number`, a `ClaudeAdapter` instance, and `GovernorDeps`.
- **Private state:**
  - `activeProcesses: Map<string, ClaudeProcess>` keyed by taskId.
  - `queue: ClaudeSpawnOptions[]` for overflow tasks.
  - `pidFilePath: string` resolving to `~/.shipwright-webui/pids.json`.

### Step 3: Implement `acquire()` Method

```typescript
async acquire(options: ClaudeSpawnOptions): Promise<ClaudeProcess | "queued">
```

- If `activeProcesses.size < maxConcurrent`: spawn via `this.adapter.spawn(options)`, add to `activeProcesses`, persist PIDs, return the `ClaudeProcess`.
- Otherwise: push `options` to `queue`, return `"queued"`.

### Step 4: Implement `release()` Method

```typescript
release(taskId: string): void
```

- Remove from `activeProcesses`, update PID file.
- If `queue` is non-empty: shift the first item, call `acquire()` to auto-start it (drain the queue).

### Step 5: Implement PID Persistence

- `persistPids(): Promise<void>` — serialize all active PIDs (as `Array<{ pid: number; taskId: string }>`) to JSON and write to `pidFilePath`. Ensure the directory exists.
- `loadPids(): Promise<Array<{ pid: number; taskId: string }>>` — read and parse PID file. Return empty array if file does not exist.

### Step 6: Implement `cleanupOrphans()` Method

```typescript
async cleanupOrphans(): Promise<{ killed: number; stale: number }>
```

- Load PIDs from previous run via `loadPids()`.
- For each tracked PID: check `deps.isProcessRunning(pid)`.
  - If running but PID is not in current `activeProcesses` -> kill it (orphan), increment `killed`.
  - If not running -> increment `stale` (remove from tracking).
- Clear the PID file after cleanup.
- Log cleanup results with counts.

### Step 7: Implement Accessor Methods

- `getProcess(taskId: string): ClaudeProcess | undefined` — lookup in `activeProcesses`.
- `getAllActive(): ClaudeProcess[]` — return all values from `activeProcesses`.
- `getQueueLength(): number` — return `queue.length`.

### Step 8: Create HeartbeatScheduler

Create `server/src/core/heartbeat.ts`. Export `class HeartbeatScheduler`:

- **Constructor** takes `ProcessGovernor` instance, `GovernorDeps`, and an optional cron expression string (default `"*/30 * * * * *"` for every 30 seconds).
- `start(): void` — use `node-cron` to schedule a job that:
  1. Iterates `governor.getAllActive()`.
  2. For each process: check `deps.isProcessRunning(process.pid)`.
  3. If process is dead: log it, call `governor.release(process.taskId)` which triggers queue drain.
  4. Log the health check summary (active count, queue length).
- `stop(): void` — destroy the cron job.

### Step 9: Write Unit Tests for ProcessGovernor

Create `server/src/core/process-governor.test.ts` with these test cases:

1. Spawn 3 processes with `maxConcurrent: 3` -> all active, none queued.
2. Spawn a 4th process -> returns `"queued"`.
3. Release one process -> queued task auto-starts (queue drain).
4. `cleanupOrphans` with 2 stale PIDs and 1 running orphan -> kills 1, removes 2 stale.
5. PID tracking: spawn adds PID to file, release removes it.
6. `persistPids` writes correct JSON structure.
7. `getProcess` returns correct process by taskId.
8. `getAllActive` returns all active processes.
9. `getQueueLength` reflects queue state accurately.

Mock `ClaudeAdapter.spawn()` to return a fake `ClaudeProcess`. Mock all `GovernorDeps` methods.

### Step 10: Write Unit Tests for HeartbeatScheduler

Create `server/src/core/heartbeat.test.ts` with these test cases:

1. Mock cron to fire callback immediately. Dead process detected -> `release()` called.
2. Healthy processes -> no action taken.
3. `stop()` destroys the cron job.
4. Health check logs active count and queue length.

Mock `node-cron` to capture the scheduled callback and invoke it synchronously.

## Test Strategy

### Unit Tests

| File | Coverage |
|------|----------|
| `server/src/core/process-governor.test.ts` | Semaphore enforcement, queue overflow/drain, PID tracking, orphan cleanup, persistence |
| `server/src/core/heartbeat.test.ts` | Dead process detection, healthy process pass-through, cron start/stop |

### Integration Tests

No HTTP routes in this section. Integration testing happens in Section 10 when routes wire up the governor.

### Mocking Strategy

- `ClaudeAdapter` — mock `spawn()` to return fake `ClaudeProcess` objects with controllable PIDs.
- `GovernorDeps` — mock `isProcessRunning`, `kill`, and all FS operations.
- `node-cron` — mock `schedule()` to capture and invoke the callback directly.

## Dependencies

- **Section 05 (Claude CLI Adapter)** — `ClaudeAdapter` class and `ClaudeProcess` / `ClaudeSpawnOptions` interfaces.
- **Section 02 (Shared Types)** — TypeScript type definitions.
- **Section 01 (Project Setup)** — `config.ts` for `maxConcurrent` default and `registryDir` path.
- **npm packages:** `node-cron`, `@types/node`.

## Acceptance Criteria

**FR-01.19: Concurrency Semaphore**
- [ ] No more than N Claude processes run simultaneously (default 3)
- [ ] The concurrency limit is configurable via settings
- [ ] Exceeding the limit queues the task rather than rejecting it

**FR-01.20: PID Tracking**
- [ ] Every spawned Claude process PID is recorded
- [ ] PIDs are removed from tracking when the process exits

**FR-01.21: Orphan Cleanup**
- [ ] On startup, tracked PIDs are checked against running OS processes
- [ ] Stale PIDs (process no longer running) are removed from tracking
- [ ] Still-running orphaned processes are terminated

**FR-01.22: Heartbeat Scheduler**
- [ ] Heartbeat runs every 30 seconds
- [ ] Dead processes are detected and their tasks marked as failed
- [ ] Queued tasks are started when slots become available

**FR-01.23: Task Queuing (Should)**
- [ ] Tasks exceeding the concurrency limit are queued
- [ ] Queued tasks start automatically when a slot becomes available
