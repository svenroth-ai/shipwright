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
import {
  existsSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
} from "node:fs";
import { readdir, stat } from "node:fs/promises";
import { join, extname, basename } from "node:path";

import { buildCopyCommands } from "../core/launcher.js";
import { pathGuard, realPathGuard } from "../core/path-guard.js";
import { loadIgnore } from "../core/gitignore-cache.js";
import {
  buildExternalLaunchCommand,
  InvalidPlaceholderError,
  UnknownPhaseError,
  type SubstitutionContext,
} from "../core/actions-substitute.js";
import { loadActionsForProject } from "../core/project-actions-loader.js";
import {
  validateActionsSchema,
  type SchemaError,
} from "../core/actions-schema-validator.js";
import {
  PreviewExitedEarlyError,
  PreviewPortInUseError,
  PreviewProfileInvalidError,
  PreviewSessionManager,
  PreviewSpawnFailedError,
  PreviewTimeoutError,
  type PreviewProfile,
} from "../core/preview-session-manager.js";
import { loadProfile, getProfilesDir } from "../core/profile-loader.js";
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

/*
 * Iterate 3 remediation — Phase A4 (BUG 3 fix, 2026-04-20).
 *
 * `/api/external/inbox` used to re-parse the entire JSONL for every
 * tracked task on every request (9–10 s latency against 216 sessions
 * observed in UAT). The cache below memoizes the derived pending set
 * keyed by `(sessionUuid, mtimeMs, dismissedKey, contentLength)`.
 *
 * - mtimeMs change (new events written) busts the cache naturally.
 * - dismissedKey busts the cache when the user dismisses an entry so
 *   the next inbox call reflects the reduced pending set.
 * - contentLength captures the `lastProcessedByteOffset` we persist to
 *   the store, so callers see a coherent pair.
 *
 * Pattern mirrors `core/project-actions-loader.ts:52-68`. No explicit
 * invalidation needed; the key tuple naturally covers all cases.
 */
interface InboxDeriveCacheEntry {
  /** Resolved on-disk path — lets us `stat()` directly on warm calls
   *  instead of rescanning every subdir of ~/.claude/projects via
   *  findByUuid (the actual hot-spot — the JSONL parse is cheap by
   *  comparison). Falls back to findByUuid on stat failure. */
  resolvedPath: string;
  mtimeMs: number;
  contentLength: number;
  dismissedKey: string;
  entries: Array<{
    toolUseId: string;
    toolName: string;
    input: unknown;
    taskTitle: string;
  }>;
  pendingIds: string[];
}
const inboxDeriveCache = new Map<string, InboxDeriveCacheEntry>();

/**
 * Negative-result cache for `findByUuid` misses (Phase A4). Sessions
 * that haven't materialized on disk yet (e.g. `awaiting_external_start`
 * tasks where the user hasn't pasted the launch command) previously
 * triggered a full readdir scan across every subdirectory of
 * `~/.claude/projects` on EVERY inbox call — the dominant latency
 * source (60+ sessions × 216 subdir scans).
 *
 * With a short TTL we skip the scan for sessions we recently confirmed
 * don't exist. The TTL is intentionally short so launch → discovery
 * still converges quickly (~15 s worst case).
 */
const NEGATIVE_RESULT_TTL_MS = 15_000;
const inboxNegativeCache = new Map<string, number>();

/** Test helper — drops the per-session inbox caches. */
export function clearInboxDeriveCache(): void {
  inboxDeriveCache.clear();
  inboxNegativeCache.clear();
}

/** Hard cap on user-assigned titles. CLI accepts more, but UI legibility
 * (TaskBoard cards, terminal title bar) breaks past ~200 chars. */
const TITLE_MAX_LENGTH = 200;

