/*
 * Thin fetch wrappers for /api/external/*.
 *
 * Kept deliberately separate from TanStack Query calls so hooks can layer
 * caching, optimistic updates, and SSE invalidation on top without
 * duplicating endpoint strings.
 */

export const EXTERNAL_API = "/api/external";

export type ExternalTaskState =
  | "draft"
  | "awaiting_external_start"
  | "active"
  | "idle"
  | "jsonl_missing"
  | "launch_failed"
  | "done";

export interface ExternalTaskInboxState {
  pendingToolUseIds: string[];
  dismissedToolUseIds: string[];
  lastProcessedByteOffset: number;
}

export interface ExternalTask {
  taskId: string;
  sessionUuid: string;
  cwd: string;
  pluginDirs: string[];
  parentTaskId?: string;
  parentSessionUuid?: string;
  title: string;
  state: ExternalTaskState;
  createdAt: string;
  launchedAt?: string;
  firstJsonlObservedAt?: string;
  lastJsonlSeenMtimeMs?: number;
  inbox: ExternalTaskInboxState;
}

export interface CopyCommandForms {
  powershell: string;
  cmd: string;
  posix: string;
}

export interface TranscriptChunk {
  fingerprint: string;
  size: number;
  fromByte: number;
  toByte: number;
  content: string;
}

export type TranscriptResponse =
  | { status: "ok"; chunk: TranscriptChunk; task: ExternalTask }
  | { status: "missing"; task: ExternalTask }
  | { status: "rotated"; task: ExternalTask; currentFingerprint: string };

export interface InboxItem {
  taskId: string;
  sessionUuid: string;
  taskTitle: string;
  toolUseId: string;
  toolName: string;
  input: unknown;
  bestEffort: true;
}

export interface DiagnosticsSnapshot {
  claudeCli: {
    raw: string;
    parsed: { major: number; minor: number; patch: number } | null;
    supported: boolean;
    minSupported: string;
  };
  sessions: { total: number; byState: Record<string, number> };
  launchers: {
    copy: { available: true };
    terminal: { available: false; reason: string };
    vscode: { available: false; reason: string };
    desktop: { available: false; reason: string };
  };
}

async function httpJson<T>(input: string, init?: RequestInit): Promise<T> {
  const r = await fetch(input, init);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`HTTP ${r.status} ${input}: ${text.slice(0, 200)}`);
  }
  return (await r.json()) as T;
}

export async function listTasks(): Promise<ExternalTask[]> {
  const json = await httpJson<{ tasks: ExternalTask[] }>(`${EXTERNAL_API}/tasks`);
  return json.tasks;
}

export async function getTask(taskId: string): Promise<ExternalTask> {
  const json = await httpJson<{ task: ExternalTask }>(`${EXTERNAL_API}/tasks/${taskId}`);
  return json.task;
}

export async function createTask(args: {
  title: string;
  cwd: string;
  pluginDirs?: string[];
}): Promise<ExternalTask> {
  const json = await httpJson<{ task: ExternalTask }>(`${EXTERNAL_API}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  return json.task;
}

export async function launchTask(
  taskId: string,
  args: { resume?: boolean } = {},
): Promise<{ task: ExternalTask; commands: CopyCommandForms }> {
  return await httpJson<{ task: ExternalTask; commands: CopyCommandForms }>(
    `${EXTERNAL_API}/tasks/${taskId}/launch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    },
  );
}

export async function forkTask(
  taskId: string,
  args: { title?: string } = {},
): Promise<{ task: ExternalTask; commands: CopyCommandForms }> {
  return await httpJson<{ task: ExternalTask; commands: CopyCommandForms }>(
    `${EXTERNAL_API}/tasks/${taskId}/fork`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    },
  );
}

export async function renameTask(taskId: string, title: string): Promise<ExternalTask> {
  const json = await httpJson<{ task: ExternalTask }>(`${EXTERNAL_API}/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return json.task;
}

export async function closeTask(taskId: string): Promise<ExternalTask> {
  const json = await httpJson<{ task: ExternalTask }>(
    `${EXTERNAL_API}/tasks/${taskId}/close`,
    { method: "POST" },
  );
  return json.task;
}

export async function deleteTask(taskId: string): Promise<void> {
  await httpJson<{ ok: boolean }>(`${EXTERNAL_API}/tasks/${taskId}`, { method: "DELETE" });
}

export async function getTranscript(
  taskId: string,
  args: { fromByte?: number; expectFingerprint?: string | null } = {},
): Promise<TranscriptResponse> {
  const q = new URLSearchParams();
  if (typeof args.fromByte === "number") q.set("fromByte", String(args.fromByte));
  if (args.expectFingerprint) q.set("expectFingerprint", args.expectFingerprint);
  const url = `${EXTERNAL_API}/tasks/${taskId}/transcript${q.size > 0 ? `?${q.toString()}` : ""}`;
  return await httpJson<TranscriptResponse>(url);
}

export async function listInbox(): Promise<InboxItem[]> {
  const json = await httpJson<{ items: InboxItem[] }>(`${EXTERNAL_API}/inbox`);
  return json.items;
}

export async function dismissInboxItem(toolUseId: string): Promise<void> {
  await httpJson(`${EXTERNAL_API}/inbox/${toolUseId}/dismiss`, { method: "POST" });
}

export async function getDiagnostics(): Promise<DiagnosticsSnapshot> {
  return await httpJson<DiagnosticsSnapshot>("/api/diagnostics");
}
