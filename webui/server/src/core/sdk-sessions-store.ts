/*
 * Persisted store for external-launch task metadata.
 *
 * Shape (on disk, `<registryDir>/sdk-sessions.json`):
 *   {
 *     schemaVersion: 2,
 *     sessions: {
 *       [taskId]: {
 *         taskId,
 *         sessionUuid,
 *         cwd,
 *         pluginDirs,
 *         parentTaskId?,
 *         parentSessionUuid?,
 *         state,               // see PocTaskState below
 *         title,
 *         projectId,           // v2 (iterate 3 section 02) — "unassigned" reserved
 *         createdAt,
 *         launchedAt?,
 *         firstJsonlObservedAt?,
 *         lastJsonlSeenMtimeMs?,
 *         inbox: { pendingToolUseIds: string[], dismissedToolUseIds: string[], lastProcessedByteOffset: number },
 *       }
 *     }
 *   }
 *
 * Schema migration (ADR-038): CURRENT_SCHEMA_VERSION = 2. The loader
 * accepts both v1 and v2 on disk. v1 rows are backfilled with
 * `projectId: "unassigned"` in memory (write-on-touch — the first
 * persist() after any mutation flushes the whole shape as v2). This
 * keeps the migration incremental — large stores (300+ rows) migrate
 * over days of normal use rather than on boot, and rollback is a
 * one-line constant revert.
 *
 * O26 (deleted project references): if a dep `getKnownProjectIds` is
 * injected, v2 rows whose projectId is not in the known set resolve
 * to "unassigned" in memory and on the next persist. Keeps the task
 * store coherent with projects.json without a separate reconcile job.
 *
 * O25 (forward compat): the v1 branch tolerates an unknown projectId
 * field — older binaries don't crash when faced with a v2-ish row
 * tagged v1 (e.g. after a partial rollback).
 *
 * Writes are guarded by proper-lockfile (via injected lock dep). Reads
 * are unguarded — the store is consulted on every request, and dirty
 * reads (post-write, pre-flush) are acceptable since we persist the
 * full shape atomically.
 *
 * Corruption tolerance: a malformed entry fails ONLY its own read, not
 * the whole file. We deliberately soft-skip entries that fail schema
 * validation rather than throwing, because a single bad row shouldn't
 * knock out every other session on restart (round-2 GPT MAJOR 6).
 */

import { randomUUID } from "node:crypto";

export type ExternalTaskState =
  | "draft"
  | "awaiting_external_start"
  | "active"
  | "idle"
  | "jsonl_missing"
  | "launch_failed"
  | "done";

/**
 * Reserved projectId sentinel for the "Unassigned" pseudo-project bucket.
 * Kept in sync with client/src/lib/projectIds.ts (intentional duplication
 * per conventions.md — the two sides don't import each other).
 */
export const UNASSIGNED_PROJECT_ID = "unassigned";

export interface ExternalTaskInboxState {
  pendingToolUseIds: string[];
  dismissedToolUseIds: string[];
  /** Byte offset in the JSONL up to which inbox-derive has processed. */
  lastProcessedByteOffset: number;
}

export interface ExternalTask {
  taskId: string;
  sessionUuid: string;
  cwd: string;
  pluginDirs: string[];
  parentTaskId?: string;
  parentSessionUuid?: string;
  state: ExternalTaskState;
  title: string;
  /**
   * v2 — iterate 3 section 02. ADR-037. Always a non-empty string; the
   * reserved literal UNASSIGNED_PROJECT_ID represents tasks without a
   * chosen project (and deleted-project references resolved via O26).
   * v1 rows on disk are backfilled with UNASSIGNED_PROJECT_ID at load time.
   */
  projectId: string;
  createdAt: string;
  launchedAt?: string;
  firstJsonlObservedAt?: string;
  lastJsonlSeenMtimeMs?: number;
  inbox: ExternalTaskInboxState;
}

export interface SdkSessionsFile {
  schemaVersion: 1 | 2;
  sessions: Record<string, ExternalTask>;
}

export interface SdkSessionsStoreDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  /** Optional proper-lockfile wrapper; omitted in tests. */
  lock?: (path: string) => Promise<() => Promise<void>>;
  /** Creates an empty file if missing (proper-lockfile requires lstat). */
  ensureFile: (path: string) => void;
  /**
   * Optional — section 02 O26. If provided, v2-loaded rows whose
   * projectId is not in this set are resolved to UNASSIGNED_PROJECT_ID
   * in memory. Next persist() writes the canonical value back.
   * Omitted in unit tests (skips the resolve step).
   */
  getKnownProjectIds?: () => Set<string>;
}

const CURRENT_SCHEMA_VERSION = 2 as const;

