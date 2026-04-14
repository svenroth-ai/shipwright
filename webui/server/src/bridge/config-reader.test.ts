import { describe, it, expect, vi } from "vitest";
import {
  readConfigFile,
  readAllConfigs,
  derivePipelineFromConfigs,
  getProjectMode,
  type ProjectModeDeps,
} from "./config-reader.js";
import type { FileSystemDeps } from "./event-reader.js";

function mockModeDeps(files: Record<string, string>): ProjectModeDeps {
  return {
    existsSync: vi.fn((p: string) => p in files),
    readFileSync: vi.fn((p: string) => {
      if (!(p in files)) throw new Error("ENOENT");
      return files[p];
    }),
  };
}

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

describe("getProjectMode", () => {
  it("returns standalone when run_config.json is missing", () => {
    const deps = mockModeDeps({});
    expect(getProjectMode("/proj/no-config", deps)).toBe("standalone");
  });

  it("returns pipeline for non-terminal status", () => {
    const deps = mockModeDeps({
      "/proj/running/shipwright_run_config.json": JSON.stringify({
        status: "running",
      }),
    });
    expect(getProjectMode("/proj/running", deps)).toBe("pipeline");
  });

  it("returns pipeline for not_started status (fresh wizard project)", () => {
    const deps = mockModeDeps({
      "/proj/fresh/shipwright_run_config.json": JSON.stringify({
        status: "not_started",
      }),
    });
    expect(getProjectMode("/proj/fresh", deps)).toBe("pipeline");
  });

  it("returns iterate for terminal status 'complete' (webui's own schema)", () => {
    const deps = mockModeDeps({
      "/proj/done/shipwright_run_config.json": JSON.stringify({
        status: "complete",
      }),
    });
    expect(getProjectMode("/proj/done", deps)).toBe("iterate");
  });

  it("returns iterate for legacy 'completed' alias", () => {
    const deps = mockModeDeps({
      "/proj/done2/shipwright_run_config.json": JSON.stringify({
        status: "completed",
      }),
    });
    expect(getProjectMode("/proj/done2", deps)).toBe("iterate");
  });

  it("returns iterate for failed/cancelled/error", () => {
    for (const status of ["failed", "cancelled", "error"]) {
      const deps = mockModeDeps({
        [`/proj/x/shipwright_run_config.json`]: JSON.stringify({ status }),
      });
      expect(getProjectMode("/proj/x", deps)).toBe("iterate");
    }
  });

  it("returns standalone on malformed JSON (never throws)", () => {
    const deps = mockModeDeps({
      "/proj/bad/shipwright_run_config.json": "{ not valid json",
    });
    expect(getProjectMode("/proj/bad", deps)).toBe("standalone");
  });

  it("returns pipeline when status field is missing entirely", () => {
    const deps = mockModeDeps({
      "/proj/noStatus/shipwright_run_config.json": JSON.stringify({
        pipeline: ["project", "build"],
      }),
    });
    // Missing status is treated as non-terminal → pipeline.
    expect(getProjectMode("/proj/noStatus", deps)).toBe("pipeline");
  });
});
