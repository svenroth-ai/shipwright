import type { ChatMessage as ChatMessageType, TaskStatus } from '../../types';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
import { ToolCallCard } from './ToolCallCard';
import { ThinkingBlock } from './ThinkingBlock';
import { AskUserCard } from './AskUserCard';

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
  /**
   * Iterate 14.10 — task lifecycle context for AskUserCard's pause
   * indicator. ChatPanel reads it from useTask() and threads it down so
   * that an interrupted task with a pending question shows a Resume
   * button at the top of the AskUserCard, matching the TaskCard
   * affordance on the kanban.
   */
  taskStatus?: TaskStatus;
  orphanReason?: string;
  claudeSessionId?: string;
  onResume?: () => void;
}

/**
 * Detect a system/init NDJSON blob that was accidentally stored as string.
 * These are huge JSON dumps of the session config — not useful in the UI.
 */
function isSystemInitBlob(content: string): boolean {
  if (!content.startsWith('{')) return false;
  return content.includes('"type":"system"') && content.includes('"subtype":"init"');
}

export function ChatMessage({
  message,
  isStreaming,
  taskStatus,
  orphanReason,
  claudeSessionId,
  onResume,
}: ChatMessageProps) {
  // AskUserQuestion detection
  if (message.toolName === 'AskUserQuestion') {
    return (
      <AskUserCard
        message={message}
        taskStatus={taskStatus}
        orphanReason={orphanReason}
        claudeSessionId={claudeSessionId}
        onResume={onResume}
      />
    );
  }

  // Collapse result duplicates — if content exactly matches a prior assistant
  // text, the result block is just the final echo and adds noise.
  // (We still render it in case the logic is wrong, but with a dim style.)

  switch (message.type) {
    case 'user':
      return <UserMessage message={message} />;
    case 'assistant':
      return <AssistantMessage message={message} isStreaming={isStreaming} />;
    case 'result':
      // The result message is Claude's final summary — skip if it's just echoing
      // a previous assistant message (common case). For now render as assistant.
      return <AssistantMessage message={message} isStreaming={isStreaming} />;
    case 'tool_use':
    case 'tool_result':
      return <ToolCallCard message={message} />;
    case 'thinking':
      return <ThinkingBlock message={message} />;
    case 'system': {
      // Hide the giant system/init blob — not useful in chat.
      if (isSystemInitBlob(message.content)) {
        return (
          <div className="text-center text-[11px] text-gray-400 py-1">
            {message.model ? `Session started · ${message.model}` : 'Session started'}
          </div>
        );
      }
      return (
        <div className="text-center text-[11px] text-gray-400 py-1">
          {message.content}
        </div>
      );
    }
    default:
      return null;
  }
}