export class SdkSessionsStore {
  private readonly path: string;
  private readonly deps: SdkSessionsStoreDeps;
  private sessions = new Map<string, ExternalTask>();
  private loaded = false;

  constructor(path: string, deps: SdkSessionsStoreDeps) {
    this.path = path;
    this.deps = deps;
  }

  async load(): Promise<void> {
    if (this.loaded) return;
    if (!this.deps.existsSync(this.path)) {
      this.sessions.clear();
      this.loaded = true;
      return;
    }
    let raw: string;
    try {
      raw = await this.deps.readFile(this.path, "utf-8");
    } catch {
      // Unreadable file → start empty. Write path will create a fresh one.
      this.sessions.clear();
      this.loaded = true;
      return;
    }
    if (!raw.trim()) {
      this.sessions.clear();
      this.loaded = true;
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // Corrupted top-level JSON → don't silently wipe; rename aside + start empty.
      const asideName = `${this.path}.corrupt-${Date.now()}`;
      try {
        await this.deps.writeFile(asideName, raw);
      } catch { /* ignore */ }
      this.sessions.clear();
      this.loaded = true;
      return;
    }

    // Schema-version gate. We accept v1 and v2 (ADR-038). Anything else
    // → start empty (future version, won't silently misinterpret).
    const schemaVersion =
      parsed && typeof parsed === "object" && "schemaVersion" in parsed
        ? (parsed as { schemaVersion: unknown }).schemaVersion
        : undefined;
    if (schemaVersion !== 1 && schemaVersion !== 2) {
      this.sessions.clear();
      this.loaded = true;
      return;
    }

    const sessionsObj =
      parsed && typeof parsed === "object" && "sessions" in parsed
        ? (parsed as { sessions: unknown }).sessions
        : undefined;
    if (!sessionsObj || typeof sessionsObj !== "object") {
      this.sessions.clear();
      this.loaded = true;
      return;
    }

    // Per-entry fault isolation: a bad row is dropped, the rest survive.
    for (const [taskId, value] of Object.entries(sessionsObj as Record<string, unknown>)) {
      const task = validateExternalTask(taskId, value, schemaVersion);
      if (task) this.sessions.set(taskId, task);
    }

    // O26: resolve stale projectId references to UNASSIGNED. Only runs when
    // the wiring provides a known-project-id set (production has it; unit
    // tests typically don't — which is fine, they test the pre-resolve shape).
    if (this.deps.getKnownProjectIds) {
      const known = this.deps.getKnownProjectIds();
      for (const task of this.sessions.values()) {
        if (
          task.projectId !== UNASSIGNED_PROJECT_ID &&
          !known.has(task.projectId)
        ) {
          task.projectId = UNASSIGNED_PROJECT_ID;
        }
      }
    }

    this.loaded = true;
  }

  create(args: {
    title: string;
    cwd: string;
    pluginDirs?: string[];
    parentTaskId?: string;
    parentSessionUuid?: string;
    /**
     * v2 — iterate 3 section 02. Defaults to UNASSIGNED_PROJECT_ID when
     * omitted. Callers that know the active project (e.g. the inline
     * task-creation form on TaskBoardPage) pass it explicitly.
     */
    projectId?: string;
  }): ExternalTask {
    const task: ExternalTask = {
      taskId: randomUUID(),
      sessionUuid: randomUUID(),
      cwd: args.cwd,
      pluginDirs: args.pluginDirs ?? [],
      parentTaskId: args.parentTaskId,
      parentSessionUuid: args.parentSessionUuid,
      title: args.title,
      projectId:
        typeof args.projectId === "string" && args.projectId.trim()
          ? args.projectId.trim()
          : UNASSIGNED_PROJECT_ID,
      state: "draft",
      createdAt: new Date().toISOString(),
      inbox: {
        pendingToolUseIds: [],
        dismissedToolUseIds: [],
        lastProcessedByteOffset: 0,
      },
    };
    this.sessions.set(task.taskId, task);
    return task;
  }

  get(taskId: string): ExternalTask | undefined {
    return this.sessions.get(taskId);
  }

  list(): ExternalTask[] {
    return Array.from(this.sessions.values()).sort((a, b) =>
      a.createdAt < b.createdAt ? 1 : -1,
    );
  }

  /** Apply a partial patch to a task; returns the updated copy or undefined. */
  patch(taskId: string, patch: Partial<ExternalTask>): ExternalTask | undefined {
    const task = this.sessions.get(taskId);
    if (!task) return undefined;
    Object.assign(task, patch);
    return task;
  }

  delete(taskId: string): boolean {
    return this.sessions.delete(taskId);
  }

