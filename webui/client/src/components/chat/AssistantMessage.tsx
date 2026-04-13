import type { ChatMessage } from '../../types';
import { MarkdownContent } from './MarkdownContent';
import { StreamingIndicator } from './StreamingIndicator';

interface AssistantMessageProps {
  message?: ChatMessage;
  content?: string;
  isStreaming?: boolean;
}

/**
 * Claude's message — white card with subtle shadow on the beige chat
 * background. Gives tables, code blocks, and block quotes a clean
 * readable surface while still looking visually distinct from tool
 * cards (no heavy border, just a soft shadow).
 */
export function AssistantMessage({ message, content, isStreaming }: AssistantMessageProps) {
  const text = content ?? message?.content ?? '';

  if (isStreaming && !text) {
    return (
      <div className="bg-white rounded-xl px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.06)] max-w-full min-w-0">
        <span className="inline-flex items-center gap-2 text-sm text-gray-500">
          <StreamingIndicator />
          <span className="italic">Thinking…</span>
        </span>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.06)] max-w-full min-w-0">
      <MarkdownContent text={text} showCursor={isStreaming} />
    </div>
  );
}
