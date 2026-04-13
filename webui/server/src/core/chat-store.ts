import type { ChatMessage } from "../../../client/src/types/chat.js";

export interface ChatStoreDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  appendFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}

/**
 * Migrate a legacy message where content is a JSON-stringified Claude CLI
 * message object (pre-chat-rendering format) into properly typed messages.
 * Old format: { type: "assistant", content: '{"model":"...","content":[{"type":"text","text":"..."}]}' }
 * New format: separate messages for each content block with extracted text.
 */
function migrateLegacyMessage(msg: ChatMessage): ChatMessage[] {
  // Only migrate assistant messages with JSON-blob content
  if (msg.type !== "assistant" || !msg.content.startsWith("{")) {
    return [msg];
  }

  try {
    const parsed = JSON.parse(msg.content);
    // Check if this looks like a Claude CLI message object
    if (!parsed.content || !Array.isArray(parsed.content)) {
      return [msg];
    }

    const model = parsed.model as string | undefined;
    const results: ChatMessage[] = [];
    let counter = 0;

    for (const block of parsed.content) {
      if (block.type === "text" && typeof block.text === "string") {
        results.push({
          ...msg,
          id: `${msg.id}-migrated-${counter++}`,
          type: "assistant",
          content: block.text,
          model,
        });
      } else if (block.type === "tool_use") {
        results.push({
          ...msg,
          id: `${msg.id}-migrated-${counter++}`,
          type: "tool_use",
          content: "",
          toolName: block.name,
          toolInput: block.input,
          model,
        });
      } else if (block.type === "thinking" && typeof block.thinking === "string") {
        results.push({
          ...msg,
          id: `${msg.id}-migrated-${counter++}`,
          type: "thinking",
          content: block.thinking,
          model,
        });
      }
    }

    return results.length > 0 ? results : [msg];
  } catch {
    return [msg];
  }
}

/** Defense-in-depth: remember the last few signatures per task so we can
 *  drop exact structural duplicates that sneak through the parser. */
const DEDUPE_WINDOW_SIZE = 8;
const DEDUPE_WINDOW_MS = 10_000;

interface RecentEntry {
  signature: string;
  at: number;
}

function signatureOf(message: ChatMessage): string {
  const toolInputKey = message.toolInput === undefined ? "" : JSON.stringify(message.toolInput);
  return [
    message.type,
    message.toolName ?? "",
    message.content,
    toolInputKey,
    message.isError ? "err" : "",
  ].join("\x1f");
}

export class ChatStore {
  constructor(private deps: ChatStoreDeps) {}

  private basePath(projectDir: string): string {
    return `${projectDir}/.shipwright-webui/chat-history`;
  }

  /** Per-task rolling window of the most recently appended message signatures. */
  private recent = new Map<string, RecentEntry[]>();

  async append(projectDir: string, taskId: string, message: ChatMessage): Promise<void> {
    const base = this.basePath(projectDir);
    this.deps.mkdirSync(base, { recursive: true });

    const key = `${projectDir}::${taskId}`;
    const now = Date.now();
    const sig = signatureOf(message);
    const recent = this.recent.get(key) ?? [];

    // Drop entries older than the window
    const fresh = recent.filter((e) => now - e.at <= DEDUPE_WINDOW_MS);

    if (fresh.some((e) => e.signature === sig)) {
      // Exact duplicate within the dedupe window → skip. Keeps the append-only
      // chat-history lossless at the `rm` level (disk state is what it is) but
      // shields us from double-persistence bugs upstream. See ADR-016.
      this.recent.set(key, fresh);
      return;
    }

    fresh.push({ signature: sig, at: now });
    while (fresh.length > DEDUPE_WINDOW_SIZE) fresh.shift();
    this.recent.set(key, fresh);

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
          // Migrate legacy JSON-blob messages to new format
          const migrated = migrateLegacyMessage(parsed as ChatMessage);
          messages.push(...migrated);
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
