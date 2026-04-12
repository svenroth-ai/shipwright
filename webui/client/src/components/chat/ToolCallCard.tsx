import { useState } from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { ChevronRight, AlertTriangle } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { ToolIcon } from './ToolIcon';

interface ToolCallCardProps {
  message: ChatMessage;
}

const MAX_OUTPUT_LINES = 50;

export function ToolCallCard({ message }: ToolCallCardProps) {
  const [open, setOpen] = useState(false);
  const [showFullOutput, setShowFullOutput] = useState(false);

  const isResult = message.type === 'tool_result';
  const isError = message.isError === true;
  const toolName = message.toolName ?? 'Tool';
  const input = message.toolInput;
  const output = isResult
    ? message.content
    : typeof message.toolOutput === 'string'
      ? message.toolOutput
      : JSON.stringify(message.toolOutput, null, 2);
  const summary = getSummary(toolName, input);

  const outputLines = output?.split('\n') ?? [];
  const isTruncated = outputLines.length > MAX_OUTPUT_LINES && !showFullOutput;
  const displayOutput = isTruncated ? outputLines.slice(0, MAX_OUTPUT_LINES).join('\n') : output;

  // Error styling
  const borderColor = isError ? 'border-red-300' : 'border-gray-200';
  const bgColor = isError ? 'bg-red-50' : 'bg-gray-100';
  const hoverBg = isError ? 'hover:bg-red-100' : 'hover:bg-gray-150';
  const nameColor = isError ? 'text-red-700' : 'text-gray-700';
  const summaryColor = isError ? 'text-red-400' : 'text-gray-400';

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div className={`${bgColor} rounded-lg border ${borderColor} overflow-hidden`}>
        <Collapsible.Trigger asChild>
          <button className={`flex items-center gap-2 px-3 py-2 w-full text-left ${hoverBg} cursor-pointer`}>
            <ChevronRight
              size={14}
              className={`${isError ? 'text-red-400' : 'text-gray-400'} transition-transform ${open ? 'rotate-90' : ''}`}
            />
            {isError ? (
              <AlertTriangle size={16} className="text-red-400 shrink-0" />
            ) : (
              <ToolIcon toolName={toolName} />
            )}
            <span className={`text-xs font-medium ${nameColor}`}>
              {isResult ? `${toolName} result` : toolName}
            </span>
            {isError && (
              <span className="text-[10px] font-medium text-red-500 bg-red-100 px-1.5 py-0.5 rounded">
                error
              </span>
            )}
            {!open && summary && (
              <span className={`text-xs ${summaryColor} truncate flex-1`}>{summary}</span>
            )}
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div className={`px-3 pb-3 border-t ${borderColor}`}>
            {input != null && !isResult && (
              <div className="mt-2">
                <p className="text-[10px] font-medium text-gray-500 uppercase mb-1">Input</p>
                <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto max-h-[200px] overflow-y-auto">
                  {typeof input === 'string' ? input : JSON.stringify(input, null, 2)}
                </pre>
              </div>
            )}
            {(output || isResult) && (
              <div className="mt-2">
                <p className="text-[10px] font-medium text-gray-500 uppercase mb-1">
                  {isResult ? 'Result' : 'Output'}
                </p>
                <pre className={`text-xs rounded p-2 overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre-wrap ${
                  isError ? 'bg-red-50 text-red-800' : 'bg-gray-50'
                }`}>
                  {displayOutput || '(no output)'}
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
  if (toolName === 'Glob') return String(obj.pattern ?? '');
  if (toolName === 'Agent') return String(obj.description ?? '').slice(0, 60);
  return '';
}
