import { createContext, useContext } from 'react';
import type { ChatMessage, TaskStatus } from '../types';

/**
 * Bridge context between the assistant-ui runtime (which only knows
 * `ThreadMessageLike` parts) and our domain-specific renderers that
 * need the raw `ChatMessage` (AskUserCard, ToolCallCard).
 *
 * The Message-level renderer reads the current message id from
 * assistant-ui, looks up the original ChatMessage here, and dispatches
 * special-case renderers (AskUserQuestion).
 */
export interface ChatRenderingContextValue {
  messagesById: Map<string, ChatMessage>;
  taskStatus?: TaskStatus;
  orphanReason?: string;
  claudeSessionId?: string;
  onResume?: () => void;
}

const defaultValue: ChatRenderingContextValue = {
  messagesById: new Map(),
};

export const ChatRenderingContext = createContext<ChatRenderingContextValue>(defaultValue);

export function useChatRendering(): ChatRenderingContextValue {
  return useContext(ChatRenderingContext);
}
