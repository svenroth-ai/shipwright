import { type ComponentProps } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Inline markdown renderer used as the `Text` part renderer inside the
 * assistant-ui Thread. Structurally identical to the legacy
 * `MarkdownContent` component that was ported from
 * The-Vibe-Company/companion (MIT), re-homed here because chat rendering
 * is the only caller.
 */
interface Props {
  text: string;
}

export function MarkdownTextPart({ text }: Props) {
  return (
    <div className="text-[14px] text-gray-900 leading-relaxed overflow-hidden max-w-full min-w-0 break-words">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          h1: ({ children }) => <h1 className="text-xl font-bold text-gray-900 mt-4 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-lg font-bold text-gray-900 mt-3 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-base font-semibold text-gray-900 mt-3 mb-1">{children}</h3>,
          h4: ({ children }) => <h4 className="text-sm font-semibold text-gray-900 mt-2 mb-1">{children}</h4>,
          ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="text-gray-900">{children}</li>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-primary,#6b5e56)] hover:underline"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[var(--color-primary,#6b5e56)]/40 pl-3 my-2 text-gray-600 italic">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="border-[var(--color-border,#e0dbd4)] my-4" />,
          code: (props: ComponentProps<'code'>) => {
            const { children, className } = props;
            const match = /language-(\w+)/.exec(className || '');
            const isBlock = match || (typeof children === 'string' && children.includes('\n'));

            if (isBlock) {
              const lang = match?.[1] || '';
              return (
                <div className="my-3 rounded-lg overflow-hidden border border-[var(--color-border,#e0dbd4)]">
                  {lang && (
                    <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-gray-500 bg-[var(--color-muted-bg,#ede8e1)] border-b border-[var(--color-border,#e0dbd4)]">
                      {lang}
                    </div>
                  )}
                  <pre className="px-3 py-2 overflow-x-auto bg-white text-xs font-mono">
                    <code className={className}>{children}</code>
                  </pre>
                </div>
              );
            }
            return (
              <code className="rounded bg-[var(--color-muted-bg,#ede8e1)] px-1 py-0.5 text-[13px] font-mono">
                {children}
              </code>
            );
          },
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto max-w-full">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[var(--color-muted-bg,#ede8e1)]">{children}</thead>,
          th: ({ children }) => (
            <th className="border border-[var(--color-border,#e0dbd4)] px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border border-[var(--color-border,#e0dbd4)] px-2 py-1">{children}</td>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
