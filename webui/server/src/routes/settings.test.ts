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

  it("PUT /api/settings merges with existing", async () => {
    const { app } = setup(JSON.stringify({ maxConcurrent: 5, defaultAutonomy: "autonomous" }));
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ maxConcurrent: 8 }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.maxConcurrent).toBe(8);
    expect(body.data.defaultAutonomy).toBe("autonomous"); // preserved from existing
  });

  it("GET /api/settings reads existing file", async () => {
    const { app } = setup(JSON.stringify({ maxConcurrent: 7, defaultProfile: "supabase-nextjs" }));
    const res = await app.request("/api/settings");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.maxConcurrent).toBe(7);
    expect(body.data.defaultProfile).toBe("supabase-nextjs");
  });

  it("PUT /api/settings with phaseToStatusMapping persists it", async () => {
    const { app, storage } = setup();
    const mapping = { project: "backlog", build: "in_progress", test: "in_review", deploy: "done" };
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phaseToStatusMapping: mapping }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.phaseToStatusMapping).toEqual(mapping);
    // Also check that it was written to the file
    const written = JSON.parse(storage["/tmp/settings.json"]);
    expect(written.phaseToStatusMapping).toEqual(mapping);
  });

  it("PUT /api/settings with defaultAutonomy persists it", async () => {
    const { app } = setup();
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ defaultAutonomy: "autonomous" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.defaultAutonomy).toBe("autonomous");
  });
});
