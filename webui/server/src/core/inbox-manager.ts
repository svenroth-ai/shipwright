import { randomUUID } from "crypto";
import type { InboxItem, InboxStatus } from "../../../client/src/types/inbox.js";
import type { ChatMessage } from "../../../client/src/types/chat.js";
import type { ProcessGovernor } from "./process-governor.js";
import type { ClaudeAdapter } from "./claude-adapter.js";
import { AppError } from "../middleware/error-handler.js";

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
      for (const line of content.split("\n")) {
        if (!line.trim()) continue;
        try {
          const item = JSON.parse(line) as InboxItem;
          if (item.id && item.projectId) {
            this.items.set(item.id, item);
          }
        } catch {
          // Skip malformed lines
        }
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

  async addQuestion(
    projectId: string,
    taskId: string,
    question: string,
    context?: string,
    options?: string[],
    toolUseId?: string,
    createdAt?: string,
  ): Promise<InboxItem> {
    // Iterate 11.1 — dedupe against existing PENDING items for the
    // same task by normalized question text. Claude emits the same
    // AskUserQuestion twice in one turn (observed in iterate-9 live
    // test) with slightly different wording but semantically identical
    // questions. Iterate 9's client-side `collapseAskUserQuestionRun`
    // hides them in the chat panel, but the inbox was still showing
    // both because each had a distinct `toolu_*` id. We dedupe at
    // write time so the InboxPage, the inbox count, and any future
    // consumer all see one item. First-write-wins: the existing
    // pending item is returned unchanged, no persist, no onNotify.
    const sig = normalizeQuestion(question);
    if (sig) {
      for (const existing of this.items.values()) {
        if (
          existing.taskId === taskId &&
          existing.status === "pending" &&
          normalizeQuestion(existing.question) === sig
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
      question,
      context,
      options,
      status: "pending",
      createdAt: createdAt ?? new Date().toISOString(),
    };
    this.items.set(item.id, item);
    await this.persistItem(item);
    this.onNotify(item);
    return item;
  }

  async answer(itemId: string, answerText: string): Promise<InboxItem> {
    const item = this.items.get(itemId);
    if (!item) throw new AppError("Inbox item not found", 404);
    if (item.status === "answered") throw new AppError("Already answered", 400);

    const proc = this.governor.getProcess(item.taskId);
    if (!proc || proc.state === "exited") {
      throw new AppError("Process no longer running", 400);
    }

    // Iterate 11 REVERT: always deliver the answer as plain text on stdin.
    //
    // Iterate 7 tried to send a structured `tool_result` content block
    // via `adapter.sendUserMessage` assuming Claude CLI was blocked on
    // the pending `tool_use AskUserQuestion` call and would unblock on
    // the matching `tool_result`. That assumption was WRONG for `-p` +
    // `--input-format stream-json` mode: Claude does NOT block on
    // tool_use, the turn just keeps generating and ends with a `result`
    // event. By the time the user clicks answer, the conversation has
    // moved past the tool_use, and sending a `tool_result` as the next
    // user message violates Anthropic's API rule ("tool_result must be
    // in user message immediately after the assistant message containing
    // the matching tool_use"). Observed as API 400:
    //     "unexpected tool_use_id found in tool_result blocks ...
    //      Each tool_result block must have a corresponding tool_use
    //      block in the previous message."
    //
    // Plain-text delivery avoids the API violation entirely and still
    // reaches Claude — the model reads "Yes" / "Persönliche ToDo App"
    // as the next user turn and continues the interview. The markdown
    // fallback that Claude emits alongside the tool_use is out of our
    // control server-side; iterate 9's `collapseAskUserQuestionRun`
    // still hides it on the client.
    this.adapter.sendStdin(proc, answerText);

    // Mirror the answer as a synthetic `tool_result` ChatMessage in the
    // chat-store for `toolu_`-prefixed items so the folded tool-card
    // transitions to "Done" and the "Answered: X" state survives a
    // refresh. Purely local UI state — does NOT hit the Anthropic API.
    if (looksLikeToolUseId(item.id)) {
      const projectDir = this.projectPaths.get(item.projectId);
      if (this.chatHooks && projectDir) {
        const resultMessage: ChatMessage = {
          id: `tool-result-${item.id}-${Date.now()}`,
          taskId: item.taskId,
          type: "tool_result",
          content: answerText,
          toolUseId: item.id,
          timestamp: new Date().toISOString(),
        };
        await this.chatHooks.appendChatMessage(projectDir, item.taskId, resultMessage);
      }
    }

    item.answer = answerText;
    item.status = "answered";
    item.answeredAt = new Date().toISOString();
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
