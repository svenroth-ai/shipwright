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
  /**
   * Iterate 3 section 02 — ADR-037. Always present on v2 server responses.
   * The reserved literal "unassigned" represents the synthesized
   * pseudo-project bucket.
   */
  projectId: string;
  /**
   * 2026-04-23 — persisted by the server on successful /launch when
   * NewIssueModal passes the action context. Optional for legacy tasks.
   * TaskDetailHeader prefers `phaseLabel` over the title-regex fallback
   * so the badge reflects the user's explicit choice.
   */
  actionId?: "new-task" | "new-pipeline" | "new-iterate";
  phase?: string;
  phaseLabel?: string;
  description?: string;
  autonomy?: "guided" | "autonomous";
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

export async function listTasks(args: { projectId?: string | null } = {}): Promise<ExternalTask[]> {
  // Section 02 (iterate 3) — optional projectId filter. Null / undefined =
  // all projects (server omits the filter). Reserved literal "unassigned"
  // is a valid filter value.
  const q = new URLSearchParams();
  if (args.projectId) q.set("projectId", args.projectId);
  const suffix = q.size > 0 ? `?${q.toString()}` : "";
  const json = await httpJson<{ tasks: ExternalTask[] }>(`${EXTERNAL_API}/tasks${suffix}`);
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
  /** Iterate 3 section 02 — optional; server defaults to "unassigned". */
  projectId?: string;
  /**
   * 2026-04-23 — iterate-20260423-chat-livetest-2 AC-B. Phase id only;
   * server derives phaseLabel from the project's actions catalog.
   * Omit when the user picks "Save to Backlog" with no selected phase
   * or when the project has no actions catalog (unassigned).
   */
  phase?: string;
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
  args: {
    resume?: boolean;
    /** Section 03 (iterate 3) — forwarded as metadata when present. */
    description?: string;
    autonomy?: "guided" | "autonomous";
    /** 2026-04-23 — action context so server can run full substitution. */
    actionId?: "new-task" | "new-pipeline" | "new-iterate";
    phase?: string;
    phaseLabel?: string;
  } = {},
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

/**
 * Section 03 (iterate 3) — typed alias for the extended launch body. Callers
 * from NewIssueModal use this signature so TS catches accidental `resume`
 * duplication.
 *
 * 2026-04-23 — iterate-20260423-launch-command-wiring. Extended to carry
 * `actionId`, `phase`, and `phaseLabel` so the server can run
 * substitutePlaceholders against the matching action's command_template
 * and persist the phase context on the task. Omitting these fields keeps
 * the legacy three-form shape (backwards compatible with Resume/Fork
 * callers).
 */
export async function launchExternalTask(
  taskId: string,
  args: {
    description?: string;
    autonomy?: "guided" | "autonomous";
    actionId?: "new-task" | "new-pipeline" | "new-iterate";
    phase?: string;
    phaseLabel?: string;
  } = {},
): Promise<{ task: ExternalTask; commands: CopyCommandForms }> {
  return await launchTask(taskId, args);
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

/**
 * Iterate 3 section 02 — PATCH the projectId of a task. Server validates
 * against the known-project-id set + the reserved "unassigned" literal.
 * Unknown id → throws (caller should surface an error toast).
 */
export async function assignTaskProject(
  taskId: string,
  projectId: string,
): Promise<ExternalTask> {
  const json = await httpJson<{ task: ExternalTask }>(`${EXTERNAL_API}/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ projectId }),
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

// -----------------------------------------------------------------------------
// Section 03 (iterate 3) — actions schema + preview + actions-stub wrappers.
// -----------------------------------------------------------------------------

export interface ActionDefinition {
  id: string;
  label: string;
  kind: "external_launch";
  description?: string;
  command_template?: string;
  modal_fields?: string[];
}

export interface PhaseDefinition {
  id: string;
  label: string;
  color?: string;
}

export interface PreviewSpec {
  enabled: boolean;
  command: string | null;
  port: number | null;
  ready_path: string | null;
  ready_timeout_seconds: number | null;
}

export interface ResolvedProjectActions {
  actions: ActionDefinition[];
  phases: PhaseDefinition[];
  defaults: { autonomy: "guided" | "autonomous" };
  preview: PreviewSpec;
  diagnostics: Array<{ code: string; path?: string; detail?: string }>;
}

/**
 * Typed error hierarchy. The decoder below maps a server's structured
 * `{error, detail, ...}` body to one of these classes; UI strings live in
 * the consuming components, never in this module (O11).
 */
export class ApiError extends Error {
  readonly code: string;
  readonly detail?: string;
  readonly status: number;
  readonly payload: Record<string, unknown>;
  constructor(code: string, status: number, payload: Record<string, unknown>) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.payload = payload;
    this.detail =
      typeof payload.detail === "string" ? payload.detail : undefined;
  }
}

export class InvalidPlaceholderApiError extends ApiError {
  readonly placeholder: string;
  readonly actionId: string;
  constructor(status: number, payload: Record<string, unknown>) {
    super("invalid_placeholder", status, payload);
    this.name = "InvalidPlaceholderApiError";
    this.placeholder = String(payload.placeholder ?? "");
    this.actionId = String(payload.actionId ?? "");
  }
}

export class PreviewApiError extends ApiError {
  readonly port?: number;
  readonly seconds?: number;
  constructor(code: string, status: number, payload: Record<string, unknown>) {
    super(code, status, payload);
    this.name = "PreviewApiError";
    this.port =
      typeof payload.port === "number" ? (payload.port as number) : undefined;
    this.seconds =
      typeof payload.seconds === "number"
        ? (payload.seconds as number)
        : undefined;
  }
}

const PREVIEW_ERROR_CODES = new Set([
  "preview_profile_invalid",
  "preview_port_in_use",
  "preview_spawn_failed",
  "preview_exited_early",
  "preview_timeout",
  "preview_unknown_error",
  "preview_unavailable",
]);

/**
 * Decode a Response with status ≥ 400 into a typed Error subclass. Never
 * produces UI strings — callers pick the toast copy based on `err.code`.
 */
export async function decodeApiError(r: Response): Promise<ApiError> {
  let payload: Record<string, unknown> = {};
  try {
    payload = (await r.json()) as Record<string, unknown>;
  } catch {
    payload = { error: `HTTP ${r.status}` };
  }
  const code = typeof payload.error === "string" ? payload.error : `http_${r.status}`;
  if (code === "invalid_placeholder") {
    return new InvalidPlaceholderApiError(r.status, payload);
  }
  if (PREVIEW_ERROR_CODES.has(code)) {
    return new PreviewApiError(code, r.status, payload);
  }
  return new ApiError(code, r.status, payload);
}

async function httpJsonTyped<T>(input: string, init?: RequestInit): Promise<T> {
  const r = await fetch(input, init);
  if (!r.ok) {
    throw await decodeApiError(r);
  }
  return (await r.json()) as T;
}

/**
 * Section 03 — resolved actions for a project. Hits
 * `GET /api/external/projects/:projectId/actions` and returns the full
 * shape including preview spec + loader diagnostics.
 */
export async function getProjectActions(
  projectId: string,
): Promise<ResolvedProjectActions> {
  return await httpJsonTyped<ResolvedProjectActions>(
    `${EXTERNAL_API}/projects/${encodeURIComponent(projectId)}/actions`,
  );
}

/**
 * Section 03 — start the project's dev preview. Returns `{url, sessionId}`
 * on success. Throws PreviewApiError for the five structured failure codes
 * (plus `preview_unknown_error` for a bug; UI surfaces as generic toast).
 */
export async function startPreview(
  projectId: string,
): Promise<{ url: string; sessionId: string }> {
  return await httpJsonTyped<{ url: string; sessionId: string }>(
    `${EXTERNAL_API}/projects/${encodeURIComponent(projectId)}/preview`,
    { method: "POST" },
  );
}

/**
 * Section 03 — invoked by the Project Wizard's "Custom" branch. Creates an
 * empty structured `.webui/actions.json` in the user's project. Idempotent
 * on the server; a repeat call is a no-op on the disk content.
 *
 * `mode` is future-proofing — today only `"custom"` is honored server-side.
 */
export async function saveActionsStub(
  projectId: string,
  mode: "custom",
): Promise<{ path: string; created: boolean }> {
  void mode; // reserved for future server-side switches
  return await httpJsonTyped<{ path: string; created: boolean }>(
    `/api/projects/${encodeURIComponent(projectId)}/actions-stub`,
    { method: "POST" },
  );
}

// -----------------------------------------------------------------------------
// Section 04 (iterate 3) — tree + file routes for the SmartViewer 3-pane body.
// Server-side ships in section 04a; the client wrappers below live here so
// every caller (FolderTree, SmartViewer, renderers) imports from one place.
// -----------------------------------------------------------------------------

export interface TreeEntry {
  name: string;
  kind: "file" | "dir";
  ignored: boolean;
}

export interface TreeResponse {
  entries: TreeEntry[];
}

/**
 * Section 04 — thrown by `fetchFileText` when either the server emits a 413
 * (file_too_large) or the client-side 1 MB cap is hit pre-flight. UI
 * components render a "File too large to preview inline" chip when they
 * catch this. Keeps renderer code free of status-code branching.
 */
export class FileTooLargeError extends Error {
  readonly maxBytes: number;
  readonly size?: number;
  readonly source: "server" | "client";
  constructor(maxBytes: number, source: "server" | "client", size?: number) {
    super("file_too_large");
    this.name = "FileTooLargeError";
    this.maxBytes = maxBytes;
    this.size = size;
    this.source = source;
  }
}

/** Client-side byte cap for text/markdown/code renderers (see plan § 7 G4 + O33). */
export const CLIENT_FILE_TEXT_MAX_BYTES = 1 * 1024 * 1024;

/**
 * Section 04 — fetch one level of the project's folder tree. `path` is a
 * project-root-relative POSIX path; the server's `pathGuard` refuses
 * traversal / absolute / drive-hop inputs.
 */
export async function fetchProjectTree(
  projectId: string,
  path?: string,
): Promise<TreeResponse> {
  const q = new URLSearchParams();
  if (path !== undefined && path !== "") q.set("path", path);
  const url = `${EXTERNAL_API}/projects/${encodeURIComponent(projectId)}/tree${
    q.size > 0 ? `?${q.toString()}` : ""
  }`;
  const r = await fetch(url);
  if (!r.ok) {
    throw await decodeApiError(r);
  }
  return (await r.json()) as TreeResponse;
}

/**
 * Section 04 — URL builder for the raw file endpoint. Used by
 * `ImageRenderer` (`<img src={fileUrl(...)}>`). No fetch here — the
 * component lets the browser stream the bytes directly.
 */
export function fileUrl(projectId: string, path: string): string {
  const q = new URLSearchParams({ path });
  return `${EXTERNAL_API}/projects/${encodeURIComponent(projectId)}/file?${q.toString()}`;
}

/**
 * Section 04 — fetch file bytes as text for the Markdown / Code / Text
 * renderers. Applies the client-side 1 MB cap (plan § 7 G4 + O33) via a
 * HEAD-first round-trip when possible; when the server returns a 413 the
 * error is rethrown as {@link FileTooLargeError}.
 *
 * Returns `{text, size}` so callers can report size in a status chip. The
 * caller is responsible for UI branching on `FileTooLargeError` — this
 * function never produces a UI string.
 */
export async function fetchFileText(
  projectId: string,
  path: string,
): Promise<{ text: string; size: number }> {
  const url = fileUrl(projectId, path);
  const r = await fetch(url);
  if (r.status === 413) {
    let payload: Record<string, unknown> = {};
    try {
      payload = (await r.json()) as Record<string, unknown>;
    } catch {
      /* swallow */
    }
    const maxBytes =
      typeof payload.maxBytes === "number"
        ? (payload.maxBytes as number)
        : 5 * 1024 * 1024;
    const size =
      typeof payload.size === "number" ? (payload.size as number) : undefined;
    throw new FileTooLargeError(maxBytes, "server", size);
  }
  if (!r.ok) {
    throw await decodeApiError(r);
  }
  const text = await r.text();
  const size = text.length;
  if (size > CLIENT_FILE_TEXT_MAX_BYTES) {
    throw new FileTooLargeError(CLIENT_FILE_TEXT_MAX_BYTES, "client", size);
  }
  return { text, size };
}
