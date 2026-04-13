import { Hono } from "hono";
import { probeClaudeCli, type CliCapability } from "../core/capability-probe.js";

export interface CapabilitiesDeps {
  probe?: () => Promise<CliCapability>;
  now?: () => number;
  cacheTtlMs?: number;
}

export function createCapabilitiesRoutes(deps: CapabilitiesDeps = {}): Hono {
  const probe = deps.probe ?? (() => probeClaudeCli());
  const now = deps.now ?? (() => Date.now());
  const cacheTtlMs = deps.cacheTtlMs ?? 60_000;

  let cached: CliCapability | null = null;
  let cachedAt = 0;
  let inFlight: Promise<CliCapability> | null = null;

  async function getCapability(force: boolean): Promise<CliCapability> {
    if (!force && cached && now() - cachedAt < cacheTtlMs) return cached;
    if (inFlight) return inFlight;

    inFlight = probe()
      .then((result) => {
        cached = result;
        cachedAt = now();
        return result;
      })
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  }

  const app = new Hono();

  app.get("/api/capabilities", async (c) => {
    const cli = await getCapability(false);
    return c.json({ data: { cli } });
  });

  app.post("/api/capabilities/refresh", async (c) => {
    const cli = await getCapability(true);
    return c.json({ data: { cli } });
  });

  return app;
}
