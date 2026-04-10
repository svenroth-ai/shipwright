import { randomUUID } from "crypto";
import type { InboxItem, InboxStatus } from "../../../client/src/types/inbox.js";
import type { ProcessGovernor } from "./process-governor.js";
import type { ClaudeAdapter } from "./claude-adapter.js";
import { AppError } from "../middleware/error-handler.js";

export class InboxManager {
  private items = new Map<string, InboxItem>();

  constructor(
    private governor: ProcessGovernor,
    private adapter: ClaudeAdapter,
    private onNotify: (item: InboxItem) => void
  ) {}

  addQuestion(
    projectId: string,
    taskId: string,
    question: string,
    context?: string,
    options?: string[]
  ): InboxItem {
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
    this.onNotify(item);
    return item;
  }

  answer(itemId: string, answerText: string): InboxItem {
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
