import type { EventStore } from "../core/event-store.js";
import type { PipelineRun, PipelinePhase } from "../../../client/src/types/pipeline.js";
import { readAllConfigs, derivePipelineFromConfigs } from "./config-reader.js";
import type { FileSystemDeps } from "./event-reader.js";
import fs from "fs";
import { readFile } from "fs/promises";

const defaultFsDeps: FileSystemDeps = {
  readFile: (path, encoding) => readFile(path, encoding as BufferEncoding),
  existsSync: (path) => fs.existsSync(path),
};

export async function getPipelineState(
  projectId: string,
  eventStore: EventStore,
  projectDir: string,
  fsDeps: FileSystemDeps = defaultFsDeps
): Promise<PipelineRun> {
  const eventPhases = eventStore.getPipelineState(projectId);
  const configs = await readAllConfigs(projectDir, fsDeps);
  const configPhases = derivePipelineFromConfigs(configs);

  // Merge: events take priority, configs fill gaps
  const merged: PipelinePhase[] = eventPhases.map((ep) => {
    const cp = configPhases.find((c) => c.name === ep.name);
    if (ep.status !== "pending") return ep;
    if (cp && cp.status !== "pending") return { ...ep, status: cp.status };
    return ep;
  });

  const currentPhase = merged.find((p) => p.status === "running")?.name;

  return {
    projectId,
    phases: merged,
    currentPhase,
  };
}
