import type { ChatMessage } from '../types';
import { ToolCallCard } from '../components/chat/ToolCallCard';
import { AskUserCard } from '../components/chat/AskUserCard';
import { useChatRendering } from './ChatRenderingContext';

/**
 * assistant-ui's tool-call Fallback contract:
 *
 *   { toolCallId, toolName, argsText, args, result?, isError? }
 *
 * We dispatch by `toolName`:
 *  - `AskUserQuestion` → AskUserCard (Sub-iterate B: first-class custom
 *    tool UI — renders inline in the thread as a composer prompt rather
 *    than a generic collapsible card).
 *  - everything else → ToolCallCard (legacy shape).
 *
 * The raw ChatMessage (for timestamps, model, images) is looked up from
 * ChatRenderingContext by `toolCallId`, which matches
 * `ChatMessage.toolUseId` after the converter has run.
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
  const { messagesById, taskStatus, orphanReason, claudeSessionId, onResume } = useChatRendering();
  const source = findSourceMessage(messagesById, toolCallId);

  if (toolName === 'AskUserQuestion') {
    const askMessage: ChatMessage = source ?? {
      id: toolCallId,
      taskId: '',
      type: 'tool_use',
      content: '',
      toolName,
      toolInput: args,
      toolUseId: toolCallId,
      timestamp: new Date().toISOString(),
    };
    return (
      <AskUserCard
        message={askMessage}
        taskStatus={taskStatus}
        orphanReason={orphanReason}
        claudeSessionId={claudeSessionId}
        onResume={onResume}
      />
    );
  }

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
