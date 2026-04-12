import { useState } from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { ChevronRight, Brain } from 'lucide-react';
import type { ChatMessage } from '../../types';

interface ThinkingBlockProps {
  message: ChatMessage;
}

function formatCharCount(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k chars`;
  return `${count} chars`;
}

/**
 * Dezent Thinking block, matching the mockup's warm neutral palette.
 * Not in the mockup explicitly, but fits the overall style.
 */
export function ThinkingBlock({ message }: ThinkingBlockProps) {
  const [open, setOpen] = useState(false);
  const charCount = message.content.length;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div
        className="rounded-lg overflow-hidden min-w-0 max-w-full bg-[var(--color-muted-bg,#ede8e1)]"
        style={{ border: '1px solid var(--color-border, #e0dbd4)' }}
      >
        <Collapsible.Trigger asChild>
          <button className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-[#e3ddd3] cursor-pointer">
            <Brain size={14} className="text-gray-500 shrink-0" />
            <span className="text-xs font-medium text-gray-700">Thinking</span>
            <span className="text-[11px] text-gray-500 ml-auto">{formatCharCount(charCount)}</span>
            <ChevronRight
              size={14}
              className={`text-gray-400 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
            />
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div className="px-3 pb-3 border-t border-[var(--color-border,#e0dbd4)]">
            <pre className="mt-2 text-xs text-gray-700 rounded p-2 overflow-x-auto max-h-[400px] overflow-y-auto whitespace-pre-wrap bg-white max-w-full break-words">
              {message.content}
            </pre>
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  );
}
