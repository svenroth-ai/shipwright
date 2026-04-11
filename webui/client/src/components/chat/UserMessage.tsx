import type { ChatMessage } from '../../types';

interface UserMessageProps {
  message: ChatMessage;
}

export function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="ml-auto max-w-[80%] bg-[var(--color-primary)] text-white rounded-2xl rounded-br-sm px-4 py-2">
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  );
}
