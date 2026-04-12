import type { ChatMessage as ChatMessageType } from '../../types';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
import { ToolCallCard } from './ToolCallCard';
import { ThinkingBlock } from './ThinkingBlock';
import { AskUserCard } from './AskUserCard';

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  // AskUserQuestion detection
  if (message.toolName === 'AskUserQuestion') {
    return <AskUserCard message={message} />;
  }

  switch (message.type) {
    case 'user':
      return <UserMessage message={message} />;
    case 'assistant':
    case 'result':
      return <AssistantMessage message={message} isStreaming={isStreaming} />;
    case 'tool_use':
    case 'tool_result':
      return <ToolCallCard message={message} />;
    case 'thinking':
      return <ThinkingBlock message={message} />;
    case 'system':
      return (
        <div className="text-center text-xs text-gray-400 py-2">
          {message.model && (
            <span className="font-medium text-gray-500">{message.model} · </span>
          )}
          {message.content}
        </div>
      );
    default:
      return null;
  }
}
