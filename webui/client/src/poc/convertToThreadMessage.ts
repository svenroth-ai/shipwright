import type { ThreadMessageLike } from '@assistant-ui/react';
import type { ChatMessage } from '../types';

/**
 * PoC — convert our stream-json derived ChatMessage into assistant-ui's
 * ThreadMessageLike. Tool_use / tool_result are correlated by toolUseId
 * (Anthropic API's id space) so assistant-ui can pair them. Thinking blocks
 * map to the `reasoning` part type (ChainOfThoughtPrimitive compatible).
 */
export function convertToThreadMessage(msg: ChatMessage): ThreadMessageLike {
  const createdAt = msg.timestamp ? new Date(msg.timestamp) : new Date();

  switch (msg.type) {
    case 'user':
      return {
        id: msg.id,
        role: 'user',
        content: [{ type: 'text', text: msg.content }],
        createdAt,
      };

    case 'assistant':
    case 'result':
      return {
        id: msg.id,
        role: 'assistant',
        content: [{ type: 'text', text: msg.content }],
        createdAt,
      };

    case 'thinking':
      return {
        id: msg.id,
        role: 'assistant',
        content: [
          // assistant-ui's reasoning part type renders via ChainOfThoughtPrimitive.
          { type: 'reasoning', text: msg.content },
        ],
        createdAt,
      };

    case 'tool_use':
      return {
        id: msg.id,
        role: 'assistant',
        content: [
          {
            type: 'tool-call',
            toolCallId: msg.toolUseId ?? msg.id,
            toolName: msg.toolName ?? 'unknown',
            // assistant-ui types args as ReadonlyJSONObject. Cast via unknown
            // — we can't narrow the NDJSON tool_input further without schema
            // knowledge of the tool. Safe because we only render as JSON.
            args: (msg.toolInput ?? {}) as never,
          },
        ],
        createdAt,
      };

    case 'tool_result':
      return {
        id: msg.id,
        role: 'assistant',
        content: [
          {
            type: 'tool-call',
            toolCallId: msg.toolUseId ?? msg.id,
            toolName: 'result',
            args: {},
            result: msg.content,
            isError: msg.isError === true,
          },
        ],
        createdAt,
      };

    case 'system':
      // system/init blobs and other system events are rendered as plain text;
      // the outer ChatPanel hides the giant system-init JSON dump separately.
      return {
        id: msg.id,
        role: 'system',
        content: [{ type: 'text', text: msg.content }],
        createdAt,
      };

    default:
      return {
        id: msg.id,
        role: 'assistant',
        content: [{ type: 'text', text: msg.content }],
        createdAt,
      };
  }
}
