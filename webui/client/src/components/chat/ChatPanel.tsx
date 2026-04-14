import { useRef, useState, useEffect, useMemo } from 'react';
import { ArrowDown, AlertCircle } from 'lucide-react';
import { useChat, useSendChat, useRefetchChatOnResume } from '../../hooks/useChat';
import { useAutoScroll } from '../../hooks/useAutoScroll';
import { useTurnStatus } from '../../hooks/useTurnStatus';
import { useProject } from '../../hooks/useProjects';
import { useSettings } from '../../hooks/useSettings';
import { ChatMessage } from './ChatMessage';
import { AssistantMessage } from './AssistantMessage';
import { ChatInput } from './ChatInput';
import { ApiError } from '../../lib/api';
import { foldToolResults } from '../../lib/foldToolResults';
import { collapseAskUserQuestionRun } from '../../lib/collapseAskUserQuestion';
import { useTurnStatusStore, taskKeyOf } from '../../stores/turnStatusStore';
import { ChatAwaitingContext } from '../../contexts/ChatAwaitingContext';
import type { AutonomyOption } from '../../types/settings';

interface ChatPanelProps {
  projectId: string;
  taskId: string;
}

/**
 * Iterate 13: ChatPanel now reads committed messages from a single source
 * (the TanStack Query cache fed by useSSE via setQueryData + mergeCommitted)
 * and per-turn lifecycle from turnStatusStore. The dual-render pipeline
 * (persisted + streamingMessages with dedupe) is gone; ADR-016/018 band-aids
 * deleted. See plan vast-mapping-petal.md.
 *
 * Keep the existing dedupeMessages helper as a render-time filter against
 * result/assistant echoes — the server emits both and they carry distinct
 * ids, so mergeCommitted correctly keeps both; this filter hides the dupe
 * visually.
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

export function ChatPanel({ projectId, taskId }: ChatPanelProps) {
  const { data: rawMessages = [] } = useChat(projectId, taskId);
  useRefetchChatOnResume(projectId, taskId);
  // Fold tool_result into tool_use, then dedupe result/assistant echoes,
  // then collapse Claude's AskUserQuestion fallback run (iterate 9).
  const messages = collapseAskUserQuestionRun(
    dedupeMessages(foldToolResults(rawMessages)),
  );

  const { data: project } = useProject(projectId);
  const { data: globalSettings } = useSettings();
  const sendChat = useSendChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Iterate 13: turn lifecycle state. Lives in Zustand so it survives
  // ChatPanel unmount (task switch), fixing the round-2 task-switch amnesia
  // concern. useSSE dispatches transitions when chat:message and
  // task:updated events arrive.
  const turn = useTurnStatus(projectId, taskId);

  // Iterate 7 — inbox-answer latency. Local boolean flipped by
  // AskUserCard.handleSubmit via ChatAwaitingContext so the "Thinking…"
  // indicator fires immediately on answer submit. Cleared when a real
  // streaming event arrives (turn.status transitions into streaming).
  const [awaitingFromInbox, setAwaitingFromInbox] = useState(false);
  useEffect(() => {
    if (turn.status === 'streaming') setAwaitingFromInbox(false);
  }, [turn.status]);
  const awaitingContextValue = useMemo(
    () => ({
      triggerAwaiting: () => {
        setAwaitingFromInbox(true);
        useTurnStatusStore
          .getState()
          .setStatus(taskKeyOf(projectId, taskId), 'awaiting_model');
      },
    }),
    [projectId, taskId],
  );

  // "Waiting for Claude" indicator: show when the turn status is non-idle,
  // when the send mutation is in flight, when the last persisted message is
  // the user's prompt (cold-start gap), or when an inbox answer was just
  // submitted.
  const lastMessage = messages[messages.length - 1];
  const awaiting =
    turn.status === 'awaiting_model' ||
    turn.status === 'streaming' ||
    turn.status === 'awaiting_user' ||
    sendChat.isPending ||
    lastMessage?.type === 'user' ||
    awaitingFromInbox;

  // Only show the trailing streaming bubble when we're actively streaming
  // AND the newest committed message is older than a heartbeat — i.e. there
  // is a brief gap between turn start and the first block arriving. Once
  // committed messages start flowing the unified list handles display.
  const now = Date.now();
  const lastMsgTs = lastMessage?.timestamp ? Date.parse(lastMessage.timestamp) : 0;
  const showLeadingIndicator =
    (turn.status === 'awaiting_model' || awaitingFromInbox || sendChat.isPending) &&
    (!lastMessage || lastMessage.type === 'user' || now - lastMsgTs > 2_000);

  const { isAtBottom, scrollToBottom } = useAutoScroll(scrollRef, [messages, turn.status, awaiting]);
  const [chatError, setChatError] = useState<string | null>(null);

  const autonomy: AutonomyOption = project?.settings?.autonomy ?? globalSettings?.defaultAutonomy ?? 'guided';

  function handleSend(payload: import('./ChatInput').ChatSendPayload) {
    setChatError(null);
    useTurnStatusStore
      .getState()
      .setStatus(taskKeyOf(projectId, taskId), 'awaiting_model');
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
    <ChatAwaitingContext.Provider value={awaitingContextValue}>
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

        {/* Leading "awaiting / cold start" indicator — shows only when there
            is no recent committed output, so we don't race with the real
            streamed messages. */}
        {showLeadingIndicator && <AssistantMessage content="" isStreaming />}
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

      {/* Input area — disable while awaiting (prevents double-send race).
          projectId + taskId flow down so PermissionMode can fire the
          mid-task mode-switch mutation (iterate 10). */}
      <ChatInput
        onSend={handleSend}
        isStreaming={awaiting}
        autonomy={autonomy}
        projectId={projectId}
        taskId={taskId}
      />
    </div>
    </ChatAwaitingContext.Provider>
  );
}
