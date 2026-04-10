import { describe, it, expect, vi } from "vitest";
import { readConfigFile, readAllConfigs, derivePipelineFromConfigs } from "./config-reader.js";
import type { FileSystemDeps } from "./event-reader.js";

function mockFs(files: Record<string, string>): FileSystemDeps {
  return {
    readFile: vi.fn(async (path: string) => {
      if (files[path]) return files[path];
      throw new Error("ENOENT");
    }),
    existsSync: vi.fn((path: string) => path in files),
  };
}

describe("readConfigFile", () => {
  it("returns parsed JSON for valid file", async () => {
    const fs = mockFs({ "/proj/config.json": '{"status":"complete"}' });
    const result = await readConfigFile("/proj/config.json", fs);
    expect(result).toEqual({ status: "complete" });
  });

  it("returns null for missing file", async () => {
    const fs = mockFs({});
    expect(await readConfigFile("/proj/missing.json", fs)).toBeNull();
  });
});

describe("readAllConfigs", () => {
  it("reads present configs, omits missing", async () => {
    const fs = mockFs({
      "/proj/shipwright_run_config.json": '{"status":"running"}',
      "/proj/shipwright_build_config.json": '{"status":"complete"}',
    });
    const configs = await readAllConfigs("/proj", fs);
    expect(configs).toHaveProperty("shipwright_run_config");
    expect(configs).toHaveProperty("shipwright_build_config");
    expect(configs).not.toHaveProperty("shipwright_test_config");
  });
});

describe("derivePipelineFromConfigs", () => {
  it("derives correct phase statuses from configs", () => {
    const configs = {
      shipwright_project_config: { status: "complete" },
      shipwright_build_config: { status: "running" },
    };
    const phases = derivePipelineFromConfigs(configs);
    expect(phases.find((p) => p.name === "project")?.status).toBe("completed");
    expect(phases.find((p) => p.name === "build")?.status).toBe("running");
    expect(phases.find((p) => p.name === "test")?.status).toBe("pending");
  });

  it("produces valid phases without run config", () => {
    const phases = derivePipelineFromConfigs({});
    expect(phases).toHaveLength(7);
    expect(phases.every((p) => p.status === "pending")).toBe(true);
  });
});
