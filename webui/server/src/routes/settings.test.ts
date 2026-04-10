import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createSettingsRoutes } from "./settings.js";

function setup(existing?: string) {
  const storage: Record<string, string> = {};
  if (existing) storage["/tmp/settings.json"] = existing;
  const deps = {
    readFile: vi.fn(async (p: string) => storage[p] ?? ""),
    writeFile: vi.fn(async (p: string, d: string) => { storage[p] = d; }),
    existsSync: vi.fn((p: string) => p in storage),
    mkdirSync: vi.fn(),
  };
  const app = new Hono();
  app.route("/", createSettingsRoutes("/tmp/settings.json", deps));
  return { app, storage };
}

describe("Settings Routes", () => {
  it("GET /api/settings returns defaults when no file", async () => {
    const { app } = setup();
    const res = await app.request("/api/settings");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.port).toBe(3847);
    expect(body.data.maxConcurrent).toBe(3);
  });

  it("PUT /api/settings persists and returns updated", async () => {
    const { app } = setup();
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ maxConcurrent: 5 }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.maxConcurrent).toBe(5);
    expect(body.data.port).toBe(3847); // default preserved
  });
});
