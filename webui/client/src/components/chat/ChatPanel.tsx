import { useRef, useState, useCallback } from 'react';
import { ArrowDown, AlertCircle } from 'lucide-react';
import { useChat, useSendChat } from '../../hooks/useChat';
import { useAutoScroll } from '../../hooks/useAutoScroll';
import { useStreamingChat } from '../../hooks/useStreamingChat';
import { useStreamingSSE } from '../../hooks/useStreamingSSE';
import { useProject } from '../../hooks/useProjects';
import { useSettings } from '../../hooks/useSettings';
import { ChatMessage } from './ChatMessage';
import { AssistantMessage } from './AssistantMessage';
import { ChatInput } from './ChatInput';
import { ApiError } from '../../lib/api';
import type { AutonomyOption } from '../../types/settings';

interface ChatPanelProps {
  projectId: string;
  taskId: string;
}

/**
 * Filter out duplicate "result" messages that echo the preceding assistant
 * text. Claude CLI emits both an assistant event and a final result event
 * with the same content — rendering both is noise.
 */
function dedupeMessages(messages: import('../../types').ChatMessage[]): import('../../types').ChatMessage[] {
  const out: typeof messages = [];
  for (const msg of messages) {
    if (msg.type === 'result') {
      const prev = out[out.length - 1];
      if (prev && prev.type === 'assistant' && prev.content === msg.content) {
        continue; // skip duplicate
      }
    }
    out.push(msg);
  }
  return out;
}

/**
 * Determine whether we should show the "waiting for Claude" indicator.
 * Shows immediately when:
 *   - The SSE stream is active (Claude is producing output), OR
 *   - The last persisted message is a user message (follow-up in flight), OR
 *   - The send mutation is pending (network round-trip)
 *
 * This avoids the long delay where the user sees nothing between clicking
 * Send and Claude CLI starting to produce NDJSON (~5–10s cold start).
 */
function isAwaitingResponse(
  messages: import('../../types').ChatMessage[],
  sendPending: boolean,
  streaming: boolean,
): boolean {
  if (streaming) return true;
  if (sendPending) return true;
  const last = messages[messages.length - 1];
  return last?.type === 'user';
}

export function ChatPanel({ projectId, taskId }: ChatPanelProps) {
  const { data: rawMessages = [] } = useChat(projectId, taskId);
  const messages = dedupeMessages(rawMessages);
  const { data: project } = useProject(projectId);
  const { data: globalSettings } = useSettings();
  const sendChat = useSendChat();
  const streaming = useStreamingChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const awaiting = isAwaitingResponse(messages, sendChat.isPending, streaming.isStreaming);
  const { isAtBottom, scrollToBottom } = useAutoScroll(scrollRef, [messages, streaming.displayContent, streaming.streamingMessages, awaiting]);
  const [chatError, setChatError] = useState<string | null>(null);

  const autonomy: AutonomyOption = project?.settings?.autonomy ?? globalSettings?.defaultAutonomy ?? 'guided';

  // Wire SSE events into the streaming hook for real-time display
  const handleStreamMessage = useCallback(
    (tid: string, msg: import('../../types').NdjsonMessage) => {
      streaming.processNdjsonMessage(tid, msg);
    },
    [streaming.processNdjsonMessage],
  );
  const handleStreamStart = useCallback(() => streaming.startStream(), [streaming.startStream]);
  const handleStreamEnd = useCallback(() => streaming.endStream(), [streaming.endStream]);
  useStreamingSSE(taskId, handleStreamMessage, handleStreamStart, handleStreamEnd);

  function handleSend(payload: import('./ChatInput').ChatSendPayload) {
    setChatError(null);
    sendChat.mutate(
      {
        projectId,
        taskId,
        message: payload.message,
        ...(payload.images ? { images: payload.images } : {}),
        model: payload.model,
        mode: payload.mode,
        effort: payload.effort,
        autonomy: payload.autonomy,
      },
      {
        onError: (err) => {
          if (err instanceof ApiError && err.status === 400) {
            setChatError('Task is not running. Start the task first using the Start button on the board.');
          } else {
            setChatError(err instanceof Error ? err.message : 'Failed to send message');
          }
        },
      }
    );
  }

  return (
    <div
      className="flex flex-col h-full min-w-0 overflow-hidden"
      style={{ background: 'var(--color-bg, #f5f0eb)' }}
      data-testid="chat-panel"
    >
      {/* Message list — warm beige background, vertical scroll only */}
      <div
        ref={scrollRef}
        className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden px-6 py-5 flex flex-col gap-[18px]"
      >
        {messages.length === 0 && !awaiting && (
          <div className="text-center text-gray-400 text-sm py-8">
            <p>No messages yet.</p>
            <p className="text-xs mt-1">Start the task to begin chatting with Claude.</p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {/* Streaming: real-time tool calls, thinking, streamed text */}
        {streaming.isStreaming &&
          streaming.streamingMessages.map((msg) => <ChatMessage key={msg.id} message={msg} />)}
        {streaming.isStreaming && streaming.displayContent && (
          <AssistantMessage content={streaming.displayContent} isStreaming />
        )}

        {/* Awaiting response indicator — shows whenever we're waiting for Claude
            output, including the cold-start gap before SSE starts streaming. */}
        {awaiting && !streaming.displayContent && (
          <AssistantMessage content="" isStreaming />
        )}
      </div>

      {/* Error banner */}
      {chatError && (
        <div className="mx-3 mb-2 flex items-start gap-2 px-3 py-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertCircle size={14} className="shrink-0 mt-0.5" />
          <span>{chatError}</span>
          <button className="ml-auto text-amber-500 hover:text-amber-700" onClick={() => setChatError(null)}>x</button>
        </div>
      )}

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

      {/* Input area — disable while awaiting (prevents double-send race) */}
      <ChatInput
        onSend={handleSend}
        isStreaming={awaiting}
        autonomy={autonomy}
      />
    </div>
  );
}
