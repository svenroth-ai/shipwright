import type { ChatMessage } from '../../types';
import { MarkdownContent } from './MarkdownContent';

interface UserMessageProps {
  message: ChatMessage;
}

/**
 * User message — subtle grey bubble, left-aligned. Readable on the
 * beige chat background but visually distinct from Claude's white cards.
 */
export function UserMessage({ message }: UserMessageProps) {
  const images = (message as unknown as {
    images?: Array<{ media_type: string; data: string }>;
  }).images;

  return (
    <div className="bg-[#d4cbbc] text-gray-900 rounded-xl px-4 py-3 max-w-full min-w-0 shadow-[0_1px_2px_rgba(0,0,0,0.06)]">
      {images && images.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {images.map((img, i) => (
            <img
              key={i}
              src={`data:${img.media_type};base64,${img.data}`}
              alt="attachment"
              className="max-w-[180px] max-h-[140px] rounded-lg object-cover border border-[var(--color-border,#e0dbd4)]"
            />
          ))}
        </div>
      )}
      {message.content && <MarkdownContent text={message.content} />}
    </div>
  );
}
