import type { FileSystemDeps } from "./event-reader.js";
import type { PipelinePhase, PhaseStatus } from "../../../client/src/types/pipeline.js";

const CONFIG_FILES = [
  "shipwright_run_config.json",
  "shipwright_project_config.json",
  "shipwright_plan_config.json",
  "shipwright_build_config.json",
  "shipwright_test_config.json",
  "shipwright_deploy_config.json",
  "shipwright_changelog_config.json",
] as const;

const PHASES = ["project", "design", "plan", "build", "test", "changelog", "deploy"] as const;

const CONFIG_TO_PHASE: Record<string, string> = {
  shipwright_project_config: "project",
  shipwright_plan_config: "plan",
  shipwright_build_config: "build",
  shipwright_test_config: "test",
  shipwright_deploy_config: "deploy",
  shipwright_changelog_config: "changelog",
};

export async function readConfigFile<T>(
  filePath: string,
  deps: FileSystemDeps
): Promise<T | null> {
  if (!deps.existsSync(filePath)) return null;
  try {
    const content = await deps.readFile(filePath, "utf-8");
    return JSON.parse(content) as T;
  } catch {
    return null;
  }
}

export async function readAllConfigs(
  projectDir: string,
  deps: FileSystemDeps
): Promise<Record<string, unknown>> {
  const result: Record<string, unknown> = {};
  for (const file of CONFIG_FILES) {
    const config = await readConfigFile(`${projectDir}/${file}`, deps);
    if (config !== null) {
      result[file.replace(".json", "")] = config;
    }
  }
  return result;
}

export function derivePipelineFromConfigs(
  configs: Record<string, unknown>
): PipelinePhase[] {
  const phaseStatuses = new Map<string, PhaseStatus>();

  for (const [configKey, value] of Object.entries(configs)) {
    const phaseName = CONFIG_TO_PHASE[configKey];
    if (!phaseName) continue;
    const config = value as Record<string, unknown>;
    if (config.status === "complete" || config.status === "completed") {
      phaseStatuses.set(phaseName, "completed");
    } else {
      phaseStatuses.set(phaseName, "running");
    }
  }

  // Design phase: check if run config has design_phase
  if (configs.shipwright_run_config) {
    const runConfig = configs.shipwright_run_config as Record<string, unknown>;
    if (runConfig.design_phase === "complete") {
      phaseStatuses.set("design", "completed");
    }
  }
  if (configs.shipwright_project_config) {
    const projConfig = configs.shipwright_project_config as Record<string, unknown>;
    if (projConfig.design_phase === "complete") {
      phaseStatuses.set("design", "completed");
    }
  }

  return PHASES.map((name) => ({
    name,
    status: phaseStatuses.get(name) ?? "pending",
  }));
}
