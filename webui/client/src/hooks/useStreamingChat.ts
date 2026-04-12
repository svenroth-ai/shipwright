import { useState, useRef, useCallback } from 'react';
import type { ChatMessage, ChatMessageType, NdjsonMessage } from '../types';

export interface StreamingState {
  isStreaming: boolean;
  /** Current assistant text being streamed (for the pulsing cursor) */
  displayContent: string;
  /** All streaming messages accumulated during this response */
  streamingMessages: ChatMessage[];
}

/**
 * Manages real-time message display during Claude streaming responses.
 * Instead of only buffering text, it maintains a typed message list
 * so the UI can show tool execution, thinking blocks, and text in real-time.
 */
export function useStreamingChat() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [displayContent, setDisplayContent] = useState('');
  const [streamingMessages, setStreamingMessages] = useState<ChatMessage[]>([]);
  const textBufferRef = useRef('');
  const counterRef = useRef(0);

  const makeId = () => `stream-${Date.now()}-${counterRef.current++}`;

  const startStream = useCallback(() => {
    setIsStreaming(true);
    setDisplayContent('');
    setStreamingMessages([]);
    textBufferRef.current = '';
    counterRef.current = 0;
  }, []);

  const endStream = useCallback(() => {
    // Flush remaining text buffer
    if (textBufferRef.current) {
      setDisplayContent((prev) => prev + textBufferRef.current);
      textBufferRef.current = '';
    }
    setIsStreaming(false);
  }, []);

  /** Append raw text token (for backward compatibility and streaming cursor) */
  const appendToken = useCallback((token: string) => {
    textBufferRef.current += token;
    // Flush immediately for responsive display
    setDisplayContent((prev) => prev + token);
  }, []);

  /** Process an NDJSON message and route to appropriate streaming state */
  const processNdjsonMessage = useCallback((taskId: string, msg: NdjsonMessage) => {
    // Assistant text — Claude CLI format: { type: "assistant", message: { model, content: [...] } }
    if (msg.type === 'assistant' && msg.message) {
      // Simple string message
      if (typeof msg.message === 'string') {
        appendToken(msg.message);
        return;
      }

      // Object with content blocks (real Claude CLI format)
      const msgObj = msg.message as Record<string, unknown>;
      const content = msgObj.content;

      if (Array.isArray(content)) {
        for (const block of content as Array<Record<string, unknown>>) {
          if (block.type === 'text' && typeof block.text === 'string') {
            appendToken(block.text);
          }
          if (block.type === 'thinking' && typeof block.thinking === 'string') {
            setStreamingMessages((prev) => [...prev, {
              id: makeId(), taskId, type: 'thinking' as ChatMessageType,
              content: block.thinking as string, timestamp: new Date().toISOString(),
            }]);
          }
          if (block.type === 'tool_use') {
            setStreamingMessages((prev) => [...prev, {
              id: makeId(), taskId, type: 'tool_use' as ChatMessageType,
              content: '', toolName: block.name as string, toolInput: block.input,
              timestamp: new Date().toISOString(),
            }]);
          }
        }
        return;
      }

      // Direct content block array (alternative format)
      if (Array.isArray(msg.message)) {
        for (const block of msg.message as Array<Record<string, unknown>>) {
          if (block.type === 'text' && typeof block.text === 'string') {
            appendToken(block.text);
          }
        }
        return;
      }

      return;
    }

    // Tool use — show tool card immediately
    if (msg.type === 'tool_use') {
      const toolName = msg.tool_name ?? (msg.message as { tool_name?: string } | undefined)?.tool_name ?? 'Tool';
      const toolInput = msg.tool_input ?? (msg.message as { tool_input?: unknown } | undefined)?.tool_input;
      setStreamingMessages((prev) => [...prev, {
        id: makeId(), taskId, type: 'tool_use',
        content: '', toolName, toolInput,
        timestamp: new Date().toISOString(),
      }]);
      return;
    }

    // Tool result — append result to streaming messages
    if (msg.type === 'tool_result') {
      const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content ?? msg.message ?? '');
      const isError = msg.is_error === true || msg.subtype === 'error';
      setStreamingMessages((prev) => [...prev, {
        id: makeId(), taskId, type: 'tool_result',
        content, isError,
        timestamp: new Date().toISOString(),
      }]);
      return;
    }

    // Result — final message, stream will end soon
    if (msg.type === 'result') {
      const content = msg.result ?? (typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message ?? ''));
      setStreamingMessages((prev) => [...prev, {
        id: makeId(), taskId, type: 'result',
        content: typeof content === 'string' ? content : JSON.stringify(content),
        timestamp: new Date().toISOString(),
      }]);
      return;
    }
  }, [appendToken]);

  return {
    isStreaming,
    displayContent,
    streamingMessages,
    appendToken,
    startStream,
    endStream,
    processNdjsonMessage,
  };
}
