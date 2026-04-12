import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { ChatMessage } from '../../types';
import { StreamingIndicator } from './StreamingIndicator';

interface AssistantMessageProps {
  message?: ChatMessage;
  content?: string;
  isStreaming?: boolean;
}

/**
 * Matches mockup 11-task-detail.html .msg-claude structure:
 *   <div class="msg-claude">
 *     <div class="msg-avatar claude">C</div>
 *     <div class="msg-body">
 *       <div class="msg-sender">Claude</div>
 *       <div class="msg-content">…markdown…</div>
 *     </div>
 *   </div>
 */
export function AssistantMessage({ message, content, isStreaming }: AssistantMessageProps) {
  const text = content ?? message?.content ?? '';

  return (
    <div className="flex gap-3 max-w-[95%] min-w-0">
      {/* Avatar — gradient brown */}
      <div
        className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold mt-0.5"
        style={{ background: 'linear-gradient(135deg, #6b5e56, #857568)' }}
      >
        C
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold mb-1 text-gray-900">Claude</div>
        <div className="text-sm leading-relaxed text-gray-900 prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:rounded-lg prose-pre:p-3 prose-code:bg-[var(--color-muted-bg,#ede8e1)] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none break-words">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {text}
          </ReactMarkdown>
          {isStreaming && <StreamingIndicator />}
        </div>
      </div>
    </div>
  );
}
