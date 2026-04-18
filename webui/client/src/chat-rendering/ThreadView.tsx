import { useMemo } from 'react';
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  useMessage,
} from '@assistant-ui/react';
import type { ChatMessage, TaskStatus } from '../types';
import { convertToThreadMessage, visibleChatMessages } from './convertToThreadMessage';
import { ChatRenderingContext, useChatRendering } from './ChatRenderingContext';
import { MarkdownTextPart } from './MarkdownTextPart';
import { ReasoningPart } from './ReasoningPart';
import { ToolCallPart } from './ToolCallPart';
import { AskUserCard } from '../components/chat/AskUserCard';

interface ThreadViewProps {
  messages: ChatMessage[];
  isRunning: boolean;
  onSend: (text: string) => void;
  /** Rendered once above the messages list — used for the spawn indicator. */
  leadingSlot?: React.ReactNode;
  /** Rendered once below the messages list — used for leading "Thinking…" placeholder. */
  trailingSlot?: React.ReactNode;
  /**
   * Override the default empty-state placeholder. Pass `null` to suppress
   * the placeholder entirely (useful when a spawn indicator owns the
   * empty-chat window).
   */
  emptyState?: React.ReactNode;
  taskStatus?: TaskStatus;
  orphanReason?: string;
  claudeSessionId?: string;
  onResume?: () => void;
  'data-testid'?: string;
}

/**
 * Sub-iterate A — renderer foundation.
 *
 * Mounts an assistant-ui `ThreadPrimitive` against our `ChatMessage[]`
 * via `useExternalStoreRuntime`. The data source is upstream (TanStack
 * Query + SSE); this component is a pure projection and never mutates
 * global stores.
 *
 * Part renderers:
 *  - text      → MarkdownTextPart (markdown + code fences + tables)
 *  - reasoning → ReasoningPart (collapsible thinking block)
 *  - tools.Fallback → ToolCallPart (wraps legacy ToolCallCard)
 *
 * Special case: messages whose source ChatMessage is a tool_use for
 * `AskUserQuestion` bypass the MessagePrimitive path entirely and render
 * as `<AskUserCard>`. Sub-iterate B will migrate AskUserQuestion to a
 * first-class custom message-part type.
 */
export function ThreadView({
  messages,
  isRunning,
  onSend,
  leadingSlot,
  trailingSlot,
  emptyState,
  taskStatus,
  orphanReason,
  claudeSessionId,
  onResume,
  'data-testid': testId = 'chat-thread',
}: ThreadViewProps) {
  const visible = useMemo(() => visibleChatMessages(messages), [messages]);

  const messagesById = useMemo(() => {
    const map = new Map<string, ChatMessage>();
    for (const msg of messages) map.set(msg.id, msg);
    return map;
  }, [messages]);

  const runtime = useExternalStoreRuntime({
    messages: visible,
    convertMessage: convertToThreadMessage,
    isRunning,
    onNew: async (message) => {
      const firstPart = message.content[0];
      const text = firstPart && firstPart.type === 'text' ? firstPart.text : '';
      if (!text.trim()) return;
      onSend(text);
    },
  });

  const contextValue = useMemo(
    () => ({ messagesById, taskStatus, orphanReason, claudeSessionId, onResume }),
    [messagesById, taskStatus, orphanReason, claudeSessionId, onResume],
  );

  return (
    <ChatRenderingContext.Provider value={contextValue}>
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root
          className="flex-1 flex flex-col min-w-0 overflow-hidden"
          data-testid={testId}
        >
          <ThreadPrimitive.Viewport
            className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden px-6 py-5 flex flex-col gap-[18px]"
            aria-label="Chat history"
            role="log"
          >
            {leadingSlot}
            <ThreadPrimitive.Empty>
              {emptyState === undefined ? (
                <div className="text-center text-gray-400 text-sm py-8">
                  <p>No messages yet.</p>
                  <p className="text-xs mt-1">Start the task to begin chatting with Claude.</p>
                </div>
              ) : (
                emptyState
              )}
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={{ Message: ThreadMessage }} />
            {trailingSlot}
          </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
      </AssistantRuntimeProvider>
    </ChatRenderingContext.Provider>
  );
}

type RoleLike = 'user' | 'assistant' | 'system';

/**
 * Per-message renderer. Detects the AskUserQuestion tool_use and swaps
 * in AskUserCard. Otherwise delegates to MessagePrimitive.Parts.
 */
function ThreadMessage() {
  const id = useMessage((m) => m.id);
  const role = useMessage((m) => m.role) as RoleLike;
  const { messagesById, taskStatus, orphanReason, claudeSessionId, onResume } = useChatRendering();

  const source = messagesById.get(id);
  if (source?.type === 'tool_use' && source.toolName === 'AskUserQuestion') {
    return (
      <AskUserCard
        message={source}
        taskStatus={taskStatus}
        orphanReason={orphanReason}
        claudeSessionId={claudeSessionId}
        onResume={onResume}
      />
    );
  }

  return (
    <MessagePrimitive.Root
      className={roleClassName(role)}
      data-testid="chat-message"
      data-role={role}
    >
      <MessagePrimitive.Parts
        components={{
          Text: ({ text }) => <MarkdownTextPart text={text} />,
          Reasoning: ({ text }) => <ReasoningPart text={text} />,
          tools: {
            Fallback: ToolCallPart,
          },
        }}
      />
    </MessagePrimitive.Root>
  );
}

function roleClassName(role: RoleLike): string {
  if (role === 'user') {
    return 'bg-[#d4cbbc] text-gray-900 rounded-xl px-4 py-3 max-w-full min-w-0 shadow-[0_1px_2px_rgba(0,0,0,0.06)]';
  }
  if (role === 'system') {
    return 'text-center text-[11px] text-gray-400 py-1';
  }
  return 'bg-white rounded-xl px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.06)] max-w-full min-w-0';
}
