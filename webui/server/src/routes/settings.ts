import { Hono } from "hono";
import type { GlobalSettings } from "../../../client/src/types/settings.js";

export interface SettingsDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}

const DEFAULT_SETTINGS: GlobalSettings = {
  port: 3847,
  maxConcurrent: 3,
  heartbeatIntervalMs: 30000,
};

export function createSettingsRoutes(
  settingsPath: string,
  deps: SettingsDeps
): Hono {
  const app = new Hono();

  app.get("/api/settings", async (c) => {
    if (!deps.existsSync(settingsPath)) {
      return c.json({ data: DEFAULT_SETTINGS });
    }
    try {
      const content = await deps.readFile(settingsPath, "utf-8");
      return c.json({ data: { ...DEFAULT_SETTINGS, ...JSON.parse(content) } });
    } catch {
      return c.json({ data: DEFAULT_SETTINGS });
    }
  });

  app.put("/api/settings", async (c) => {
    const body = await c.req.json();
    let existing = { ...DEFAULT_SETTINGS };
    if (deps.existsSync(settingsPath)) {
      try {
        const content = await deps.readFile(settingsPath, "utf-8");
        existing = { ...existing, ...JSON.parse(content) };
      } catch {
        // Use defaults
      }
    }
    const merged = { ...existing, ...body };
    const dir = settingsPath.substring(0, settingsPath.lastIndexOf("/"));
    if (dir && !deps.existsSync(dir)) {
      deps.mkdirSync(dir, { recursive: true });
    }
    await deps.writeFile(settingsPath, JSON.stringify(merged, null, 2));
    return c.json({ data: merged });
  });

  return app;
}
