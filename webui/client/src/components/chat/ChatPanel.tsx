import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useChat, useSendChat, useRefetchChatOnResume } from '../../hooks/useChat';
import { useTurnStatus } from '../../hooks/useTurnStatus';
import { useProject } from '../../hooks/useProjects';
import { useSettings } from '../../hooks/useSettings';
import { useInterruptTask } from '../../hooks/useInterruptTask';
import { useResumeTask } from '../../hooks/useResumeTask';
import { useTask } from '../../hooks/useTask';
import { useChatSettings } from '../../hooks/useChatSettings';
import { ChatInput } from './ChatInput';
import { ApiError } from '../../lib/api';
import { foldToolResults } from '../../lib/foldToolResults';
import { collapseAskUserQuestionRun } from '../../lib/collapseAskUserQuestion';
import { useTurnStatusStore, taskKeyOf } from '../../stores/turnStatusStore';
import { useChatStore, useSystemInitModel } from '../../stores/chatStore';
import { ChatAwaitingContext } from '../../contexts/ChatAwaitingContext';
import { ThreadView } from '../../chat-rendering/ThreadView';
import type { ChatMessage } from '../../types';
import type { AutonomyOption } from '../../types/settings';

interface ChatPanelProps {
  projectId: string;
  taskId: string;
  /**
   * Iterate 14.7.1 — when true, scroll the chat to the newest message on
   * mount. Set by TaskDetailPage when the URL contains `?focus=chat-bottom`
   * (InboxPage → task navigation). Only fires once per mount; useAutoScroll
   * continues to govern further user interaction.
   */
  focusBottomOnMount?: boolean;
}

/**
 * Collapse result/assistant echoes that the server emits as distinct
 * messages but which render as visible duplicates. Kept as a render-time
 * filter; mergeCommitted correctly stores both, this filter only hides
 * the dupe visually.
 */
