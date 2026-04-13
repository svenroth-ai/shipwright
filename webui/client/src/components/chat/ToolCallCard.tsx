import { useState } from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { ChevronRight, Check, AlertTriangle } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { ToolIconTile } from './ToolIcon';

interface ToolCallCardProps {
  message: ChatMessage;
}

const MAX_OUTPUT_LINES = 50;

/**
 * Matches mockup 11-task-detail.html .tool-card structure:
 *   - White background, subtle border + shadow
 *   - Colored icon tile (blue for Read, amber for Edit, green for Bash)
 *   - Monospace title with file path / command
 *   - Success/error status badge right-aligned
 *   - Expandable body with input/output
 */
export function ToolCallCard({ message }: ToolCallCardProps) {
  const [open, setOpen] = useState(false);
  const [showFullOutput, setShowFullOutput] = useState(false);

  const isLegacyResult = message.type === 'tool_result';
  const hasFoldedOutput = message.toolOutput !== undefined;
  const isDone = isLegacyResult || hasFoldedOutput || message.isError === true;
  const isError = message.isError === true;
  const toolName = message.toolName ?? 'Tool';
  const input = message.toolInput;
  const output = isLegacyResult
    ? message.content
    : typeof message.toolOutput === 'string'
      ? message.toolOutput
      : message.toolOutput !== undefined
        ? JSON.stringify(message.toolOutput, null, 2)
        : undefined;
  const title = formatTitle(toolName, input);

  const outputLines = output?.split('\n') ?? [];
  const isTruncated = outputLines.length > MAX_OUTPUT_LINES && !showFullOutput;
  const displayOutput = isTruncated ? outputLines.slice(0, MAX_OUTPUT_LINES).join('\n') : output;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div
        className="bg-white rounded-lg overflow-hidden transition-all min-w-0 max-w-full"
        style={{
          border: `1px solid ${isError ? '#FCA5A5' : 'var(--color-border, #e0dbd4)'}`,
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          minHeight: '42px',
        }}
      >
        <Collapsible.Trigger asChild>
          <button
            className="flex items-center gap-2.5 px-3.5 py-2.5 w-full text-left hover:bg-[var(--color-muted-bg,#ede8e1)] cursor-pointer transition-colors min-w-0"
            style={{ minHeight: '42px' }}
          >
            <ToolIconTile toolName={toolName} />
            <span className="flex-1 text-[13px] font-medium text-gray-900 font-mono truncate min-w-0">
              {title}
            </span>
            {isError ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-red-600 shrink-0">
                <AlertTriangle size={12} />
                Error
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-green-700 shrink-0">
                <Check size={12} />
                {isDone ? 'Done' : 'Running'}
              </span>
            )}
            <ChevronRight
              size={16}
              className={`text-gray-400 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
            />
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content>
          <div className="border-t px-3.5 py-3 font-mono text-xs leading-relaxed bg-[#fafaf8] min-w-0 overflow-hidden" style={{ borderColor: 'var(--color-border, #e0dbd4)' }}>
            {input != null && !isLegacyResult && (
              <div className="mb-2">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-1">Input</div>
                <pre className="text-xs bg-white rounded p-2 overflow-x-auto max-h-[200px] overflow-y-auto max-w-full border border-gray-100">
                  {typeof input === 'string' ? input : JSON.stringify(input, null, 2)}
                </pre>
              </div>
            )}
            {(output != null || isLegacyResult) && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-1">
                  {isLegacyResult ? 'Result' : 'Output'}
                </div>
                <pre className={`text-xs rounded p-2 overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre-wrap max-w-full border break-words ${
                  isError ? 'bg-red-50 text-red-800 border-red-200' : 'bg-white border-gray-100'
                }`}>
                  {displayOutput || '(no output)'}
                </pre>
                {isTruncated && (
                  <button
                    className="text-xs text-[var(--color-primary,#6b5e56)] hover:underline mt-1"
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

function formatTitle(toolName: string, input: unknown): string {
  if (!input || typeof input !== 'object') return toolName;
  const obj = input as Record<string, unknown>;
  if (toolName === 'Bash') {
    const cmd = String(obj.command ?? '');
    return cmd ? `Run ${cmd}` : toolName;
  }
  if (toolName === 'Read') return `Read ${obj.file_path ?? obj.path ?? ''}`;
  if (toolName === 'Write') return `Write ${obj.file_path ?? obj.path ?? ''}`;
  if (toolName === 'Edit') return `Edit ${obj.file_path ?? obj.path ?? ''}`;
  if (toolName === 'Grep') return `Grep ${obj.pattern ?? ''}`;
  if (toolName === 'Glob') return `Glob ${obj.pattern ?? ''}`;
  if (toolName === 'Agent' || toolName === 'Task') return `${toolName} ${obj.description ?? ''}`;
  if (toolName === 'WebFetch' || toolName === 'WebSearch') return `${toolName} ${obj.url ?? obj.query ?? ''}`;
  return toolName;
}
