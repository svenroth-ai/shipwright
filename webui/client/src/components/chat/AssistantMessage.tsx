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

export function AssistantMessage({ message, content, isStreaming }: AssistantMessageProps) {
  const text = content ?? message?.content ?? '';

  return (
    <div className="flex justify-start">
      <div className="mr-auto max-w-[80%] bg-[var(--color-background,#f5f0eb)] text-gray-900 rounded-2xl rounded-bl-sm px-4 py-2">
        <div className="text-sm prose prose-sm max-w-none prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:rounded-lg prose-pre:p-3 prose-code:text-[var(--color-primary)]">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {text}
          </ReactMarkdown>
          {isStreaming && <StreamingIndicator />}
        </div>
      </div>
    </div>
  );
}
