import type { ChatMessage } from '../../types';

interface UserMessageProps {
  message: ChatMessage;
}

/**
 * User message in the chat. Not in mockup 11 explicitly, but matches the
 * rest of the visual language: right-aligned, primary brown bubble.
 */
export function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end min-w-0">
      <div className="ml-auto max-w-[80%] bg-[var(--color-primary,#6b5e56)] text-white rounded-xl rounded-br-sm px-4 py-2 shadow-sm">
        <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
      </div>
    </div>
  );
}
