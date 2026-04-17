import { randomUUID } from "crypto";
import type { InboxItem, InboxItemPart, InboxStatus } from "../../../client/src/types/inbox.js";
import type { ChatMessage } from "../../../client/src/types/chat.js";
import type { ProcessGovernor } from "./process-governor.js";
import type { ClaudeAdapter } from "./claude-adapter.js";
import { AppError } from "../middleware/error-handler.js";
import { serializePartAnswers } from "../../../client/src/lib/askUserPayload.js";

export interface InboxStoreDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  appendFile: (path: string, data: string) => Promise<void>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  // Optional: cross-process file lock + file-exists guard. Prevents a
  // new-question append from colliding with a concurrent answer rewrite
  // on the same inbox.jsonl. Omitted in unit tests.
  lock?: (path: string) => Promise<() => Promise<void>>;
  ensureFile?: (path: string) => void;
}

/** Hooks the inbox manager uses to persist the synthetic `tool_result`
 *  chat message when a real `toolu_`-prefixed AskUserQuestion answer is
 *  delivered. Optional — when omitted, the answer is still delivered to
 *  Claude but no chat-store entry is written. Constructor-injected so
 *  tests can mock without touching the filesystem. */
export interface InboxChatHooks {
  appendChatMessage: (projectDir: string, taskId: string, message: ChatMessage) => Promise<void>;
}

/** Returns true when the inbox item id is an Anthropic `tool_use_id`
 *  (added in iterate-6). These ids are stable across refreshes and are
 *  what the Claude CLI needs as the `tool_use_id` field in a tool_result
 *  content block to unblock its current AskUserQuestion call. */
function looksLikeToolUseId(id: string): boolean {
  return id.startsWith("toolu_");
}

/** Iterate 11.1 — normalize a question string so that Claude's
 *  same-turn duplicate AskUserQuestions collapse to one inbox item.
 *  Strip case + whitespace + punctuation so small variations like
 *  "Was für eine App?" vs "was FÜR eine App" vs "Was für eine App!"
 *  all produce the same signature. */
function normalizeQuestion(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9äöüß]/g, "");
}

/** Iterate 14.2 — dedupe signature for a multi-part item. Joins all part
 *  questions so an item asking {A, B} collapses with another item asking
 *  {A, B} but NOT with one asking {A, C}. */
function inboxItemSignature(item: InboxItem): string {
  return item.parts.map((p) => normalizeQuestion(p.question)).join("|");
}

/**
 * Input shape for `addQuestion`. Either pass a ready-made `parts` array,
 * OR fall back to the legacy single-question args for replay/backwards-compat.
 * Iterate 14.2: new callers should always pass `parts`.
 */
export interface AddQuestionInput {
  projectId: string;
  taskId: string;
  parts: InboxItemPart[];
  toolUseId?: string;
  createdAt?: string;
}

export class InboxManager {
  private items = new Map<string, InboxItem>();
  private storageDeps?: InboxStoreDeps;
  private chatHooks?: InboxChatHooks;
  private projectPaths = new Map<string, string>(); // projectId -> projectDir

  constructor(
    private governor: ProcessGovernor,
    private adapter: ClaudeAdapter,
    private onNotify: (item: InboxItem) => void,
    storageDeps?: InboxStoreDeps,
    chatHooks?: InboxChatHooks,
  ) {
    this.storageDeps = storageDeps;
    this.chatHooks = chatHooks;
  }

  registerProject(projectId: string, projectDir: string): void {
    this.projectPaths.set(projectId, projectDir);
  }

  private inboxPath(projectDir: string): string {
    return `${projectDir}/.shipwright-webui/inbox.jsonl`;
  }

  async loadFromDisk(projectId: string, projectDir: string): Promise<void> {
    this.projectPaths.set(projectId, projectDir);
    if (!this.storageDeps) return;

    const filePath = this.inboxPath(projectDir);
    if (!this.storageDeps.existsSync(filePath)) return;

    try {
      const content = await this.storageDeps.readFile(filePath, "utf-8");
      // Iterate 14.2 — per-line schema validation. Any entry that lacks a
      // `parts` array is a v1 legacy entry (the old `{ question, options,
      // answer }` shape). We skip it, count it as purged, and rewrite the
      // file once at the end so the jsonl ends up in a clean v2 state.
      //
      // Rewrite does NOT wipe the whole file — it keeps every entry that
      // survived validation. Robust against partial writes or mixed-schema
      // files during dev.
      let purgedCount = 0;
      let retainedCount = 0;
      for (const line of content.split("\n")) {
        if (!line.trim()) continue;
        try {
          const parsed = JSON.parse(line) as unknown;
          if (!parsed || typeof parsed !== "object") {
            purgedCount++;
            continue;
          }
          const candidate = parsed as Partial<InboxItem>;
          if (!candidate.id || !candidate.projectId) {
            purgedCount++;
            continue;
          }
          if (!Array.isArray(candidate.parts)) {
            // v1 legacy — has `question`/`options`/`answer` at the top
            // level. Skip entirely; user confirmed no backward-compat.
            purgedCount++;
            continue;
          }
          this.items.set(candidate.id, candidate as InboxItem);
          retainedCount++;
        } catch {
          // Malformed JSON line — skip but do NOT count as purge
          // (existing behavior preserved).
        }
      }

      if (purgedCount > 0) {
        console.warn(JSON.stringify({
          level: "warn",
          message: `Inbox: purged ${purgedCount} legacy entries on schema upgrade, ${retainedCount} v2 entries retained.`,
          projectId,
        }));
        // Rewrite file to drop the v1 entries for good.
        await this.rewriteProject(projectId);
      }
    } catch {
      // File read error — start fresh
    }
  }

