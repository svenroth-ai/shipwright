import type { ChatMessage } from '../types';
import { ToolCallCard } from '../components/chat/ToolCallCard';
import { useChatRendering } from './ChatRenderingContext';

/**
 * assistant-ui's tool-call Fallback contract:
 *
 *   { toolCallId, toolName, argsText, args, result?, isError? }
 *
 * We reconstruct a minimal `ChatMessage` from those fields so the existing
 * ToolCallCard (folded tool_use + tool_result rendering) keeps working
 * unchanged. The folded-output path (`toolOutput`) carries `result` from
 * assistant-ui through to the card's "Output" section.
 *
 * When available, we prefer the raw ChatMessage from ChatRenderingContext
 * (indexed by `toolCallId`, which matches ChatMessage.toolUseId after the
 * converter ran). The context lookup preserves fields like `model` and
 * `timestamp` that assistant-ui does not surface.
 */
interface ToolFallbackProps {
  toolCallId: string;
  toolName: string;
  args: unknown;
  result?: unknown;
  isError?: boolean;
}

function findSourceMessage(
  messagesById: Map<string, ChatMessage>,
  toolCallId: string,
): ChatMessage | undefined {
  for (const msg of messagesById.values()) {
    if (msg.type === 'tool_use' && msg.toolUseId === toolCallId) return msg;
  }
  return undefined;
}

export function ToolCallPart({
  toolCallId,
  toolName,
  args,
  result,
  isError,
}: ToolFallbackProps) {
  const { messagesById } = useChatRendering();
  const source = findSourceMessage(messagesById, toolCallId);

  const message: ChatMessage = {
    id: source?.id ?? toolCallId,
    taskId: source?.taskId ?? '',
    type: 'tool_use',
    content: '',
    toolName,
    toolInput: args,
    toolUseId: toolCallId,
    toolOutput: result,
    isError: isError === true,
    timestamp: source?.timestamp ?? new Date().toISOString(),
    ...(source?.model ? { model: source.model } : {}),
  };

  return (
    <div data-testid="tool-call-card">
      <ToolCallCard message={message} />
    </div>
  );
}
