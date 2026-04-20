/*
 * Shipwright Command Center — server entry.
 *
 * Plan D'' variant-a architecture (external-launch):
 *   - Webui owns no Claude subprocess, no SSE chat stream, no NDJSON parser.
 *   - User launches Claude Code in their own terminal via a pre-bound
 *     --session-id UUID (copy-command generator at core/launcher.ts).
 *   - Webui observes the JSONL at ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl
 *     via SessionWatcher + polling (core/session-watcher.ts).
 *   - Task metadata persisted at <registryDir>/sdk-sessions.json
 *     (core/sdk-sessions-store.ts).
 *
 * This file used to be 800+ LOC of chat/adapter/heartbeat wiring.
 * Sub-iterate 3 of Plan D'' trims it to ~100 LOC.
 */

import { Hono } from "hono";
import { cors } from "hono/cors";
import { serveStatic } from "@hono/node-server/serve-static";
import { serve } from "@hono/node-server";
import fs from "fs";
import { readFile, writeFile } from "fs/promises";
import * as lockfile from "proper-lockfile";

import { getConfig } from "./config.js";
import { errorHandler } from "./middleware/error-handler.js";
import { requestLogger } from "./middleware/logger.js";
import { ProjectManager } from "./core/project-manager.js";
import { SdkSessionsStore } from "./core/sdk-sessions-store.js";
import { SessionWatcher } from "./core/session-watcher.js";
import { probeClaudeVersion, type ClaudeVersionInfo } from "./core/cli-compat.js";
import { PreviewSessionManager } from "./core/preview-session-manager.js";
import {
  loadProfile as loadProfileReal,
  getProfilesDir,
} from "./core/profile-loader.js";

import { createProjectRoutes } from "./routes/projects.js";
import { createSettingsRoutes } from "./routes/settings.js";
import { createProfilesRoutes } from "./routes/profiles.js";
import { createExternalRoutes } from "./external/routes.js";
import { createDiagnosticsRoutes } from "./routes/diagnostics.js";

const config = getConfig();
const startTime = Date.now();

export const app = new Hono();

app.use(
  "*",
  cors({
    origin: (origin) => {
      if (origin && origin.includes("localhost")) return origin;
      return null;
    },
  }),
);
app.use("*", requestLogger);
app.onError(errorHandler);

app.get("/api/health", (c) =>
  c.json({
    status: "ok",
    version: "0.1.0",
    uptime: Math.floor((Date.now() - startTime) / 1000),
  }),
);

const isMainModule =
  typeof process !== "undefined" &&
  process.argv[1] &&
  (process.argv[1].endsWith("index.ts") || process.argv[1].endsWith("index.js"));

