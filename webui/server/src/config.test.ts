import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { getConfig } from "./config.js";

describe("getConfig", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("returns default port 3847 when no PORT env var is set", () => {
    delete process.env.PORT;
    const config = getConfig();
    expect(config.port).toBe(3847);
  });

  it("reads PORT env var and returns parsed number", () => {
    process.env.PORT = "4000";
    const config = getConfig();
    expect(config.port).toBe(4000);
  });

  it("returns default maxConcurrent of 3", () => {
    delete process.env.SHIPWRIGHT_MAX_CONCURRENT;
    const config = getConfig();
    expect(config.maxConcurrent).toBe(3);
  });

  it("reads SHIPWRIGHT_MAX_CONCURRENT env var", () => {
    process.env.SHIPWRIGHT_MAX_CONCURRENT = "5";
    const config = getConfig();
    expect(config.maxConcurrent).toBe(5);
  });

  it("returns heartbeatIntervalMs of 30000", () => {
    const config = getConfig();
    expect(config.heartbeatIntervalMs).toBe(30000);
  });

  it("returns a registryDir path containing .shipwright-webui", () => {
    const config = getConfig();
    expect(config.registryDir).toContain(".shipwright-webui");
  });
});
