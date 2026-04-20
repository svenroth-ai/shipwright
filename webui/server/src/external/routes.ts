/*
 * /api/external/* — Sub-iterate 1 production routes.
 *
 * Stays under /api/external for now so it doesn't collide with the
 * existing /api/tasks (which still drives the old chat UI). Sub-iterate 2
 * renames to /api/tasks after deleting the chat surface.
 *
 * Backed by the promoted core modules:
 *   - core/launcher.ts         (copy-command generation)
 *   - core/session-watcher.ts  (filename-first discovery + byte-range read)
 *   - core/session-parser.ts   (server-side parser for inbox)
 *   - core/inbox-derive.ts     (pending tool_use extraction)
 *   - core/sdk-sessions-store.ts (persisted task metadata)
 *   - core/cli-compat.ts       (version-gate injection for diagnostics)
 */

import { Hono } from "hono";

import { buildCopyCommands } from "../core/launcher.js";
import { SessionWatcher } from "../core/session-watcher.js";
import { parseSessionJsonl } from "../core/session-parser.js";
import { deriveInbox, DEFAULT_USER_BLOCKING_TOOLS } from "../core/inbox-derive.js";
import {
  SdkSessionsStore,
  UNASSIGNED_PROJECT_ID,
  type ExternalTask,
  type ExternalTaskState,
} from "../core/sdk-sessions-store.js";

const ACTIVE_IDLE_THRESHOLD_MS = 120_000;
const IDLE_REACTIVATE_THRESHOLD_MS = 5_000;

/** Hard cap on user-assigned titles. CLI accepts more, but UI legibility
 * (TaskBoard cards, terminal title bar) breaks past ~200 chars. */
const TITLE_MAX_LENGTH = 200;

