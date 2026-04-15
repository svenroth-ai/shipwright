import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createProfilesRoutes } from "./profiles.js";
import { errorHandler } from "../middleware/error-handler.js";

function setup(opts: {
  files: string[];
  loaders: Record<string, { name?: string; label?: string; description?: string } | null>;
}) {
  const readdirSync = vi.fn(() => opts.files);
  const loadProfile = vi.fn((name: string) => opts.loaders[name] ?? null);
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createProfilesRoutes({
    profilesDir: "/fake/profiles",
    readdirSync,
    loadProfile,
  }));
  return { app, readdirSync, loadProfile };
}

describe("Profiles routes", () => {
  it("GET /api/profiles lists profile JSON files", async () => {
    const { app } = setup({
      files: ["a.json", "b.json"],
      loaders: {
        a: { name: "a", label: "A", description: "first" },
        b: { name: "b", label: "B", description: "second" },
      },
    });
    const res = await app.request("/api/profiles");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(2);
    expect(body.data[0].name).toBe("a");
    expect(body.data[1].name).toBe("b");
  });

  it("returns profiles sorted alphabetically", async () => {
    const { app } = setup({
      files: ["zebra.json", "alpha.json", "mike.json"],
      loaders: {
        zebra: { name: "zebra" },
        alpha: { name: "alpha" },
        mike: { name: "mike" },
      },
    });
    const res = await app.request("/api/profiles");
    const body = await res.json();
    const names = body.data.map((p: { name: string }) => p.name);
    expect(names).toEqual(["alpha", "mike", "zebra"]);
  });

  it("ignores files starting with _", async () => {
    const { app } = setup({
      files: ["good.json", "_internal.json", "_disabled.json"],
      loaders: {
        good: { name: "good" },
        _internal: { name: "_internal" },
        _disabled: { name: "_disabled" },
      },
    });
    const res = await app.request("/api/profiles");
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].name).toBe("good");
  });

  it("skips malformed JSON without 500ing", async () => {
    const { app } = setup({
      files: ["good.json", "broken.json"],
      loaders: {
        good: { name: "good" },
        broken: null, // loadProfile returns null on parse failure
      },
    });
    const res = await app.request("/api/profiles");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].name).toBe("good");
  });
});
