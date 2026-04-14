import type { NdjsonMessage, ChatMessage } from "../../../client/src/types/chat.js";
import type { SSEEvent } from "../../../client/src/types/sse.js";

/**
 * Iterate 13: extract + broadcast + persist helper.
 *
 * Extracts each NDJSON assistant event into one or more ChatMessages, then
 * broadcasts each one individually over SSE with `payload.message: ChatMessage`.
 * The SSE id space now matches the REST GET /chat id space, so clients can
 * dedupe by id using mergeCommitted.
 *
 * Extracted into its own file so we can unit-test the routing logic without
 * spinning up the full Hono server and ClaudeAdapter wiring. See plan
 * vast-mapping-petal.md.
 */
export interface BroadcastDeps {
  sseManager: { broadcast(event: SSEEvent): void };
  chatStore: { append(projectDir: string, taskId: string, msg: ChatMessage): Promise<void> };
}

export interface BroadcastContext {
  taskId: string;
  projectId: string | undefined;
  projectPath: string | undefined;
  msg: NdjsonMessage;
  chatMessages: ChatMessage[];
}

export function broadcastAndPersistChat(
  ctx: BroadcastContext,
  deps: BroadcastDeps,
): void {
  const { taskId, projectId, projectPath, chatMessages } = ctx;
  if (chatMessages.length === 0) return;

  for (const chatMsg of chatMessages) {
    if (projectPath) {
      deps.chatStore.append(projectPath, taskId, chatMsg).catch((err) =>
        console.error(JSON.stringify({ level: "error", message: "Chat persist error", error: String(err) })),
      );
    }
    deps.sseManager.broadcast({
      type: "chat:message",
      payload: { taskId, projectId, message: chatMsg },
      timestamp: chatMsg.timestamp,
    });
  }
}