  /** Serializes any write (append or rewrite) against the inbox file so
   *  a concurrent addQuestion-append can't be clobbered by an answer-
   *  driven rewriteProject. The lock is shared across both code paths
   *  since they target the same inbox.jsonl path. */
  private async withInboxLock<T>(filePath: string, writer: () => Promise<T>): Promise<T> {
    const deps = this.storageDeps!;
    if (deps.ensureFile) deps.ensureFile(filePath);
    if (!deps.lock) return writer();
    const release = await deps.lock(filePath);
    try {
      return await writer();
    } finally {
      await release();
    }
  }

  private async persistItem(item: InboxItem): Promise<void> {
    if (!this.storageDeps) return;
    const projectDir = this.projectPaths.get(item.projectId);
    if (!projectDir) return;

    const dir = `${projectDir}/.shipwright-webui`;
    this.storageDeps.mkdirSync(dir, { recursive: true });
    const filePath = this.inboxPath(projectDir);
    await this.withInboxLock(filePath, () =>
      this.storageDeps!.appendFile(filePath, JSON.stringify(item) + "\n")
    );
  }

  private async rewriteProject(projectId: string): Promise<void> {
    if (!this.storageDeps) return;
    const projectDir = this.projectPaths.get(projectId);
    if (!projectDir) return;

    const dir = `${projectDir}/.shipwright-webui`;
    this.storageDeps.mkdirSync(dir, { recursive: true });

    const items = Array.from(this.items.values()).filter((i) => i.projectId === projectId);
    const content = items.map((i) => JSON.stringify(i)).join("\n") + (items.length > 0 ? "\n" : "");
    const filePath = this.inboxPath(projectDir);
    await this.withInboxLock(filePath, () =>
      this.storageDeps!.writeFile(filePath, content)
    );
  }

  /**
   * Iterate 14.2 — takes a full `parts` array (one per question in the
   * underlying AskUserQuestion tool_use). Dedupes against existing pending
   * items for the same task by the joined signature of all part questions.
   */
  async addQuestion(input: AddQuestionInput): Promise<InboxItem> {
    const { projectId, taskId, parts, toolUseId, createdAt } = input;

    if (!Array.isArray(parts) || parts.length === 0) {
      throw new AppError("addQuestion requires at least one part", 400);
    }

    // Iterate 11.1 + 14.2 — dedupe against existing PENDING items for the
    // same task by normalized signature (joined question text across all
    // parts). Claude occasionally emits the same AskUserQuestion twice in
    // one turn with slightly different wording but semantically identical
    // content. First-write-wins: the existing pending item is returned
    // unchanged, no persist, no onNotify.
    const sig = parts.map((p) => normalizeQuestion(p.question)).join("|");
    if (sig && sig.replace(/\|/g, "")) {
      for (const existing of this.items.values()) {
        if (
          existing.taskId === taskId &&
          existing.status === "pending" &&
          inboxItemSignature(existing) === sig
        ) {
          return existing;
        }
      }
    }

    // Prefer the stable Anthropic tool_use_id over a fresh random UUID so the
    // client's ChatMessage.toolUseId can find the item back after a refresh
    // (and so the iterate-7 tool_result refactor has a correlation key for
    // free). Fall back to a random id only when toolUseId is missing.
    const item: InboxItem = {
      id: toolUseId ?? randomUUID(),
      projectId,
      taskId,
      parts: parts.map((p) => ({ ...p })),
      status: "pending",
      createdAt: createdAt ?? new Date().toISOString(),
    };
    this.items.set(item.id, item);
    await this.persistItem(item);
    this.onNotify(item);
    return item;
  }

