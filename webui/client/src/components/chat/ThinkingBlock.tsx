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

export function ThinkingBlock({ message }: ThinkingBlockProps) {
  const [open, setOpen] = useState(false);
  const charCount = message.content.length;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div className="rounded-lg border border-purple-200 bg-purple-50 overflow-hidden">
        <Collapsible.Trigger asChild>
          <button className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-purple-100 cursor-pointer">
            <ChevronRight
              size={14}
              className={`text-purple-400 transition-transform ${open ? 'rotate-90' : ''}`}
            />
            <Brain size={16} className="text-purple-400 shrink-0" />
            <span className="text-xs font-medium text-purple-700">Thinking</span>
            <span className="text-xs text-purple-400 ml-auto">{formatCharCount(charCount)}</span>
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div className="px-3 pb-3 border-t border-purple-200">
            <pre className="mt-2 text-xs text-purple-900 bg-purple-50 rounded p-2 overflow-x-auto max-h-[400px] overflow-y-auto whitespace-pre-wrap">
              {message.content}
            </pre>
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  );
}