export function createExternalRoutes(args: {
  store: SdkSessionsStore;
  watcher: SessionWatcher;
  /**
   * Section 02 (iterate 3) — validates projectId on PATCH / POST. Returns
   * the set of non-synthesized project ids currently known to the server.
   * The reserved UNASSIGNED_PROJECT_ID sentinel is accepted independently
   * of this set. Omitted in legacy callers — PATCH projectId support is
   * gated on presence (iterate-2 callers still work without it, and the
   * route returns 400 "projectId not supported" if a client sends one
   * without wiring).
   */
  getKnownProjectIds?: () => Set<string>;
}) {
  const app = new Hono();
  const { store, watcher, getKnownProjectIds } = args;

  app.post("/api/external/tasks", async (c) => {
    const body = await c.req.json().catch(() => ({}));
    const title = typeof body.title === "string" && body.title.trim()
      ? body.title.trim()
      : "Untitled task";
    const cwd = typeof body.cwd === "string" && body.cwd.trim()
      ? body.cwd.trim()
      : process.cwd();
    const pluginDirs = Array.isArray(body.pluginDirs)
      ? body.pluginDirs.filter((p: unknown): p is string => typeof p === "string")
      : [];
    // Section 02 (iterate 3) — allow callers to pass an explicit projectId
    // at creation. Defaults to UNASSIGNED_PROJECT_ID via the store. Invalid
    // ids are rejected symmetrically with PATCH so the TaskBoard inline
    // form can't leak a stale project id from a deleted project.
    let projectId: string | undefined;
    if (typeof body.projectId === "string" && body.projectId.trim()) {
      const candidate = body.projectId.trim();
      const validation = validateProjectIdOrError(candidate, getKnownProjectIds);
      if (validation) return c.json(validation, 400);
      projectId = candidate;
    }
    const task = store.create({ title, cwd, pluginDirs, projectId });
    await store.persist();
    return c.json({ task });
  });

  app.get("/api/external/tasks", (c) => {
    // Section 02 — optional ?projectId=<id> filter. Unvalidated on read
    // (unknown id → empty list, not 400) because an orphaned URL from a
    // deleted project is a benign state, not a user error. The reserved
    // "unassigned" literal is a valid filter value for the synthesized
    // bucket.
    const filter = c.req.query("projectId");
    const all = store.list();
    const tasks = filter ? all.filter((t) => t.projectId === filter) : all;
    return c.json({ tasks });
  });

  app.get("/api/external/tasks/:id", (c) => {
    const task = store.get(c.req.param("id"));
    if (!task) return c.json({ error: "Task not found" }, 404);
    return c.json({ task });
  });

  app.post("/api/external/tasks/:id/launch", async (c) => {
    const body = await c.req.json().catch(() => ({}));
    const resume = Boolean(body.resume);
    const task = store.get(c.req.param("id"));
    if (!task) return c.json({ error: "Task not found" }, 404);
    const commands = buildCopyCommands({
      sessionUuid: task.sessionUuid,
      cwd: task.cwd,
      resume,
      pluginDirs: task.pluginDirs,
      title: task.title,
    });
    const updated = store.patch(task.taskId, {
      state: "awaiting_external_start",
      launchedAt: new Date().toISOString(),
    });
    await store.persist();
    return c.json({ task: updated, commands });
  });

  /**
   * Patch a task. Title is the source of truth for the next launch's
   * `--name` flag (Claude's CLI picker title). Section 02 (iterate 3)
   * extends the body to accept `{projectId}` independently of title —
   * at least one of the two must be present.
   *
   * Concurrent writers from multiple tabs are serialized by
   * `proper-lockfile` inside the store's persist() call; on lock
   * contention we surface 409 so the client can retry instead of
   * overwriting silently.
   */
  app.patch("/api/external/tasks/:id", async (c) => {
    const body = await c.req.json().catch(() => ({}));
    const task = store.get(c.req.param("id"));
    if (!task) return c.json({ error: "Task not found" }, 404);

    const hasTitle = typeof body.title === "string";
    const hasProjectId = typeof body.projectId === "string";

    if (!hasTitle && !hasProjectId) {
      return c.json({ error: "at_least_one_field_required" }, 400);
    }

    const patch: Partial<ExternalTask> = {};

    if (hasTitle) {
      if (/[\r\n]/.test(body.title)) {
        return c.json({ error: "title cannot contain newlines" }, 400);
      }
      const trimmed = body.title.trim();
      if (trimmed.length === 0) {
        return c.json({ error: "title cannot be empty" }, 400);
      }
      if (trimmed.length > TITLE_MAX_LENGTH) {
        return c.json({ error: `title exceeds ${TITLE_MAX_LENGTH} characters` }, 400);
      }
      patch.title = trimmed;
    }

    if (hasProjectId) {
      const candidate = body.projectId.trim();
      if (candidate === "") {
        return c.json({ error: "projectId cannot be empty" }, 400);
      }
      const validation = validateProjectIdOrError(candidate, getKnownProjectIds);
      if (validation) return c.json(validation, 400);
      patch.projectId = candidate;
    }

    store.patch(task.taskId, patch);
    try {
      await store.persist();
    } catch (err) {
      if ((err as NodeJS.ErrnoException)?.code === "ELOCKED") {
        return c.json({ error: "sdk-sessions.json is locked, retry" }, 409);
      }
      throw err;
    }
    return c.json({ task: store.get(task.taskId) });
  });

  app.post("/api/external/tasks/:id/fork", async (c) => {
    const parent = store.get(c.req.param("id"));
    if (!parent) return c.json({ error: "Parent task not found" }, 404);
    const body = await c.req.json().catch(() => ({}));
    const title = typeof body.title === "string" && body.title.trim()
      ? body.title.trim()
      : `${parent.title} — fork`;
    const child = store.create({
      title,
      cwd: parent.cwd,
      pluginDirs: parent.pluginDirs,
      parentTaskId: parent.taskId,
      parentSessionUuid: parent.sessionUuid,
      // Section 02 — forks inherit the parent's projectId. Falls through to
      // UNASSIGNED_PROJECT_ID via the store's default when the parent is a
      // legacy v1 task that has already been backfilled.
      projectId: parent.projectId,
    });
    const commands = buildCopyCommands({
      sessionUuid: child.sessionUuid,
      cwd: child.cwd,
      fork: true,
      parentSessionUuid: parent.sessionUuid,
      pluginDirs: child.pluginDirs,
      title: child.title,
    });
    store.patch(child.taskId, {
      state: "awaiting_external_start",
      launchedAt: new Date().toISOString(),
    });
    await store.persist();
    return c.json({ task: store.get(child.taskId), commands });
  });

  app.get("/api/external/tasks/:id/transcript", async (c) => {
    const task = store.get(c.req.param("id"));
    if (!task) return c.json({ error: "Task not found" }, 404);

    const fromByte = parseIntSafe(c.req.query("fromByte"), 0);
    const expectFingerprint = c.req.query("expectFingerprint") ?? null;

    const result = await watcher.readChunk({
      sessionUuid: task.sessionUuid,
      fromByte,
      expectFingerprint,
    });

    // Apply state-machine transitions based on probe outcome + mtime.
    if (result.status === "missing") {
      if (task.firstJsonlObservedAt && task.state !== "jsonl_missing") {
        store.patch(task.taskId, { state: "jsonl_missing" });
        await store.persist();
      }
      return c.json({ status: "missing", task: store.get(task.taskId) });
    }

    if (result.status === "rotated") {
      return c.json({
        status: "rotated",
        task,
        currentFingerprint: result.currentFingerprint,
      });
    }

    const now = Date.now();
    const loc = await watcher.findByUuid(task.sessionUuid);
    const mtime = loc?.mtimeMs ?? 0;

    const patch: Partial<ExternalTask> = { lastJsonlSeenMtimeMs: mtime };
    let nextState: ExternalTaskState = task.state;
    if (!task.firstJsonlObservedAt) {
      nextState = "active";
      patch.firstJsonlObservedAt = new Date().toISOString();
    } else if (task.state === "jsonl_missing") {
      nextState = "active";
    } else if (task.state === "active" && now - mtime > ACTIVE_IDLE_THRESHOLD_MS) {
      nextState = "idle";
    } else if (task.state === "idle" && now - mtime <= IDLE_REACTIVATE_THRESHOLD_MS) {
      nextState = "active";
    }
    if (nextState !== task.state) {
      patch.state = nextState;
    }
    store.patch(task.taskId, patch);
    await store.persist();

    return c.json({
      status: "ok",
      chunk: result.chunk,
      task: store.get(task.taskId),
    });
  });

  app.get("/api/external/inbox", async (c) => {
    // Aggregate inbox across all tracked tasks. Re-derive each time —
    // the fastpath (incremental via lastProcessedByteOffset) is Sub-iterate
    // 1.5 work if latency on large transcripts proves painful.
    type AggregatedEntry = {
      taskId: string;
      sessionUuid: string;
      taskTitle: string;
      toolUseId: string;
      toolName: string;
      input: unknown;
      bestEffort: true;
    };
    const out: AggregatedEntry[] = [];
    for (const task of store.list()) {
      // Skip tasks the user has explicitly closed or whose session is
      // unrecoverable — they cannot grow new pending interactions, and
      // re-reading their JSONL is a major contributor to inbox latency
      // when sdk-sessions.json accumulates many stale entries.
      if (task.state === "done" || task.state === "launch_failed") continue;
      const loc = await watcher.findByUuid(task.sessionUuid);
      if (!loc) continue;
      let content = "";
      try {
        const chunk = await watcher.readChunk({
          sessionUuid: task.sessionUuid,
          fromByte: 0,
          expectFingerprint: null,
        });
        if (chunk.status === "ok") content = chunk.chunk.content;
      } catch {
        continue;
      }
      const parsed = parseSessionJsonl(content);
      const result = deriveInbox({
        events: parsed.events,
        allowlist: DEFAULT_USER_BLOCKING_TOOLS,
        dismissed: new Set(task.inbox.dismissedToolUseIds),
      });
      for (const e of result.pending) {
        out.push({
          taskId: task.taskId,
          sessionUuid: task.sessionUuid,
          taskTitle: task.title,
          toolUseId: e.toolUseId,
          toolName: e.toolName,
          input: e.input,
          bestEffort: true,
        });
      }
      // Persist the observed pending set so the next restart doesn't
      // re-derive from scratch for UI latency.
      const nextPending = result.pending.map((e) => e.toolUseId);
      if (
        nextPending.join(",") !== task.inbox.pendingToolUseIds.join(",") ||
        task.inbox.lastProcessedByteOffset !== content.length
      ) {
        store.patch(task.taskId, {
          inbox: {
            pendingToolUseIds: nextPending,
            dismissedToolUseIds: task.inbox.dismissedToolUseIds,
            lastProcessedByteOffset: content.length,
          },
        });
      }
    }
    await store.persist();
    return c.json({ items: out });
  });

  app.post("/api/external/inbox/:toolUseId/dismiss", async (c) => {
    const toolUseId = c.req.param("toolUseId");
    for (const task of store.list()) {
      if (!task.inbox.pendingToolUseIds.includes(toolUseId)) continue;
      const dismissed = new Set(task.inbox.dismissedToolUseIds);
      dismissed.add(toolUseId);
      store.patch(task.taskId, {
        inbox: {
          pendingToolUseIds: task.inbox.pendingToolUseIds.filter((id) => id !== toolUseId),
          dismissedToolUseIds: Array.from(dismissed),
          lastProcessedByteOffset: task.inbox.lastProcessedByteOffset,
        },
      });
      await store.persist();
      return c.json({ ok: true, taskId: task.taskId });
    }
    return c.json({ ok: false, error: "toolUseId not found in any pending set" }, 404);
  });

  app.post("/api/external/tasks/:id/close", async (c) => {
    const task = store.get(c.req.param("id"));
    if (!task) return c.json({ error: "Task not found" }, 404);
    const updated = store.patch(task.taskId, { state: "done" });
    await store.persist();
    return c.json({ task: updated });
  });

  app.delete("/api/external/tasks/:id", async (c) => {
    const deleted = store.delete(c.req.param("id"));
    if (!deleted) return c.json({ error: "Task not found" }, 404);
    await store.persist();
    return c.json({ ok: true });
  });

  return app;
}

function parseIntSafe(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

/**
 * Section 02 (iterate 3) — projectId validation.
 *
 * Returns a structured error body on rejection, or null when the id is
 * acceptable. The reserved UNASSIGNED_PROJECT_ID sentinel is always
 * valid (represents the synthesized bucket). If `getKnownProjectIds`
 * is not wired, every non-sentinel id is rejected — the route demands
 * explicit validation so a misconfigured server can't silently accept
 * arbitrary strings.
 */
function validateProjectIdOrError(
  candidate: string,
  getKnownProjectIds: (() => Set<string>) | undefined,
): { error: string; projectId: string } | null {
  if (candidate === UNASSIGNED_PROJECT_ID) return null;
  const known = getKnownProjectIds?.();
  if (!known || !known.has(candidate)) {
    return { error: "unknown_project_id", projectId: candidate };
  }
  return null;
}
