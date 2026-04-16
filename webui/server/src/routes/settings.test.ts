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

  // Iterate 14.8.2 — defaultModel + defaultMode
  it("GET /api/settings returns defaultModel when persisted", async () => {
    const { app } = setup(JSON.stringify({ defaultModel: "claude-opus-4-6" }));
    const res = await app.request("/api/settings");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.defaultModel).toBe("claude-opus-4-6");
  });

  it("GET /api/settings returns defaultMode when persisted", async () => {
    const { app } = setup(JSON.stringify({ defaultMode: "acceptEdits" }));
    const res = await app.request("/api/settings");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.defaultMode).toBe("acceptEdits");
  });

  it("PUT /api/settings with defaultModel persists and returns it", async () => {
    const { app, storage } = setup();
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ defaultModel: "claude-sonnet-4-6" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.defaultModel).toBe("claude-sonnet-4-6");
    const written = JSON.parse(storage["/tmp/settings.json"]);
    expect(written.defaultModel).toBe("claude-sonnet-4-6");
  });

  it("PUT /api/settings with defaultMode persists and returns it", async () => {
    const { app, storage } = setup();
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ defaultMode: "plan" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.defaultMode).toBe("plan");
    const written = JSON.parse(storage["/tmp/settings.json"]);
    expect(written.defaultMode).toBe("plan");
  });

  it("PUT /api/settings with both defaultModel and defaultMode together", async () => {
    const { app } = setup();
    const res = await app.request("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ defaultModel: "claude-haiku-4-5", defaultMode: "bypassPermissions" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.defaultModel).toBe("claude-haiku-4-5");
    expect(body.data.defaultMode).toBe("bypassPermissions");
  });
});
