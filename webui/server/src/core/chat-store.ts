import type { ChatMessage } from "../../../client/src/types/chat.js";

export interface ChatStoreDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  appendFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}

export class ChatStore {
  constructor(private deps: ChatStoreDeps) {}

  private basePath(projectDir: string): string {
    return `${projectDir}/.shipwright-webui/chat-history`;
  }

  async append(projectDir: string, taskId: string, message: ChatMessage): Promise<void> {
    const base = this.basePath(projectDir);
    this.deps.mkdirSync(base, { recursive: true });
    await this.deps.appendFile(`${base}/${taskId}.jsonl`, JSON.stringify(message) + "\n");
  }

  async load(projectDir: string, taskId: string): Promise<ChatMessage[]> {
    const filePath = `${this.basePath(projectDir)}/${taskId}.jsonl`;
    if (!this.deps.existsSync(filePath)) return [];

    const content = await this.deps.readFile(filePath, "utf-8");
    const messages: ChatMessage[] = [];

    for (const line of content.split("\n")) {
      if (!line.trim()) continue;
      try {
        const parsed = JSON.parse(line);
        if (parsed.id && parsed.timestamp) {
          messages.push(parsed as ChatMessage);
        }
      } catch {
        // Skip malformed lines
      }
    }

    return messages.sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }

  exists(projectDir: string, taskId: string): boolean {
    return this.deps.existsSync(`${this.basePath(projectDir)}/${taskId}.jsonl`);
  }
}
