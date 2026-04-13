import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createCapabilitiesRoutes } from "./capabilities.js";
import type { CliCapability } from "../core/capability-probe.js";

function makeCli(overrides: Partial<CliCapability> = {}): CliCapability {
  return {
    name: "claude",
    available: true,
    version: "1.2.3",
    path: "/usr/local/bin/claude",
    checkedAt: "2026-04-13T00:00:00.000Z",
    ...overrides,
  };
}

function mount(deps: Parameters<typeof createCapabilitiesRoutes>[0]) {
  const app = new Hono();
  app.route("/", createCapabilitiesRoutes(deps));
  return app;
}

describe("Capabilities Routes", () => {
  it("GET /api/capabilities returns the probed CLI capability", async () => {
    const probe = vi.fn(async () => makeCli());
    const app = mount({ probe });
    const res = await app.request("/api/capabilities");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.cli.available).toBe(true);
    expect(body.data.cli.version).toBe("1.2.3");
    expect(probe).toHaveBeenCalledTimes(1);
  });

  it("caches within TTL — second GET does not re-probe", async () => {
    const probe = vi.fn(async () => makeCli());
    let t = 0;
    const app = mount({ probe, now: () => t, cacheTtlMs: 1000 });

    await app.request("/api/capabilities");
    t = 500;
    await app.request("/api/capabilities");

    expect(probe).toHaveBeenCalledTimes(1);
  });

  it("re-probes after TTL expires", async () => {
    const probe = vi.fn(async () => makeCli());
    let t = 0;
    const app = mount({ probe, now: () => t, cacheTtlMs: 1000 });

    await app.request("/api/capabilities");
    t = 2000;
    await app.request("/api/capabilities");

    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("POST /api/capabilities/refresh forces a re-probe even inside TTL", async () => {
    const probe = vi.fn(async () => makeCli());
    const app = mount({ probe, cacheTtlMs: 60_000 });

    await app.request("/api/capabilities");
    await app.request("/api/capabilities/refresh", { method: "POST" });

    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("returns available:false cleanly when the probe reports missing CLI", async () => {
    const probe = vi.fn(async () =>
      makeCli({ available: false, version: undefined, path: undefined, error: "claude CLI not found on PATH" }),
    );
    const app = mount({ probe });
    const res = await app.request("/api/capabilities");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.cli.available).toBe(false);
    expect(body.data.cli.error).toBe("claude CLI not found on PATH");
  });

  it("coalesces concurrent requests into a single probe call", async () => {
    let resolveProbe: ((cli: CliCapability) => void) | null = null;
    const probe = vi.fn(
      () => new Promise<CliCapability>((resolve) => {
        resolveProbe = resolve;
      }),
    );
    const app = mount({ probe });

    const [p1, p2, p3] = [
      app.request("/api/capabilities"),
      app.request("/api/capabilities"),
      app.request("/api/capabilities"),
    ];
    // Let the routes attach to the same in-flight promise
    await new Promise((r) => setTimeout(r, 10));
    resolveProbe!(makeCli());
    await Promise.all([p1, p2, p3]);

    expect(probe).toHaveBeenCalledTimes(1);
  });
});
