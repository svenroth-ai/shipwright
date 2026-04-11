import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { RendererProps } from '../../../types/viewer';
import { MermaidBlock } from './MermaidBlock';

export const MarkdownRenderer = memo(function MarkdownRenderer({ content }: RendererProps) {
  return (
    <div className="p-4 overflow-y-auto h-full">
      <div className="prose prose-sm max-w-none prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:rounded-lg prose-pre:p-3">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            code({ className, children, ...props }) {
              const match = /language-(\w+)/.exec(className || '');
              const lang = match?.[1];

              if (lang === 'mermaid') {
                return <MermaidBlock code={String(children).replace(/\n$/, '')} />;
              }

              // Inline code vs block code
              const isBlock = className?.includes('language-');
              if (isBlock) {
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              }

              return <code className="bg-gray-100 px-1 rounded text-sm" {...props}>{children}</code>;
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
});