  /**
   * Atomically persist the current in-memory state to disk. Guarded by the
   * injected lock if provided. Callers should `await persist()` after any
   * mutation that matters for a later server restart.
   */
  async persist(): Promise<void> {
    // Ensure parent dir + file exist before locking (proper-lockfile lstats).
    const lastSlash = Math.max(this.path.lastIndexOf("/"), this.path.lastIndexOf("\\"));
    if (lastSlash !== -1) {
      const dir = this.path.slice(0, lastSlash);
      if (!this.deps.existsSync(dir)) this.deps.mkdirSync(dir, { recursive: true });
    }
    this.deps.ensureFile(this.path);

    const payload: SdkSessionsFile = {
      schemaVersion: CURRENT_SCHEMA_VERSION,
      sessions: Object.fromEntries(this.sessions),
    };
    const serialized = JSON.stringify(payload, null, 2);

    const release = this.deps.lock ? await this.deps.lock(this.path) : null;
    try {
      await this.deps.writeFile(this.path, serialized);
    } finally {
      if (release) await release();
    }
  }
}

// ---------- schema validators (hand-rolled; zod stays out of the store
// load path because a single malformed field shouldn't cascade-throw) ----------

function validateExternalTask(
  taskId: string,
  raw: unknown,
  schemaVersion: 1 | 2,
): ExternalTask | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (r.taskId !== taskId) return null;
  if (typeof r.sessionUuid !== "string") return null;
  if (typeof r.cwd !== "string") return null;
  if (typeof r.title !== "string") return null;
  if (typeof r.createdAt !== "string") return null;
  const pluginDirs = Array.isArray(r.pluginDirs)
    ? r.pluginDirs.filter((x: unknown): x is string => typeof x === "string")
    : [];
  const validStates: ExternalTaskState[] = [
    "draft",
    "awaiting_external_start",
    "active",
    "idle",
    "jsonl_missing",
    "launch_failed",
    "done",
  ];
  const state = validStates.includes(r.state as ExternalTaskState)
    ? (r.state as ExternalTaskState)
    : "draft";

  // projectId branches on schemaVersion (ADR-038).
  //
  // v1: any projectId field on disk is untrusted (this is a compat-window
  //   shape, e.g. an older binary read a v2 row tagged v1). Always
  //   backfill UNASSIGNED_PROJECT_ID. External review O25.
  // v2: require a non-empty string; soft-skip the row otherwise (null,
  //   empty-string, or non-string = corrupt).
  let projectId: string;
  if (schemaVersion === 1) {
    projectId = UNASSIGNED_PROJECT_ID;
  } else {
    if (typeof r.projectId !== "string" || r.projectId.trim() === "") {
      return null;
    }
    projectId = r.projectId.trim();
  }

  const rawInbox = r.inbox;
  const inbox: ExternalTaskInboxState =
    rawInbox && typeof rawInbox === "object"
      ? {
          pendingToolUseIds: Array.isArray((rawInbox as Record<string, unknown>).pendingToolUseIds)
            ? ((rawInbox as Record<string, unknown>).pendingToolUseIds as unknown[]).filter(
                (x: unknown): x is string => typeof x === "string",
              )
            : [],
          dismissedToolUseIds: Array.isArray((rawInbox as Record<string, unknown>).dismissedToolUseIds)
            ? ((rawInbox as Record<string, unknown>).dismissedToolUseIds as unknown[]).filter(
                (x: unknown): x is string => typeof x === "string",
              )
            : [],
          lastProcessedByteOffset:
            typeof (rawInbox as Record<string, unknown>).lastProcessedByteOffset === "number"
              ? ((rawInbox as Record<string, unknown>).lastProcessedByteOffset as number)
              : 0,
        }
      : { pendingToolUseIds: [], dismissedToolUseIds: [], lastProcessedByteOffset: 0 };

  return {
    taskId,
    sessionUuid: r.sessionUuid,
    cwd: r.cwd,
    pluginDirs,
    parentTaskId: typeof r.parentTaskId === "string" ? r.parentTaskId : undefined,
    parentSessionUuid: typeof r.parentSessionUuid === "string" ? r.parentSessionUuid : undefined,
    title: r.title,
    projectId,
    state,
    createdAt: r.createdAt,
    launchedAt: typeof r.launchedAt === "string" ? r.launchedAt : undefined,
    firstJsonlObservedAt: typeof r.firstJsonlObservedAt === "string" ? r.firstJsonlObservedAt : undefined,
    lastJsonlSeenMtimeMs:
      typeof r.lastJsonlSeenMtimeMs === "number" ? r.lastJsonlSeenMtimeMs : undefined,
    inbox,
  };
}