export interface ExternalRouteProjectView {
  id: string;
  name: string;
  path: string;
  profile?: string;
  synthesized?: boolean;
  settings?: { color?: string };
}

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
  /**
   * Section 03 (iterate 3) — look up a registered project by id. Used by
   * GET /projects/:id/actions + POST /projects/:id/preview +
   * POST /projects/:id/actions-stub. The synthesized "unassigned" row is
   * NOT returned from here (it has no filesystem path).
   */
  getProjectById?: (id: string) => ExternalRouteProjectView | undefined;
  /**
   * Section 03 — preview-session manager instance, shared across requests
   * so the dedup cache holds between POSTs. Injected by index.ts;
   * test harnesses can pass a fresh instance per test.
   */
  previewManager?: PreviewSessionManager;
  /**
   * Section 03 — loads a profile by name. Defaults to the real
   * `core/profile-loader.ts` entry; tests inject a synthetic profile.
   */
  loadProfile?: (profileName: string) => PreviewProfile | null;
}) {
  const app = new Hono();
  const {
    store,
    watcher,
    getKnownProjectIds,
    getProjectById,
    previewManager,
    loadProfile: injectedLoadProfile,
  } = args;
  const profileResolver =
    injectedLoadProfile ??
    ((name: string) => loadProfile(name, getProfilesDir()) as PreviewProfile | null);

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

    // Section 03 (iterate 3) — O20 idempotency guard.
    //
    // The spec language "state ∈ {pending, backlog}" loosely maps to our
    // enum's `draft` + `awaiting_external_start` + `launch_failed`. The
    // intent is: reject re-launches against a TERMINAL state (done). The
    // existing Resume / Fork flows (LaunchRow) already call this route
    // against `active` and `idle` — the `resume: true` branch emits a new
    // copy-command to pick up where the user left off, which is a valid
    // re-launch. We therefore reject ONLY `done` and `launch_failed`
    // when no explicit resume intent is present.
    //
    // Note: `launch_failed` is accepted (the user is retrying after a
    // clipboard hiccup). `done` is terminal — closing a task is an
    // explicit user action and a re-launch after close is almost always
    // unintended.
    if (task.state === "done") {
      return c.json(
        { error: "launch_invalid_state", state: task.state },
        409,
      );
    }

    // Description + autonomy flow through buildCopyCommands as the
    // `title` already did. For iterate 3.3b we keep the existing three-
    // form output intact (launch still emits --session-id / --name /
    // --plugin-dir via the legacy path). Future iterate can switch this
    // to buildExternalLaunchCommand once the NewIssueModal can carry the
    // full SubstitutionContext. Today, description / autonomy on the
    // body are forwarded as metadata for the ExternalTask record so the
    // Task Detail surface can render them, but do not mutate the copy-
    // command shape (to keep spec 30/36 green).
    const description =
      typeof body.description === "string" ? body.description : undefined;
    const autonomy =
      body.autonomy === "autonomous" || body.autonomy === "guided"
        ? (body.autonomy as "autonomous" | "guided")
        : undefined;
    void description; // reserved for future NewIssueModal → launch wiring
    void autonomy;

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
    // Aggregate inbox across all tracked tasks. Phase A4 (iterate 3
    // remediation, 2026-04-20): per-session derive cache keyed by
    // (sessionUuid, mtimeMs, dismissedKey, contentLength). Cold call
    // still does the full scan; warm calls (no new events, no new
    // dismissals) short-circuit to the cached entries array. Mirrors
    // the mtime-cache pattern in `core/project-actions-loader.ts`.
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
    let storeDirty = false;
    for (const task of store.list()) {
      // Skip tasks the user has explicitly closed or whose session is
      // unrecoverable — they cannot grow new pending interactions, and
      // re-reading their JSONL is a major contributor to inbox latency
      // when sdk-sessions.json accumulates many stale entries.
      if (task.state === "done" || task.state === "launch_failed") continue;

      const dismissedKey = task.inbox.dismissedToolUseIds.slice().sort().join(",");
      const cached = inboxDeriveCache.get(task.sessionUuid);

      // Warm-path fastpath (Phase A4): avoid the full
      // `findByUuid` readdir scan over every subdir of
      // ~/.claude/projects by stat-ing the previously resolved path
      // directly. If mtime is unchanged AND dismissed set is
      // unchanged, reuse the cached entries and skip all I/O past
      // the single stat call.
      if (cached) {
        let currentMtime: number | null = null;
        try {
          const s = await stat(cached.resolvedPath);
          currentMtime = s.mtimeMs;
        } catch {
          // File moved/rotated — fall through to cold path below.
          currentMtime = null;
        }
        if (
          currentMtime !== null &&
          currentMtime === cached.mtimeMs &&
          cached.dismissedKey === dismissedKey
        ) {
          for (const e of cached.entries) {
            out.push({
              taskId: task.taskId,
              sessionUuid: task.sessionUuid,
              taskTitle: e.taskTitle,
              toolUseId: e.toolUseId,
              toolName: e.toolName,
              input: e.input,
              bestEffort: true,
            });
          }
          continue;
        }
      }

      // Cold path — either no cache entry, or the cached mtime is
      // stale, or the cached file is gone. Do the full scan.
      //
      // Phase A4 (iterate 3 remediation) — skip the scan if we very
      // recently confirmed no file exists for this session
      // (`awaiting_external_start` tasks pre-launch). Short TTL so
      // launch → discovery still converges fast.
      const negUntil = inboxNegativeCache.get(task.sessionUuid);
      const nowMs = Date.now();
      if (negUntil !== undefined && negUntil > nowMs) continue;

      const loc = await watcher.findByUuid(task.sessionUuid);
      if (!loc) {
        inboxNegativeCache.set(task.sessionUuid, nowMs + NEGATIVE_RESULT_TTL_MS);
        continue;
      }
      // Session materialized — bust any stale negative entry.
      inboxNegativeCache.delete(task.sessionUuid);

      // Cold / stale — re-read + re-derive.
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
      const cacheEntries: InboxDeriveCacheEntry["entries"] = [];
      for (const e of result.pending) {
        cacheEntries.push({
          toolUseId: e.toolUseId,
          toolName: e.toolName,
          input: e.input,
          taskTitle: task.title,
        });
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
        storeDirty = true;
      }

      inboxDeriveCache.set(task.sessionUuid, {
        resolvedPath: loc.path,
        mtimeMs: loc.mtimeMs,
        contentLength: content.length,
        dismissedKey,
        entries: cacheEntries,
        pendingIds: nextPending,
      });
    }
    if (storeDirty) await store.persist();
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
      // Phase A4 — bust the derive cache for this session so the next
      // GET /inbox call reflects the reduced pending set immediately.
      // (The cache key includes dismissedKey so this is belt-and-braces,
      // but the explicit delete guarantees no stale object sticks
      // around even if the sort-order ever drifts.)
      inboxDeriveCache.delete(task.sessionUuid);
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

  // -------------------------------------------------------------------------
  // Section 03 (iterate 3) — project-scoped actions / preview routes.
  //
  // These live on the SAME Hono app as the /tasks routes because they share
  // the same middleware chain (CORS, auth eventually). They are NOT nested
  // under /tasks — they operate on projects.
  // -------------------------------------------------------------------------

  /**
   * GET /api/external/projects/:projectId/actions — resolved actions schema
   * for the project. Falls back to the bundled default when .webui/actions.json
   * is absent; returns diagnostics in-band when the user file exists but is
   * malformed (O24 chip). Validates every command_template via the substitute
   * dry-run; unknown placeholder → 400 with typed code.
   */
  app.get("/api/external/projects/:projectId/actions", (c) => {
    const projectId = c.req.param("projectId");
    const project = getProjectById?.(projectId);
    if (!project) {
      return c.json({ error: "project_not_found", projectId }, 404);
    }

    const loaded = loadActionsForProject(project.path || "");
    const actions = loaded.actions;

    // Structural validation (5 O24 cases).
    const schemaErrors: SchemaError[] = validateActionsSchema(actions);
    if (schemaErrors.length > 0) {
      // Prefer the first hard schema error as the 400 code — the UI needs
      // one actionable message. All errors are surfaced in `errors[]` for
      // debugging.
      const first = schemaErrors[0];
      return c.json(
        {
          error: first.code,
          errors: schemaErrors,
          projectId,
        },
        400,
      );
    }

    // Placeholder-level dry-run validation per action template.
    for (const a of actions.actions) {
      if (!a.command_template) continue;
      const phaseIds = actions.phases.map((p) => p.id);
      try {
        // Build a throwaway substitution context and attempt all three
        // shell forms. validateTemplate() returns only placeholder errors;
        // anything else we let bubble up as a 500 (bug).
        const errCandidate = dryRunTemplate(a.command_template, a.id, phaseIds);
        if (errCandidate) {
          return c.json(
            {
              error: "invalid_placeholder",
              placeholder: errCandidate.placeholder,
              actionId: errCandidate.actionId,
              template: errCandidate.template,
            },
            400,
          );
        }
      } catch {
        // Defense-in-depth: a crashing template validator should fail
        // the route rather than expose the raw stack trace.
        return c.json(
          { error: "template_validation_failed", actionId: a.id },
          500,
        );
      }
    }

    // Resolve preview.enabled per plan.md § 2.1 precedence:
    //   Step 1 — profile.stack.frontend present AND dev_server.command
    //            present → true unless explicitly disabled below.
    //   Step 2 — actions.preview.enabled:
    //            "auto" → follow Step 1.
    //            true   → only honored if Step 1 also allowed it (profile gate wins).
    //            false  → force off regardless.
    const profile = project.profile
      ? (profileResolver(project.profile) as
          | (PreviewProfile & { stack?: { frontend?: unknown } })
          | null)
      : null;
    const profileAllowsPreview =
      Boolean(profile?.stack?.frontend) &&
      Boolean(profile?.dev_server?.command);
    const actionsPref = actions.preview?.enabled;
    let previewEnabled: boolean;
    if (actionsPref === false) {
      previewEnabled = false;
    } else if (actionsPref === true) {
      previewEnabled = profileAllowsPreview;
    } else {
      // "auto" or undefined — follow profile.
      previewEnabled = profileAllowsPreview;
    }

    return c.json({
      actions: actions.actions,
      phases: actions.phases,
      defaults: actions.defaults,
      preview: {
        enabled: previewEnabled,
        command: profile?.dev_server?.command ?? null,
        port: profile?.dev_server?.port ?? null,
        ready_path: profile?.dev_server?.ready_path ?? null,
        ready_timeout_seconds: profile?.dev_server?.ready_timeout_seconds ?? null,
      },
      diagnostics: loaded.diagnostics,
    });
  });

  /**
   * POST /api/external/projects/:projectId/preview — spawn dev server.
   *
   * Structured error codes — the UI maps each to a specific toast:
   *   preview_profile_invalid  (400) — command contains shell operators / empty
   *   preview_spawn_failed     (500) — spawn threw (ENOENT etc.)
   *   preview_port_in_use      (500) — port probe reported EADDRINUSE
   *   preview_exited_early     (500) — child emitted exit before ready
   *   preview_timeout          (500) — no ready signal within timeout
   */
  app.post("/api/external/projects/:projectId/preview", async (c) => {
    if (!previewManager) {
      return c.json({ error: "preview_unavailable" }, 501);
    }
    const projectId = c.req.param("projectId");
    const project = getProjectById?.(projectId);
    if (!project) {
      return c.json({ error: "project_not_found", projectId }, 404);
    }
    if (!project.profile) {
      return c.json(
        { error: "preview_profile_invalid", detail: "project has no profile" },
        400,
      );
    }
    const profile = profileResolver(project.profile);
    if (!profile) {
      return c.json(
        { error: "preview_profile_invalid", detail: "profile not found" },
        400,
      );
    }
    try {
      const entry = await previewManager.spawn(projectId, profile, {
        cwd: project.path,
      });
      return c.json({ url: entry.url, sessionId: entry.sessionId });
    } catch (err) {
      if (err instanceof PreviewProfileInvalidError) {
        return c.json(
          { error: "preview_profile_invalid", detail: err.detail },
          400,
        );
      }
      if (err instanceof PreviewPortInUseError) {
        return c.json(
          { error: "preview_port_in_use", port: err.port },
          500,
        );
      }
      if (err instanceof PreviewSpawnFailedError) {
        return c.json(
          { error: "preview_spawn_failed", detail: err.detail },
          500,
        );
      }
      if (err instanceof PreviewExitedEarlyError) {
        return c.json(
          { error: "preview_exited_early", detail: `exited with code ${err.code}` },
          500,
        );
      }
      if (err instanceof PreviewTimeoutError) {
        return c.json(
          { error: "preview_timeout", seconds: err.seconds },
          500,
        );
      }
      // Unknown failure — bubble as a generic 500 so a bug doesn't masquerade
      // as one of the expected codes.
      return c.json(
        { error: "preview_unknown_error", detail: String(err).slice(0, 200) },
        500,
      );
    }
  });

  // -------------------------------------------------------------------------
  // Section 04a — Tree + File routes for SmartViewer / FolderTree.
  //
  // Security surface:
  //   - path-guard.ts refuses traversal / absolute-input / drive-hop attempts
  //   - file route enforces 5 MB cap (413) and image-allowlist (415)
  //   - file route sets explicit Content-Type + nosniff + sanitized
  //     Content-Disposition to block MIME-sniffing + header-injection
  // -------------------------------------------------------------------------

  /**
   * GET /api/external/projects/:projectId/tree?path=<relpath>
   *
   * Returns one level of entries. `ignored: true` is advisory — the client
   * decides whether to show them muted or hide them entirely (plan § 7 O6).
   */
  app.get("/api/external/projects/:projectId/tree", async (c) => {
    const projectId = c.req.param("projectId");
    const project = getProjectById?.(projectId);
    if (!project) {
      return c.json({ error: "project_not_found", projectId }, 404);
    }
    if (!project.path) {
      return c.json({ error: "project_path_unavailable", projectId }, 400);
    }

    const relpath = c.req.query("path") ?? "";
    const guard = pathGuard(project.path, relpath);
    if (!guard.ok) {
      // Normalize guard reasons to a single client-facing error code for
      // consistency: both "absolute_input" and "drive_change" surface as
      // "path_traversal" — the UI doesn't distinguish and we avoid leaking
      // internal-guard semantics. The `detail` field preserves the precise
      // reason for server logs.
      const err = guard.reason === "traversal" ? "path_traversal" : guard.reason;
      return c.json({ error: err, detail: guard.reason }, 400);
    }

    const ig = loadIgnore(project.path);

    // Build the subpath prefix relative to project.path for ignore lookups.
    // If the caller requested "src", an entry "index.ts" should be tested
    // against "src/index.ts" so that a .gitignore rule like "src/index.ts"
    // matches. We always use POSIX separators for ignore() — the `ignore`
    // package documents that.
    const subPrefix = relpath.length > 0 && relpath !== "."
      ? relpath.replace(/\\/g, "/").replace(/\/+$/, "")
      : "";

    let entries;
    try {
      entries = await readdir(guard.absolute, { withFileTypes: true });
    } catch (err) {
      const code = (err as NodeJS.ErrnoException)?.code;
      if (code === "ENOENT") {
        return c.json({ error: "not_found", path: relpath }, 404);
      }
      if (code === "ENOTDIR") {
        return c.json({ error: "not_a_directory", path: relpath }, 400);
      }
      return c.json(
        { error: "tree_read_failed", detail: String(err).slice(0, 200) },
        500,
      );
    }

    // Symlink-escape check — only when the caller requested a subdirectory
    // (the project root itself is trusted; it's where the user pointed us).
    // For any non-empty relpath we realpath + re-verify. A symlinked-dir
    // escape attempt lands here, NOT in pathGuard (which is string-only).
    if (relpath.length > 0 && relpath !== ".") {
      const realGuard = realPathGuard(project.path, guard.absolute);
      if (!realGuard.ok) {
        return c.json(
          { error: "path_traversal", detail: realGuard.reason },
          400,
        );
      }
    }

    const out = entries.map((d) => {
      const kind: "file" | "dir" = d.isDirectory() ? "dir" : "file";
      // `ignore` requires a relative path. It treats trailing slashes as a
      // directory hint, which affects pattern semantics.
      const testPathBase = subPrefix ? `${subPrefix}/${d.name}` : d.name;
      const testPath = kind === "dir" ? `${testPathBase}/` : testPathBase;
      const ignored = ig.ignores(testPath) || ig.ignores(testPathBase);
      return { name: d.name, kind, ignored };
    });

    // Stable sort — dirs first, then alpha. Keeps the UI deterministic.
    out.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "dir" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

    return c.json({ entries: out });
  });

  /**
   * GET /api/external/projects/:projectId/file?path=<relpath>
   *
   * Byte-streams the file with:
   *   - X-Content-Type-Options: nosniff
   *   - Explicit Content-Type per extension (never inferred)
   *   - Content-Disposition: inline; filename="<sanitized>"
   *
   * 400 on traversal / absolute input. 413 if > 5 MB. 415 if extension not
   * in the text/markdown/image allowlist.
   */
  app.get("/api/external/projects/:projectId/file", async (c) => {
    const projectId = c.req.param("projectId");
    const project = getProjectById?.(projectId);
    if (!project) {
      return c.json({ error: "project_not_found", projectId }, 404);
    }
    if (!project.path) {
      return c.json({ error: "project_path_unavailable", projectId }, 400);
    }

    const relpath = c.req.query("path");
    if (!relpath || relpath.length === 0) {
      return c.json({ error: "path_required" }, 400);
    }
    const guard = pathGuard(project.path, relpath);
    if (!guard.ok) {
      const err = guard.reason === "traversal" ? "path_traversal" : guard.reason;
      return c.json({ error: err, detail: guard.reason }, 400);
    }

    let st;
    try {
      st = await stat(guard.absolute);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException)?.code;
      if (code === "ENOENT") {
        return c.json({ error: "not_found", path: relpath }, 404);
      }
      return c.json(
        { error: "file_stat_failed", detail: String(err).slice(0, 200) },
        500,
      );
    }

    if (!st.isFile()) {
      return c.json({ error: "not_a_file", path: relpath }, 400);
    }

    // Symlink-escape defense. The stat above already succeeded, so the
    // target exists — realpath will verify it's still under project root.
    // If the file is a symlink whose target is outside the root, reject.
    const realGuard = realPathGuard(project.path, guard.absolute);
    if (!realGuard.ok) {
      return c.json(
        { error: "path_traversal", detail: realGuard.reason },
        400,
      );
    }

    if (st.size > FILE_MAX_BYTES) {
      return c.json(
        { error: "file_too_large", maxBytes: FILE_MAX_BYTES, size: st.size },
        413,
      );
    }

    const rawExt = extname(guard.absolute).toLowerCase().slice(1);
    const mime = MIME_BY_EXTENSION[rawExt];
    if (!mime) {
      return c.json(
        {
          error: "binary_not_previewable",
          mime: `application/octet-stream`,
          extension: rawExt || null,
        },
        415,
      );
    }

    const filename = sanitizeContentDispositionFilename(basename(guard.absolute));

    // Read the full file into memory. This is safe because the 5 MB cap is
    // already enforced above — no file larger than 5 MB reaches this point.
    // We avoid streaming here to dodge a race in test teardown (where the
    // file disappears before the node-readable has finished draining into
    // the web-response) AND to make the Content-Length + body atomic — a
    // streamed response could race with a filesystem-level deletion and
    // produce a truncated body past the nosniff check.
    let body: Buffer;
    try {
      body = readFileSync(guard.absolute);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException)?.code;
      if (code === "ENOENT") {
        return c.json({ error: "not_found", path: relpath }, 404);
      }
      return c.json(
        { error: "file_read_failed", detail: String(err).slice(0, 200) },
        500,
      );
    }

    // Set security headers BEFORE sending body.
    c.header("Content-Type", mime);
    c.header("X-Content-Type-Options", "nosniff");
    c.header("Content-Disposition", `inline; filename="${filename}"`);
    c.header("Content-Length", String(body.length));
    c.header("Cache-Control", "private, max-age=0, must-revalidate");
    // Defense-in-depth for SVG (which CAN embed <script>): when an SVG is
    // loaded via <iframe> browsers WILL execute inline script. The CSP
    // header blocks that in every viewer. For non-SVG responses the CSP
    // is harmless. `default-src 'none'` also prevents sub-resource loads
    // (the SmartViewer image renderer uses <img src>, which is unaffected).
    c.header(
      "Content-Security-Policy",
      "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    );

    // Return the raw bytes. Hono wraps a Uint8Array into the Response body
    // as-is; Content-Type is NOT mutated (we set it above).
    return c.body(new Uint8Array(body));
  });

  /**
   * POST /api/projects/:id/actions-stub — create `<project.path>/.webui/actions.json`
   * as an empty structured stub. Only called from the wizard's "Custom"
   * branch; idempotent (second call is a no-op).
   *
   * This is the ONLY write webui performs inside a user's project path.
   */
  app.post("/api/projects/:id/actions-stub", (c) => {
    const id = c.req.param("id");
    const project = getProjectById?.(id);
    if (!project) {
      return c.json({ error: "project_not_found", projectId: id }, 404);
    }
    if (!project.path) {
      return c.json(
        { error: "project_path_unavailable", projectId: id },
        400,
      );
    }
    const dir = join(project.path, ".webui");
    const file = join(dir, "actions.json");
    try {
      if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
      if (!existsSync(file)) {
        const stub = {
          $schema:
            "https://shipwright.dev/schemas/actions.v1.json (see docs/actions.md)",
          schemaVersion: 1,
          defaults: { autonomy: "guided" },
          actions: [],
          phases: [],
          preview: { enabled: "auto" },
        };
        writeFileSync(file, JSON.stringify(stub, null, 2) + "\n", "utf-8");
      }
      return c.json({ path: file, created: true });
    } catch (err) {
      return c.json(
        {
          error: "stub_write_failed",
          detail: String(err).slice(0, 200),
          path: file,
        },
        500,
      );
    }
  });

  return app;
}

