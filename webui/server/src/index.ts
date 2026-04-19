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
      const projectManagerDeps = {
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
      const sdkSessionsPath = `${config.registryDir}/sdk-sessions.json`;
      const sdkSessionsDeps = {
        readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
        writeFile: (p: string, d: string) => writeFile(p, d),
        existsSync: (p: string) => fs.existsSync(p),
        mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
        lock: lockPath,
        ensureFile: ensureFileExists,
      };
      const sdkSessionsStore = new SdkSessionsStore(sdkSessionsPath, sdkSessionsDeps);
      await sdkSessionsStore.load();
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
      app.route("/", createExternalRoutes({ store: sdkSessionsStore, watcher: sessionWatcher }));
      app.route("/", createDiagnosticsRoutes({ store: sdkSessionsStore, versionInfo }));

      const shutdown = () => {
        console.log("Shutting down…");
        process.exit(0);
      };
      process.on("SIGTERM", shutdown);
      process.on("SIGINT", shutdown);

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
