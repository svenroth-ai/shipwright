import type { NdjsonMessage, ChatMessage } from "../../../client/src/types/chat.js";
import type { SSEEvent } from "../../../client/src/types/sse.js";

/**
 * Iterate 13 / Phase 0: extract + broadcast + persist helper.
 *
 * Two modes, gated by SHIPWRIGHT_NEW_CHAT_PROTOCOL:
 * - new protocol (flag=1): extract ChatMessages first, then broadcast each one
 *   individually with `payload.message: ChatMessage`. Same stable id space as
 *   REST GET /chat so clients can dedupe by id.
 * - legacy (flag=0): broadcast raw NdjsonMessage, persist extracted ChatMessages.
 *   Kept for rollback until the client fully migrates.
 *
 * Extracted into its own file so we can unit-test the routing logic without
 * spinning up the full Hono server and ClaudeAdapter wiring. See plan
 * vast-mapping-petal.md section "Phase 0".
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
  newProtocol: boolean,
): void {
  const { taskId, projectId, projectPath, msg, chatMessages } = ctx;

  if (newProtocol) {
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
    return;
  }

  // Legacy path.
  deps.sseManager.broadcast({
    type: "chat:message",
    payload: { taskId, projectId, message: msg },
    timestamp: new Date().toISOString(),
  });
  if (chatMessages.length > 0 && projectPath) {
    for (const chatMsg of chatMessages) {
      deps.chatStore.append(projectPath, taskId, chatMsg).catch((err) =>
        console.error(JSON.stringify({ level: "error", message: "Chat persist error", error: String(err) })),
      );
    }
  }
}