/**
 * Dry-run the substitute pipeline against a template using placeholder-
 * allowlist-safe values; returns the first placeholder failure, or null.
 * Shared between the GET /actions route and unit tests.
 */
function dryRunTemplate(
  template: string,
  actionId: string,
  phaseIds: string[],
): InvalidPlaceholderError | null {
  const ctx: SubstitutionContext = {
    project: { id: "dry-run", path: "/tmp/dry-run" },
    task: {
      uuid: "00000000-0000-0000-0000-000000000000",
      title: "dry run",
      phase: phaseIds[0] ?? "dry-run-phase",
      phase_label: "Dry Run",
    },
    pluginDirs: [],
    allowedPhaseIds: new Set([...phaseIds, "dry-run-phase"]),
    actionId,
  };
  try {
    buildExternalLaunchCommand({ template, ctx });
    return null;
  } catch (err) {
    if (err instanceof InvalidPlaceholderError) return err;
    if (err instanceof UnknownPhaseError) return null; // handled at launch time
    throw err;
  }
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

// ---------------------------------------------------------------------------
// Section 04a — helpers for the file route.
// ---------------------------------------------------------------------------

/** 5 MB — server-side cap per spec. Client applies a lower 1 MB cap for
 * text/markdown/code; images may use the full 5 MB budget. */
export const FILE_MAX_BYTES = 5 * 1024 * 1024;

/**
 * Explicit extension → Content-Type mapping. Any extension NOT in this table
 * is treated as "not previewable" and rejected with 415 from the file route.
 *
 * Security rationale:
 *   - Everything text-ish is served as text/plain (NOT application/javascript
 *     or text/typescript) so the browser can't be tricked into executing it
 *     even in a renderable-script context.
 *   - Markdown is served as text/markdown; charset=utf-8 — some browsers
 *     render it inline, but the nosniff header + Content-Disposition inline
 *     with explicit filename prevents auto-download shenanigans.
 *   - Image entries match the documented allowlist (png / jpg / jpeg / gif /
 *     svg / webp).
 */
export const MIME_BY_EXTENSION: Record<string, string> = Object.freeze({
  // Text-ish — all served as text/plain regardless of semantic type.
  txt: "text/plain; charset=utf-8",
  md: "text/markdown; charset=utf-8",
  markdown: "text/markdown; charset=utf-8",
  log: "text/plain; charset=utf-8",
  json: "text/plain; charset=utf-8",
  yaml: "text/plain; charset=utf-8",
  yml: "text/plain; charset=utf-8",
  toml: "text/plain; charset=utf-8",
  csv: "text/plain; charset=utf-8",
  xml: "text/plain; charset=utf-8",
  html: "text/plain; charset=utf-8",
  css: "text/plain; charset=utf-8",
  js: "text/plain; charset=utf-8",
  jsx: "text/plain; charset=utf-8",
  ts: "text/plain; charset=utf-8",
  tsx: "text/plain; charset=utf-8",
  mjs: "text/plain; charset=utf-8",
  cjs: "text/plain; charset=utf-8",
  sh: "text/plain; charset=utf-8",
  bash: "text/plain; charset=utf-8",
  zsh: "text/plain; charset=utf-8",
  py: "text/plain; charset=utf-8",
  rb: "text/plain; charset=utf-8",
  go: "text/plain; charset=utf-8",
  rs: "text/plain; charset=utf-8",
  java: "text/plain; charset=utf-8",
  kt: "text/plain; charset=utf-8",
  swift: "text/plain; charset=utf-8",
  c: "text/plain; charset=utf-8",
  h: "text/plain; charset=utf-8",
  cpp: "text/plain; charset=utf-8",
  hpp: "text/plain; charset=utf-8",
  sql: "text/plain; charset=utf-8",
  env: "text/plain; charset=utf-8",
  gitignore: "text/plain; charset=utf-8",
  dockerfile: "text/plain; charset=utf-8",
  mmd: "text/plain; charset=utf-8",
  mermaid: "text/plain; charset=utf-8",
  // Image allowlist.
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  svg: "image/svg+xml",
  webp: "image/webp",
});

/**
 * Sanitize a filename for use inside `Content-Disposition: inline;
 * filename="<sanitized>"`.
 *
 * Contract:
 *   - ASCII alphanumerics + `. _ -` + spaces are preserved.
 *   - All other characters (including CR, LF, ", \, ;, non-ASCII) are
 *     replaced with `_`. This blocks header-injection via CR/LF, avoids
 *     the need for RFC 6266 percent-encoding, and produces a filename
 *     the client can safely render back.
 *   - Result is clamped to 120 characters. If the original was longer
 *     we preserve the extension when possible.
 *   - Empty result falls back to "file".
 *
 * This is intentionally MORE restrictive than RFC 6266 allows — the UI
 * only needs the filename as a hint; we prefer a conservative char class
 * over round-trip fidelity.
 */
export function sanitizeContentDispositionFilename(raw: string): string {
  const base = basename(raw || "").normalize("NFKC");
  if (base.length === 0) return "file";

  // Replace anything outside the allowed class with `_`.
  const cleaned = base.replace(/[^A-Za-z0-9._ -]/g, "_");

  if (cleaned.length === 0) return "file";
  if (cleaned.length <= 120) return cleaned;

  // Clamp to 120, preserving the extension if we can.
  const dot = cleaned.lastIndexOf(".");
  if (dot > 0 && cleaned.length - dot <= 16) {
    const ext = cleaned.slice(dot);
    const headLen = 120 - ext.length;
    return cleaned.slice(0, headLen) + ext;
  }
  return cleaned.slice(0, 120);
}
