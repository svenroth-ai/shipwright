import { Hono } from "hono";
import type { GlobalSettings } from "../../../client/src/types/settings.js";

export interface SettingsDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  // Optional: cross-process file lock + file-exists guard. Serializes
  // the PUT read-merge-write cycle so two concurrent settings saves
  // can't lose fields. Omitted in unit tests.
  lock?: (path: string) => Promise<() => Promise<void>>;
  ensureFile?: (path: string) => void;
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
    const dir = settingsPath.substring(0, settingsPath.lastIndexOf("/"));
    if (dir && !deps.existsSync(dir)) {
      deps.mkdirSync(dir, { recursive: true });
    }
    // Ensure the file exists BEFORE acquiring the lock — proper-lockfile
    // calls lstat on the target path and fails if it's missing. The
    // first PUT against a fresh install has no settings.json yet.
    if (deps.ensureFile) deps.ensureFile(settingsPath);

    // Read-merge-write must happen inside the lock; otherwise two
    // concurrent PUTs would both read the same baseline and the second
    // writer would silently drop the first writer's fields.
    const rmw = async (): Promise<GlobalSettings> => {
      let existing = { ...DEFAULT_SETTINGS };
      if (deps.existsSync(settingsPath)) {
        try {
          const content = await deps.readFile(settingsPath, "utf-8");
          if (content.trim()) {
            existing = { ...existing, ...JSON.parse(content) };
          }
        } catch {
          // Malformed or empty — fall back to defaults.
        }
      }
      const merged = { ...existing, ...body };
      await deps.writeFile(settingsPath, JSON.stringify(merged, null, 2));
      return merged;
    };

    let merged: GlobalSettings;
    if (deps.lock) {
      const release = await deps.lock(settingsPath);
      try {
        merged = await rmw();
      } finally {
        await release();
      }
    } else {
      merged = await rmw();
    }
    return c.json({ data: merged });
  });

  return app;
}