  /**
   * Iterate 14.2 — answer accepts a list of per-part answers indexed by
   * `partIndex`. It fills them into the item's `parts[]`, requires ALL
   * parts to end up answered, joins them with `serializePartAnswers`, and
   * ships ONE tool_result to Claude CLI via the existing stdin path.
   */
  async answer(itemId: string, answers: Array<{ index: number; answer: string }>): Promise<InboxItem> {
    const item = this.items.get(itemId);
    if (!item) throw new AppError("Inbox item not found", 404);
    if (item.status === "answered") throw new AppError("Already answered", 400);

    const proc = this.governor.getProcess(item.taskId);
    if (!proc || proc.state === "exited") {
      throw new AppError("Process no longer running", 400);
    }

    // Write the incoming answers into their parts slots (in place).
    const nowIso = new Date().toISOString();
    for (const { index, answer } of answers) {
      if (index < 0 || index >= item.parts.length) {
        throw new AppError(`answer index ${index} out of range`, 400);
      }
      item.parts[index].answer = answer;
      item.parts[index].answeredAt = nowIso;
    }

    // Validate every part now has an answer (even empty string is allowed;
    // it renders as "(skipped)" in the serialized tool_result).
    const missing = item.parts.findIndex((p) => p.answer === undefined);
    if (missing >= 0) {
      throw new AppError(`part ${missing} still unanswered`, 400);
    }

    const joined = serializePartAnswers(item.parts);

    // Iterate 11 REVERT: always deliver the joined answer as plain text on
    // stdin. See the long comment on iterate 11 below for why structured
    // tool_result content blocks fail. We still use the joined markdown
    // format — Claude reads it as the next user turn and picks up all N
    // answers in one go.
    //
    // Iterate 14.14 (Bug 2 observability): log the delivery so a future
    // "answer submitted but Claude never responds" report can be traced
    // to the process state + content at submit time. Keep the log
    // structured (JSON) so it's greppable in prod.
    console.info(JSON.stringify({
      level: "info",
      source: "inbox-manager",
      message: "Delivering AskUserQuestion answer to Claude stdin",
      taskId: item.taskId,
      itemId: item.id,
      notBlocked: item.notBlocked === true,
      partCount: item.parts.length,
      processState: proc.state,
      processPid: proc.pid,
    }));
    this.adapter.sendStdin(proc, joined);

    // Mirror the joined answer as a synthetic `tool_result` ChatMessage in
    // the chat-store for `toolu_`-prefixed items so the folded tool-card
    // transitions to "Done" and the "Answered: X" state survives a refresh.
    // Purely local UI state — does NOT hit the Anthropic API.
    if (looksLikeToolUseId(item.id)) {
      const projectDir = this.projectPaths.get(item.projectId);
      if (this.chatHooks && projectDir) {
        const resultMessage: ChatMessage = {
          id: `tool-result-${item.id}-${Date.now()}`,
          taskId: item.taskId,
          type: "tool_result",
          content: joined,
          toolUseId: item.id,
          timestamp: nowIso,
        };
        await this.chatHooks.appendChatMessage(projectDir, item.taskId, resultMessage);
      }
    }

    item.status = "answered";
    item.answeredAt = nowIso;
    await this.rewriteProject(item.projectId);
    return item;
  }

  /**
   * Iterate 14.5 — mark an inbox item as `notBlocked`. Called by the
   * SSE-handler in index.ts when Claude continues generating after an
   * AskUserQuestion without waiting for the user's answer, or when the
   * turn ends before a matching tool_result arrives. First-write-wins:
   * flipping an already-flagged item is a no-op to avoid redundant
   * rewrites. Persists the mutation to inbox.jsonl so the flag survives
   * a server restart or page reload.
   *
   * Lives on InboxManager instead of inside `addQuestion` because 14.2's
   * dedupe swallows second AskUserQuestions in the same turn — the inbox
   * manager never sees them. Detection has to live in the SSE handler
   * which tracks per-turn pending tool_use IDs and calls us back here.
   */
  async setNotBlocked(itemId: string, value: boolean): Promise<InboxItem | undefined> {
    const item = this.items.get(itemId);
    if (!item) return undefined;
    if (item.notBlocked === value) return item;
    item.notBlocked = value;
    // Persist via rewrite — same pattern as `answer()`. A line-in-place
    // patch would be nicer but the jsonl layout doesn't make that trivial
    // and rewrite is already the existing mutation-persist pattern.
    await this.rewriteProject(item.projectId);
    return item;
  }

  getAll(filter?: { status?: InboxStatus }): InboxItem[] {
    let items = Array.from(this.items.values());
    if (filter?.status) {
      items = items.filter((i) => i.status === filter.status);
    }
    return items.sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );
  }

  getByProject(projectId: string): InboxItem[] {
    return Array.from(this.items.values()).filter((i) => i.projectId === projectId);
  }

  getById(itemId: string): InboxItem | undefined {
    return this.items.get(itemId);
  }
}
