import { useState } from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { ChevronRight } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { ToolIcon } from './ToolIcon';

interface ToolCallCardProps {
  message: ChatMessage;
}

const MAX_OUTPUT_LINES = 50;

export function ToolCallCard({ message }: ToolCallCardProps) {
  const [open, setOpen] = useState(false);
  const [showFullOutput, setShowFullOutput] = useState(false);

  const toolName = message.toolName ?? 'Tool';
  const input = message.toolInput;
  const output = typeof message.toolOutput === 'string' ? message.toolOutput : JSON.stringify(message.toolOutput, null, 2);
  const summary = getSummary(toolName, input);

  const outputLines = output?.split('\n') ?? [];
  const isTruncated = outputLines.length > MAX_OUTPUT_LINES && !showFullOutput;
  const displayOutput = isTruncated ? outputLines.slice(0, MAX_OUTPUT_LINES).join('\n') : output;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div className="bg-gray-100 rounded-lg border border-gray-200 overflow-hidden">
        <Collapsible.Trigger asChild>
          <button className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-gray-150 cursor-pointer">
            <ChevronRight
              size={14}
              className={`text-gray-400 transition-transform ${open ? 'rotate-90' : ''}`}
            />
            <ToolIcon toolName={toolName} />
            <span className="text-xs font-medium text-gray-700">{toolName}</span>
            {!open && summary && (
              <span className="text-xs text-gray-400 truncate flex-1">{summary}</span>
            )}
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div className="px-3 pb-3 border-t border-gray-200">
            {input != null && (
              <div className="mt-2">
                <p className="text-[10px] font-medium text-gray-500 uppercase mb-1">Input</p>
                <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto max-h-[200px] overflow-y-auto">
                  {typeof input === 'string' ? input : JSON.stringify(input, null, 2)}
                </pre>
              </div>
            )}
            {output && (
              <div className="mt-2">
                <p className="text-[10px] font-medium text-gray-500 uppercase mb-1">Output</p>
                <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                  {displayOutput}
                </pre>
                {isTruncated && (
                  <button
                    className="text-xs text-[var(--color-primary)] hover:underline mt-1"
                    onClick={() => setShowFullOutput(true)}
                  >
                    Show more ({outputLines.length - MAX_OUTPUT_LINES} more lines)
                  </button>
                )}
              </div>
            )}
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  );
}

function getSummary(toolName: string, input: unknown): string {
  if (!input || typeof input !== 'object') return '';
  const obj = input as Record<string, unknown>;
  if (toolName === 'Bash') return String(obj.command ?? '').slice(0, 60);
  if (toolName === 'Read' || toolName === 'Write' || toolName === 'Edit') return String(obj.file_path ?? obj.path ?? '');
  if (toolName === 'Grep') return String(obj.pattern ?? '');
  return '';
}
