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

  private async persistItem(item: InboxItem): Promise<void> {
    if (!this.storageDeps) return;
    const projectDir = this.projectPaths.get(item.projectId);
    if (!projectDir) return;

    const dir = `${projectDir}/.shipwright-webui`;
    this.storageDeps.mkdirSync(dir, { recursive: true });
    await this.storageDeps.appendFile(this.inboxPath(projectDir), JSON.stringify(item) + "\n");
  }

  private async rewriteProject(projectId: string): Promise<void> {
    if (!this.storageDeps) return;
    const projectDir = this.projectPaths.get(projectId);
    if (!projectDir) return;

    const dir = `${projectDir}/.shipwright-webui`;
    this.storageDeps.mkdirSync(dir, { recursive: true });

    const items = Array.from(this.items.values()).filter((i) => i.projectId === projectId);
    const content = items.map((i) => JSON.stringify(i)).join("\n") + (items.length > 0 ? "\n" : "");
    await this.storageDeps.writeFile(this.inboxPath(projectDir), content);
  }

  async addQuestion(
    projectId: string,
    taskId: string,
    question: string,
    context?: string,
    options?: string[],
    toolUseId?: string,
  ): Promise<InboxItem> {
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
      createdAt: new Date().toISOString(),
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

    // Iterate 7: when the item id is a real Anthropic `tool_use_id` (stable
    // across refresh since iterate-6), reply with a structured `tool_result`
    // content block. This is what makes Claude CLI actually unblock its
    // pending AskUserQuestion call instead of emitting the markdown fallback
    // question list. Legacy random-UUID items (pre-iterate-6) still fall
    // through to the plain-text stdin path for backwards compat.
    if (looksLikeToolUseId(item.id)) {
      this.adapter.sendUserMessage(proc, [
        { type: "tool_result", tool_use_id: item.id, content: answerText },
      ]);

      // Mirror the delivered tool_result as a ChatMessage in the chat-store
      // so (a) the folded tool-card transitions to "Done" in place, (b) the
      // "Answered: X" state survives a page refresh without relying on the
      // inbox-only store, and (c) foldToolResults has an authoritative
      // entry to consume. Only fires when chatHooks + project dir are set.
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
    } else {
      this.adapter.sendStdin(proc, answerText);
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
