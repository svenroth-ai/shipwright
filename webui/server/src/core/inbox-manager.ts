import { randomUUID } from "crypto";
import type { InboxItem, InboxStatus } from "../../../client/src/types/inbox.js";
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

export class InboxManager {
  private items = new Map<string, InboxItem>();
  private storageDeps?: InboxStoreDeps;
  private projectPaths = new Map<string, string>(); // projectId -> projectDir

  constructor(
    private governor: ProcessGovernor,
    private adapter: ClaudeAdapter,
    private onNotify: (item: InboxItem) => void,
    storageDeps?: InboxStoreDeps
  ) {
    this.storageDeps = storageDeps;
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
    options?: string[]
  ): Promise<InboxItem> {
    const item: InboxItem = {
      id: randomUUID(),
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

    this.adapter.sendStdin(proc, answerText);
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
