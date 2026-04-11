import { useRef } from 'react';
import { ArrowDown } from 'lucide-react';
import { useChat, useSendChat } from '../../hooks/useChat';
import { useAutoScroll } from '../../hooks/useAutoScroll';
import { useStreamingChat } from '../../hooks/useStreamingChat';
import { ChatMessage } from './ChatMessage';
import { AssistantMessage } from './AssistantMessage';
import { ChatInput } from './ChatInput';

interface ChatPanelProps {
  projectId: string;
  taskId: string;
}

export function ChatPanel({ projectId, taskId }: ChatPanelProps) {
  const { data: messages = [] } = useChat(projectId, taskId);
  const sendChat = useSendChat();
  const streaming = useStreamingChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const { isAtBottom, scrollToBottom } = useAutoScroll(scrollRef, [messages, streaming.displayContent]);

  function handleSend(message: string, settings: { model: string; mode: string; effort: string }) {
    sendChat.mutate({ projectId, taskId, message, ...settings });
  }

  return (
    <div className="flex flex-col h-full" data-testid="chat-panel">
      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {streaming.isStreaming && (
          <AssistantMessage content={streaming.displayContent} isStreaming />
        )}
      </div>

      {/* Scroll to bottom button */}
      {!isAtBottom && (
        <div className="relative">
          <button
            onClick={scrollToBottom}
            className="absolute -top-10 left-1/2 -translate-x-1/2 p-2 rounded-full bg-white shadow-md border border-gray-200 hover:bg-gray-50"
            aria-label="Scroll to bottom"
          >
            <ArrowDown size={16} className="text-gray-500" />
          </button>
        </div>
      )}

      {/* Input area */}
      <ChatInput
        onSend={handleSend}
        isStreaming={streaming.isStreaming}
      />
    </div>
  );
}