function dedupeMessages(messages: ChatMessage[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  for (const msg of messages) {
    if (msg.type === 'result') {
      const prev = out[out.length - 1];
      if (prev && prev.type === 'assistant' && prev.content === msg.content) {
        continue;
      }
    }
    out.push(msg);
  }
  return out;
}

export function ChatPanel({ projectId, taskId, focusBottomOnMount = false }: ChatPanelProps) {
  const { data: rawMessages = [] } = useChat(projectId, taskId);
  useRefetchChatOnResume(projectId, taskId);
  const messages = useMemo(
    () => collapseAskUserQuestionRun(dedupeMessages(foldToolResults(rawMessages))),
    [rawMessages],
  );

  const { data: project } = useProject(projectId);
  const { data: globalSettings } = useSettings();
  const { data: task } = useTask(projectId, taskId);
  const sendChat = useSendChat();
  const chatSettings = useChatSettings();

  const turn = useTurnStatus(projectId, taskId);

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

  const lastMessage = messages[messages.length - 1];
  const awaiting =
    turn.status === 'awaiting_model' ||
    turn.status === 'streaming' ||
    turn.status === 'awaiting_user' ||
    sendChat.isPending ||
    lastMessage?.type === 'user' ||
    awaitingFromInbox;

  const now = Date.now();
  const lastMsgTs = lastMessage?.timestamp ? Date.parse(lastMessage.timestamp) : 0;
  const showLeadingIndicator =
    (turn.status === 'awaiting_model' || awaitingFromInbox || sendChat.isPending) &&
    (!lastMessage || lastMessage.type === 'user' || now - lastMsgTs > 2_000);

  const [chatError, setChatError] = useState<string | null>(null);
  // Suppress focusBottomOnMount until assistant-ui's ScrollToBottom
  // primitive is wired — for now autoscroll at mount is handled by
  // ThreadPrimitive.Viewport which snaps to the last message.
  void focusBottomOnMount;

  const { mutate: interruptTask } = useInterruptTask(projectId, taskId);
  const resumeTask = useResumeTask();
  const handleResume = useCallback(
    () => resumeTask.mutate({ projectId, taskId }),
    [resumeTask, projectId, taskId],
  );

  const taskKey = taskKeyOf(projectId, taskId);
  const hydratedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!rawMessages.length || hydratedRef.current === taskKey) return;
    let latestModel: string | undefined;
    for (const m of rawMessages) {
      if (m.type === 'system' && m.model) latestModel = m.model;
    }
    if (latestModel) {
      useChatStore.getState().setSystemInit(taskKey, { model: latestModel });
      hydratedRef.current = taskKey;
    }
  }, [rawMessages, taskKey]);

  const systemInitModel = useSystemInitModel(taskKey);
  // Iterate 2026-04-18 modelswitch-spawn-ux — `task` is undefined on the
  // very first mount of a freshly-created task (tasks query lag + 404
  // race). Previously the spawn indicator only rendered when `task` was
  // loaded AND its status was in SPAWNING_STATUSES, so new tasks saw the
  // empty-state placeholder flash first. Now: if systemInit is empty,
  // treat the panel as awaiting-init. We still guard against terminal
  // tasks (don't render spinner once task loads with a terminal status).
  const TERMINAL_TASK_STATUSES = new Set([
    'done',
    'failed',
    'cancelled',
    'archived',
    'orphaned',
  ]);
  const taskIsTerminal = !!task && TERMINAL_TASK_STATUSES.has(task.status);
  const awaitingInit = !systemInitModel && !taskIsTerminal;

  const autonomy: AutonomyOption =
    project?.settings?.autonomy ?? globalSettings?.defaultAutonomy ?? 'guided';

  const handleThreadSend = useCallback(
    (text: string) => {
      setChatError(null);
      useTurnStatusStore
        .getState()
        .setStatus(taskKeyOf(projectId, taskId), 'awaiting_model');
      sendChat.mutate(
        {
          projectId,
          taskId,
          message: text,
          model: chatSettings.model,
          mode: chatSettings.mode,
          autonomy,
        },
        {
          onError: (err) => {
            if (err instanceof ApiError && err.status === 400) {
              setChatError(
                'Task is not running. Start the task first using the Start button on the board.',
              );
            } else {
              setChatError(err instanceof Error ? err.message : 'Failed to send message');
            }
          },
        },
      );
    },
    [projectId, taskId, sendChat, chatSettings.model, chatSettings.mode, autonomy],
  );

  function handleInputSend(payload: import('./ChatInput').ChatSendPayload) {
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
        autonomy: payload.autonomy,
      },
      {
        onError: (err) => {
          if (err instanceof ApiError && err.status === 400) {
            setChatError(
              'Task is not running. Start the task first using the Start button on the board.',
            );
          } else {
            setChatError(err instanceof Error ? err.message : 'Failed to send message');
          }
        },
      },
    );
  }

  const spawnSlot = awaitingInit ? (
    <div
      className="flex items-center justify-center gap-2 text-gray-500 text-sm py-8"
      data-testid="chat-spawn-indicator"
    >
      <Loader2 size={16} className="animate-spin" />
      <span>Starting Claude…</span>
    </div>
  ) : null;

  // Iterate 2026-04-18 — legacy "weisser Balken" leading indicator
  // removed. UAT report: users saw a visually ambiguous white card with
  // no obvious text while awaiting the model's first reply. The spawn
  // indicator now owns the visual slot during the boot gap; the in-turn
  // "awaiting" signal rides on assistant-ui's built-in streaming
  // rendering (isRunning → ThreadPrimitive rendering a progress state).
  void showLeadingIndicator; // retained for potential future wiring

  return (
    <ChatAwaitingContext.Provider value={awaitingContextValue}>
      <div
        className="flex flex-col h-full min-w-0 overflow-hidden"
        style={{ background: 'var(--color-bg, #f5f0eb)' }}
        data-testid="chat-panel"
      >
        <div className="flex-1 min-w-0 overflow-hidden flex flex-col">
          <ThreadView
            messages={messages}
            isRunning={awaiting}
            onSend={handleThreadSend}
            trailingSlot={spawnSlot}
            emptyState={awaitingInit ? null : undefined}
            taskStatus={task?.status}
            orphanReason={task?.orphanReason}
            claudeSessionId={task?.claudeSessionId}
            onResume={handleResume}
          />
        </div>

        {chatError && (
          <div className="mx-3 mb-2 flex items-start gap-2 px-3 py-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertCircle size={14} className="shrink-0 mt-0.5" />
            <span>{chatError}</span>
            <button
              className="ml-auto text-amber-500 hover:text-amber-700"
              onClick={() => setChatError(null)}
            >
              x
            </button>
          </div>
        )}

        <ChatInput
          onSend={handleInputSend}
          isStreaming={awaiting}
          autonomy={autonomy}
          projectId={projectId}
          taskId={taskId}
          onInterrupt={() => interruptTask()}
          taskStatus={task?.status}
          awaitingInit={awaitingInit}
        />
      </div>
    </ChatAwaitingContext.Provider>
  );
}
