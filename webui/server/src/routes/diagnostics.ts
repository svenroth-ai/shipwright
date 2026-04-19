/*
 * GET /api/diagnostics — external-launch health + version gate.
 *
 * Exposes the CLI version + supported-range, number of tracked sessions,
 * last-scan timestamp (set by the heartbeat probe), and per-launcher
 * availability (Copy is always available; Terminal/VSCode/Desktop are
 * explicitly labeled as v2+).
 *
 * Round-3 plan integration: UI's Diagnostics page reads this and surfaces
 * a persistent banner when the installed CLI is out-of-range.
 */

import { Hono } from "hono";

import { MIN_SUPPORTED_CLI, type ClaudeVersionInfo } from "../core/cli-compat.js";
import { SdkSessionsStore } from "../core/sdk-sessions-store.js";

export interface DiagnosticsSnapshot {
  claudeCli: {
    raw: string;
    parsed: ClaudeVersionInfo["parsed"];
    supported: boolean;
    minSupported: string;
  };
  sessions: {
    total: number;
    byState: Record<string, number>;
  };
  launchers: {
    copy: { available: true };
    terminal: { available: false; reason: "deferred to v2 (variant-a narrow)" };
    vscode: { available: false; reason: "deferred to v2 (variant-a narrow)" };
    desktop: { available: false; reason: "awaiting Claude Desktop URL scheme" };
  };
}

export function createDiagnosticsRoutes(args: {
  store: SdkSessionsStore;
  versionInfo: () => ClaudeVersionInfo;
}) {
  const app = new Hono();

  app.get("/api/diagnostics", (c) => {
    const v = args.versionInfo();
    const tasks = args.store.list();
    const byState: Record<string, number> = {};
    for (const t of tasks) {
      byState[t.state] = (byState[t.state] ?? 0) + 1;
    }
    const snapshot: DiagnosticsSnapshot = {
      claudeCli: {
        raw: v.raw,
        parsed: v.parsed,
        supported: v.supported,
        minSupported: MIN_SUPPORTED_CLI,
      },
      sessions: {
        total: tasks.length,
        byState,
      },
      launchers: {
        copy: { available: true },
        terminal: { available: false, reason: "deferred to v2 (variant-a narrow)" },
        vscode: { available: false, reason: "deferred to v2 (variant-a narrow)" },
        desktop: { available: false, reason: "awaiting Claude Desktop URL scheme" },
      },
    };
    return c.json(snapshot);
  });

  return app;
}