if (isMainModule) {
  void (async () => {
    try {
      const FATAL_ERROR_CODES = new Set(["EADDRINUSE", "EACCES", "EADDRNOTAVAIL"]);
      process.on("uncaughtException", (err) => {
        const code = (err as NodeJS.ErrnoException).code;
        if (code && FATAL_ERROR_CODES.has(code)) {
          console.error(
            JSON.stringify({
              level: "fatal",
              message: `Fatal startup error (${code}) — exiting so tsx watch can retry`,
              error: String(err),
              code,
            }),
          );
          process.exit(1);
        }
        console.error(
          JSON.stringify({
            level: "error",
            message: "Uncaught exception (server stays alive)",
            error: String(err),
            stack: err.stack,
          }),
        );
      });
      process.on("unhandledRejection", (reason) => {
        console.error(
          JSON.stringify({
            level: "error",
            message: "Unhandled rejection (server stays alive)",
            error: String(reason),
          }),
        );
      });

      // Shared cross-process lock + file-exists guard.
      const lockPath = async (p: string) => lockfile.lock(p, { retries: 3 });
      const ensureFileExists = (p: string) => {
        if (!fs.existsSync(p)) fs.writeFileSync(p, "");
      };

      // ProjectManager — still used by /api/projects + wizard.
      // getTaskProjectIds (section 02) is late-bound below, after the
      // sessionsStore is constructed.
      const projectManagerDeps: {
        readFile: (p: string, e: string) => Promise<string>;
        writeFile: (p: string, d: string) => Promise<void>;
        existsSync: (p: string) => boolean;
        mkdirSync: (p: string, o?: { recursive: boolean }) => void;
        readdirSync: (p: string, o?: { withFileTypes: boolean }) => Array<{ name: string; isDirectory: () => boolean }>;
        lock: (p: string) => Promise<() => Promise<void>>;
        ensureFile: (p: string) => void;
        getTaskProjectIds?: () => Set<string>;
      } = {
        readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
        writeFile: (p: string, d: string) => writeFile(p, d),
        existsSync: (p: string) => fs.existsSync(p),
        mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
        readdirSync: ((p: string, o?: { withFileTypes: boolean }) =>
          fs.readdirSync(p, o as unknown as { withFileTypes: true })) as (
          p: string,
          o?: { withFileTypes: boolean },
        ) => Array<{ name: string; isDirectory: () => boolean }>,
        lock: lockPath,
        ensureFile: ensureFileExists,
      };
      const projectManager = new ProjectManager(
        `${config.registryDir}/projects.json`,
        projectManagerDeps,
      );
      await projectManager.load();

      // External-launch store + watcher.
      //
      // Section 02 (iterate 3, ADR-037/038) — two cross-wirings:
      //   1. projectManager.getTaskProjectIds reads from sessionsStore so
      //      the Unassigned pseudo-project surfaces iff any task needs it.
      //   2. sdkSessionsStore.getKnownProjectIds reads from projectManager
      //      so stale projectIds on-disk (deleted projects, O26) resolve
      //      to UNASSIGNED in memory on load.
      //
      // The wiring order matters — projectManager loads first (sync
      // projects.json read) and the sessionsStore reads from it during
      // its own load(). The sessionsStore is created fresh above so we
      // pass a reference-equality callback that stays valid after both
      // stores finish loading.
      const sdkSessionsPath = `${config.registryDir}/sdk-sessions.json`;
      const sdkSessionsDeps = {
        readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
        writeFile: (p: string, d: string) => writeFile(p, d),
        existsSync: (p: string) => fs.existsSync(p),
        mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
        lock: lockPath,
        ensureFile: ensureFileExists,
        getKnownProjectIds: () => new Set(projectManager.getAll().filter((p) => !p.synthesized).map((p) => p.id)),
      };
      const sdkSessionsStore = new SdkSessionsStore(sdkSessionsPath, sdkSessionsDeps);
      await sdkSessionsStore.load();

      // Late-bind getTaskProjectIds on the already-constructed
      // projectManager — its deps shape is public (mutable fields), so we
      // append here rather than threading through constructor args above.
      (projectManager as unknown as { deps: { getTaskProjectIds: () => Set<string> } }).deps.getTaskProjectIds =
        () => new Set(sdkSessionsStore.list().map((t) => t.projectId));

      // Boot-time diagnostic (spec step 7). Logs once if any session
      // carries projectId="unassigned" while the on-disk file is still
      // schemaVersion: 1 — confirms the write-on-touch migration is
      // deferred as designed (ADR-038) rather than silently broken.
      try {
        if (fs.existsSync(sdkSessionsPath)) {
          const raw = fs.readFileSync(sdkSessionsPath, "utf-8");
          if (raw.trim()) {
            const parsed = JSON.parse(raw) as { schemaVersion?: number };
            const hasUnassignedInMemory = sdkSessionsStore
              .list()
              .some((t) => t.projectId === "unassigned");
            if (parsed.schemaVersion === 1 && hasUnassignedInMemory) {
              console.log(
                JSON.stringify({
                  level: "info",
                  message:
                    "sdk-sessions.json is still schemaVersion 1; v1→v2 migration will land on next task mutation (ADR-038)",
                }),
              );
            }
          }
        }
      } catch {
        // Non-fatal — the diagnostic is purely informational.
      }

      const sessionWatcher = new SessionWatcher();

      // Claude CLI version probe (refreshed on demand; post-upgrade clients
      // see the new number without a server restart).
      let claudeVersion: ClaudeVersionInfo = probeClaudeVersion();
      const versionInfo = (): ClaudeVersionInfo => {
        if (!claudeVersion.raw) claudeVersion = probeClaudeVersion();
        return claudeVersion;
      };

      // Mount routes.
      const settingsPath = `${config.registryDir}/settings.json`;
      const settingsDeps = {
        readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
        writeFile: (p: string, d: string) => writeFile(p, d),
        existsSync: (p: string) => fs.existsSync(p),
        mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
        lock: lockPath,
        ensureFile: ensureFileExists,
      };
      const projectFsDeps = {
        existsSync: (p: string) => fs.existsSync(p),
        mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
        writeFileSync: (p: string, d: string) => fs.writeFileSync(p, d),
      };
      app.route("/", createProjectRoutes(projectManager, projectFsDeps));
      app.route("/", createSettingsRoutes(settingsPath, settingsDeps));
      app.route("/", createProfilesRoutes());
      // Section 03 (iterate 3) — preview-session manager. Single instance
      // per server process so the dedup map lives across requests. Its
      // killAll() runs on shutdown so user-spawned dev servers don't
      // linger past a webui restart.
      const previewManager = new PreviewSessionManager();

      app.route(
        "/",
        createExternalRoutes({
          store: sdkSessionsStore,
          watcher: sessionWatcher,
          // Section 02 — PATCH/POST projectId validation. Excludes the
          // synthesized Unassigned row (that sentinel is hard-coded valid
          // inside validateProjectIdOrError).
          getKnownProjectIds: () =>
            new Set(projectManager.getAll().filter((p) => !p.synthesized).map((p) => p.id)),
          // Section 03 — actions / preview / stub routes. Synthesized row
          // has no filesystem path so it's skipped by getProjectById.
          getProjectById: (id) => {
            const p = projectManager.getById(id);
            if (!p || p.synthesized) return undefined;
            return {
              id: p.id,
              name: p.name,
              path: p.path,
              profile: p.profile,
              synthesized: p.synthesized,
              settings: p.settings ? { color: p.settings.color } : undefined,
            };
          },
          previewManager,
          loadProfile: (name: string) => loadProfileReal(name, getProfilesDir()),
        }),
      );
      app.route("/", createDiagnosticsRoutes({ store: sdkSessionsStore, versionInfo }));

      // Section 03 — boot-time profile coherence check (plan § 2.1 matrix).
      // Warn (don't fail) when stack.frontend is declared but dev_server
      // is not wired, or vice versa. Non-fatal — the API route resolves
      // preview.enabled per request, but the log helps operators diagnose
      // "why isn't Preview showing up?" without opening devtools.
      try {
        const all = projectManager.getAll().filter((p) => !p.synthesized);
        for (const proj of all) {
          if (!proj.profile) continue;
          const prof = loadProfileReal(proj.profile, getProfilesDir()) as
            | (ReturnType<typeof loadProfileReal> & { stack?: { frontend?: unknown } })
            | null;
          if (!prof) continue;
          const hasFrontend = Boolean(
            (prof as { stack?: { frontend?: unknown } }).stack?.frontend,
          );
          const hasDevServer = Boolean(prof.dev_server?.command);
          if (hasFrontend && !hasDevServer) {
            console.warn(
              JSON.stringify({
                level: "warn",
                message:
                  "profile declares stack.frontend but no dev_server.command — preview button will stay hidden",
                projectId: proj.id,
                profile: proj.profile,
              }),
            );
          }
          if (!hasFrontend && hasDevServer) {
            console.warn(
              JSON.stringify({
                level: "warn",
                message:
                  "profile has dev_server.command but no stack.frontend — preview gate denies regardless (ADR-036)",
                projectId: proj.id,
                profile: proj.profile,
              }),
            );
          }
        }
      } catch (err) {
        // Non-fatal — the diagnostic is purely informational.
        console.warn(
          JSON.stringify({
            level: "warn",
            message: "boot-time profile coherence check threw",
            error: String(err).slice(0, 200),
          }),
        );
      }

      const shutdown = () => {
        console.log("Shutting down…");
        try {
          previewManager.killAll();
        } catch {
          // best-effort — ignore shutdown errors
        }
        process.exit(0);
      };
      process.on("SIGTERM", shutdown);
      process.on("SIGINT", shutdown);
      process.on("exit", () => {
        try {
          previewManager.killAll();
        } catch {
          // ignore
        }
      });

      serve({ fetch: app.fetch, port: config.port }, (info) => {
        console.log(`Shipwright Command Center listening on http://localhost:${info.port}`);
      });
    } catch (err) {
      console.error("FATAL: Server startup failed:", err);
      process.exit(1);
    }
  })();
}

app.use("/*", serveStatic({ root: config.staticDir }));

app.notFound((c) => c.json({ error: "Not found" }, 404));
