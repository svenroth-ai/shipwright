import type { ShipwrightEvent } from "../../../client/src/types/event.js";

export interface WriterDeps {
  appendFile: (path: string, data: string) => Promise<void>;
  lock: (path: string) => Promise<() => Promise<void>>;
  ensureDir?: (path: string) => void;
  ensureFile?: (path: string) => void;
}

export async function appendEvent(
  filePath: string,
  event: ShipwrightEvent,
  deps: WriterDeps
): Promise<void> {
  // Ensure parent directory and file exist before lock (lockfile needs lstat)
  if (deps.ensureDir) {
    const dir = filePath.substring(0, Math.max(filePath.lastIndexOf("/"), filePath.lastIndexOf("\\")));
    if (dir) deps.ensureDir(dir);
  }
  if (deps.ensureFile) {
    deps.ensureFile(filePath);
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
  phase?: string,
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
    ...(phase && { phase }),
  };

  if (deps) {
    await appendEvent(filePath, event, deps);
  }

  return event;
}

export async function emitPhaseStartedEvent(
  filePath: string,
  taskId: string,
  projectId: string,
  phase: string,
  deps: WriterDeps
): Promise<ShipwrightEvent> {
  const event: ShipwrightEvent = {
    type: "phase_started",
    timestamp: new Date().toISOString(),
    task_id: taskId,
    project_id: projectId,
    phase,
    source: "webui",
  };
  await appendEvent(filePath, event, deps);
  return event;
}

export async function emitWorkCompletedEvent(
  filePath: string,
  taskId: string,
  projectId: string,
  deps: WriterDeps
): Promise<ShipwrightEvent> {
  const event: ShipwrightEvent = {
    type: "work_completed",
    timestamp: new Date().toISOString(),
    task_id: taskId,
    project_id: projectId,
    source: "webui",
  };
  await appendEvent(filePath, event, deps);
  return event;
}

export async function emitTaskCancelledEvent(
  filePath: string,
  taskId: string,
  projectId: string,
  deps: WriterDeps,
): Promise<ShipwrightEvent> {
  const event: ShipwrightEvent = {
    type: "task_cancelled",
    timestamp: new Date().toISOString(),
    task_id: taskId,
    project_id: projectId,
    source: "webui",
  };
  await appendEvent(filePath, event, deps);
  return event;
}

export async function emitTaskUpdatedEvent(
  filePath: string,
  taskId: string,
  projectId: string,
  fields: { title?: string; description?: string },
  deps: WriterDeps,
): Promise<ShipwrightEvent> {
  const event: ShipwrightEvent = {
    type: "task_updated",
    timestamp: new Date().toISOString(),
    task_id: taskId,
    project_id: projectId,
    source: "webui",
    ...(fields.title !== undefined && { title: fields.title }),
    ...(fields.description !== undefined && { description: fields.description }),
  };
  await appendEvent(filePath, event, deps);
  return event;
}

export async function emitWorkFailedEvent(
  filePath: string,
  taskId: string,
  projectId: string,
  detail: string,
  deps: WriterDeps
): Promise<ShipwrightEvent> {
  const event: ShipwrightEvent = {
    type: "work_failed",
    timestamp: new Date().toISOString(),
    task_id: taskId,
    project_id: projectId,
    detail,
    source: "webui",
  };
  await appendEvent(filePath, event, deps);
  return event;
}
