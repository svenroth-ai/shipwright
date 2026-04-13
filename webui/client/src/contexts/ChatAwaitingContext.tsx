import { createContext, useContext } from 'react';

/**
 * ChatAwaitingContext — iterate 7 latency fix.
 *
 * Lets `AskUserCard` tell the enclosing `ChatPanel` that an inbox answer
 * was just submitted, so the "Thinking…" indicator can fire immediately
 * instead of waiting 2–3s for Claude CLI's first NDJSON event on the
 * warmed-up stdin pipe. `ChatPanel` owns a local boolean flipped by
 * `triggerAwaiting()` and cleared once the stream starts or a new
 * persisted message lands.
 */
export interface ChatAwaitingValue {
  triggerAwaiting: () => void;
}

const noop: ChatAwaitingValue = { triggerAwaiting: () => {} };

export const ChatAwaitingContext = createContext<ChatAwaitingValue>(noop);

export function useChatAwaiting(): ChatAwaitingValue {
  return useContext(ChatAwaitingContext);
}
