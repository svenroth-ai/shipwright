import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  MessagePartPrimitive,
  ComposerPrimitive,
  useThread,
} from '@assistant-ui/react';
import { useChat, useSendChat } from '../hooks/useChat';
import { useTurnStatus } from '../hooks/useTurnStatus';
import { convertToThreadMessage } from './convertToThreadMessage';

/**
 * PoC — mount a minimal assistant-ui Thread against our existing
 * useChat data source and useSendChat mutation. No styling polish yet;
 * we only want to see if the rendering pipeline (text, tool-call,
 * reasoning, streaming) works end-to-end with our NDJSON-derived messages.
 */
interface Props {
  projectId: string;
  taskId: string;
}

export function PocChatPanel({ projectId, taskId }: Props) {
  const { data: rawMessages = [] } = useChat(projectId, taskId);
  const sendChat = useSendChat();
  const turn = useTurnStatus(projectId, taskId);

  // Hide the giant system/init JSON blobs from the feed — production's
  // ChatMessage.tsx does the same via isSystemInitBlob. Keep non-blob
  // system messages (short "Session started…" lines) but suppress blobs.
  const visibleMessages = rawMessages.filter((m) => {
    if (m.type !== 'system') return true;
    if (typeof m.content !== 'string') return true;
    if (!m.content.startsWith('{')) return true;
    return !m.content.includes('"subtype":"init"');
  });

  // assistant-ui's ExternalStoreRuntime takes our messages + a converter;
  // we don't manage its own message array, it projects from ours.
  const runtime = useExternalStoreRuntime({
    messages: visibleMessages,
    convertMessage: convertToThreadMessage,
    // While our turn status shows awaiting_model / streaming, we're running.
    // (The known Issue #2603 about isRunning + non-empty messages is
    //  acknowledged — if it misbehaves we'll fall back to message.status.)
    isRunning: turn.status === 'awaiting_model' || turn.status === 'streaming',
    onNew: async (message) => {
      const firstPart = message.content[0];
      const text = firstPart && firstPart.type === 'text' ? firstPart.text : '';
      if (!text.trim()) return;
      sendChat.mutate({
        projectId,
        taskId,
        message: text,
      });
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex flex-col h-full" data-testid="poc-chat-panel">
        <ThreadPrimitive.Root className="flex-1 flex flex-col overflow-hidden">
          <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
            <ThreadPrimitive.Empty>
              <div className="text-center text-gray-400 text-sm py-8">
                <p>(PoC) No messages yet.</p>
              </div>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={{ Message: PocMessage }} />
          </ThreadPrimitive.Viewport>
          <div className="border-t p-3">
            <ComposerPrimitive.Root className="flex gap-2">
              <ComposerPrimitive.Input
                className="flex-1 border rounded px-3 py-2 text-sm"
                placeholder="(PoC) Send a message"
              />
              <ComposerPrimitive.Send className="px-4 py-2 rounded bg-[var(--color-primary)] text-white text-sm">
                Send
              </ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
          </div>
        </ThreadPrimitive.Root>
      </div>
    </AssistantRuntimeProvider>
  );
}

function PocMessage() {
  return (
    <MessagePrimitive.Root className="mr-auto max-w-[80%] rounded-xl border bg-white p-3 text-sm shadow-sm data-[role=user]:ml-auto data-[role=user]:mr-0 data-[role=user]:bg-blue-50 data-[role=system]:mx-auto data-[role=system]:max-w-none data-[role=system]:border-none data-[role=system]:bg-transparent data-[role=system]:text-center data-[role=system]:text-[11px] data-[role=system]:text-gray-400 data-[role=system]:shadow-none">
      <MessagePrimitive.Parts
        components={{
          Text: () => <MessagePartPrimitive.Text />,
          tools: {
            Fallback: PocToolCall,
          },
        }}
      />
    </MessagePrimitive.Root>
  );
}

function PocToolCall({ toolName, args }: { toolName: string; args: unknown }) {
  return (
    <div className="rounded bg-gray-50 p-2 text-xs font-mono">
      <div className="font-semibold">🔧 {toolName}</div>
      <pre className="whitespace-pre-wrap">{JSON.stringify(args, null, 2)}</pre>
    </div>
  );
}

// Silence unused import — useThread is exported for downstream subcomponents
// if we want to read thread state; not used in the minimal PoC.
void useThread;

// Keep projectId/taskId referenced in the module (unused vars) — the Props
// interface plus AssistantRuntimeProvider consume them via closure.
void (null as unknown as Props);
