import type { ChatMessage } from '../../types';
import { MarkdownContent } from './MarkdownContent';
import { StreamingIndicator } from './StreamingIndicator';

interface AssistantMessageProps {
  message?: ChatMessage;
  content?: string;
  isStreaming?: boolean;
}

/**
 * Claude's message — flat, left-aligned, no avatar, no sender label.
 * Just markdown flowing on the page background (VS Code chat style).
 */
export function AssistantMessage({ message, content, isStreaming }: AssistantMessageProps) {
  const text = content ?? message?.content ?? '';

  if (isStreaming && !text) {
    return <StreamingIndicator />;
  }

  return <MarkdownContent text={text} showCursor={isStreaming} />;
}
