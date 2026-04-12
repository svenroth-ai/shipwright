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
 * Minimal flat assistant message — no avatar, no sender label.
 * Matches the user's preferred VS Code-extension look: just markdown
 * flowing on the page background, left-aligned.
 *
 * Proper table/list/code styling is applied via explicit component
 * overrides below — we can't rely on @tailwindcss/typography alone
 * because tables collapse without borders (e.g. "SpieleTordiff.Punkte").
 */
export function AssistantMessage({ message, content, isStreaming }: AssistantMessageProps) {
  const text = content ?? message?.content ?? '';

  return (
    <div className="min-w-0 max-w-full text-sm leading-relaxed text-gray-900 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Paragraphs — normal spacing
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,

          // Headings
          h1: ({ children }) => <h1 className="text-base font-bold mt-3 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold mt-3 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,

          // Lists
          ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
          li: ({ children }) => <li className="text-sm">{children}</li>,

          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-primary,#6b5e56)] underline hover:no-underline"
            >
              {children}
            </a>
          ),

          // Inline code — small chip
          code: ({ className, children }) => {
            const isBlock = /language-/.test(className ?? '');
            if (isBlock) {
              return <code className={className}>{children}</code>;
            }
            return (
              <code className="bg-[var(--color-muted-bg,#ede8e1)] px-1.5 py-0.5 rounded text-[12px] font-mono">
                {children}
              </code>
            );
          },

          // Code blocks — dark rounded box
          pre: ({ children }) => (
            <pre className="bg-gray-900 text-gray-100 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono max-w-full">
              {children}
            </pre>
          ),

          // Tables — proper borders + padding so cells don't collide
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto max-w-full">
              <table className="border-collapse text-xs w-full">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-[var(--color-muted-bg,#ede8e1)]">{children}</thead>
          ),
          th: ({ children, style }) => (
            <th
              className="border border-[var(--color-border,#e0dbd4)] px-2.5 py-1.5 text-left font-semibold"
              style={style}
            >
              {children}
            </th>
          ),
          td: ({ children, style }) => (
            <td
              className="border border-[var(--color-border,#e0dbd4)] px-2.5 py-1.5"
              style={style}
            >
              {children}
            </td>
          ),

          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[var(--color-primary,#6b5e56)] pl-3 my-2 text-gray-600 italic">
              {children}
            </blockquote>
          ),

          // Horizontal rules
          hr: () => <hr className="my-3 border-t border-[var(--color-border,#e0dbd4)]" />,

          // Bold / italic
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
        }}
      >
        {text}
      </ReactMarkdown>
      {isStreaming && <StreamingIndicator />}
    </div>
  );
}
