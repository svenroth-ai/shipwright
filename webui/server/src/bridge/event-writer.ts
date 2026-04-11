import type { ShipwrightEvent } from "../../../client/src/types/event.js";

export interface WriterDeps {
  appendFile: (path: string, data: string) => Promise<void>;
  lock: (path: string) => Promise<() => Promise<void>>;
  ensureDir?: (path: string) => void;
}

export async function appendEvent(
  filePath: string,
  event: ShipwrightEvent,
  deps: WriterDeps
): Promise<void> {
  // Ensure parent directory exists before lock/write
  if (deps.ensureDir) {
    const dir = filePath.substring(0, Math.max(filePath.lastIndexOf("/"), filePath.lastIndexOf("\\")));
    if (dir) deps.ensureDir(dir);
  }
  const release = await deps.lock(filePath);
  try {
    await deps.appendFile(filePath, JSON.stringify(event) + "\n");
  } finally {
    await release();
  }
}

export async function emitTaskCreatedEvent(
  filePath: string,
  taskId: string,
  projectId: string,
  description: string,
  intent?: string,
  priority?: string,
  deps?: WriterDeps
): Promise<ShipwrightEvent> {
  const event: ShipwrightEvent = {
    type: "task_created",
    timestamp: new Date().toISOString(),
    task_id: taskId,
    project_id: projectId,
    description,
    source: "webui",
    ...(intent && { intent }),
    ...(priority && { priority }),
  };

  if (deps) {
    await appendEvent(filePath, event, deps);
  }

  return event;
}
