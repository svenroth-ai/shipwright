import type { ChatMessage } from '../../types';
import { MarkdownContent } from './MarkdownContent';

interface UserMessageProps {
  message: ChatMessage;
}

/**
 * User message — left-aligned, flat layout matching VS Code's Claude
 * extension. A thin primary-colored left border and a subtle background
 * tint distinguish it from Claude's messages without using a bubble.
 *
 * Also renders any attached images as thumbnails above the text.
 */
export function UserMessage({ message }: UserMessageProps) {
  const images = (message as unknown as {
    images?: Array<{ media_type: string; data: string }>;
  }).images;

  return (
    <div className="min-w-0 max-w-full border-l-2 border-[var(--color-primary,#6b5e56)] pl-3 py-0.5">
      <div className="text-[11px] font-semibold text-[var(--color-primary,#6b5e56)] mb-1 uppercase tracking-wide">
        You
      </div>
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
