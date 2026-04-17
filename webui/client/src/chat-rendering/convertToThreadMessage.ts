import type { ThreadMessageLike } from '@assistant-ui/react';
import type { ChatMessage } from '../types';

/**
 * Convert our stream-json derived ChatMessage into assistant-ui's
 * ThreadMessageLike. Tool_use / tool_result are correlated by toolUseId
 * (Anthropic API's id space) so assistant-ui can pair them. Thinking
 * blocks map to the `reasoning` part type (ChainOfThoughtPrimitive
 * compatible).
 *
 * Ownership contract:
 * - Message truth lives in TanStack Query cache (useChat).
 * - This function is a pure projection — no side effects, no store writes.
 * - Consumers memoize at message-id granularity, not array granularity.
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
        content: [{ type: 'reasoning', text: msg.content }],
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

/**
 * Hide system/init JSON blobs from the feed while preserving short system
 * lines ("Session started · claude-opus-4-7"). Production's legacy
 * ChatMessage.tsx used the same check — duplicated here so both old and
 * new renderers agree during the migration window.
 */
export function isSystemInitBlob(message: ChatMessage): boolean {
  if (message.type !== 'system') return false;
  if (typeof message.content !== 'string') return false;
  if (!message.content.startsWith('{')) return false;
  return message.content.includes('"subtype":"init"');
}

/**
 * The set of messages the thread should render. Filters out system/init
 * blobs (noise) while keeping other system/init-like lines.
 */
export function visibleChatMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.filter((m) => !isSystemInitBlob(m));
}
