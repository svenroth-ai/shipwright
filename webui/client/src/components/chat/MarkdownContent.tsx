import { type ComponentProps } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Full-featured Markdown renderer ported from The-Vibe-Company/companion
 * (MIT) — web/src/components/MessageBubble.tsx → MarkdownContent component.
 *
 * Handles every common artifact: headings, paragraphs, lists, tables,
 * blockquotes, horizontal rules, links, strong/em, inline code, and
 * fenced code blocks with optional language header.
 *
 * Uses our existing CSS custom properties (--color-*) instead of
 * companion's cc-* Tailwind tokens. Otherwise structurally identical.
 */
interface Props {
  text: string;
  showCursor?: boolean;
}

export function MarkdownContent({ text, showCursor = false }: Props) {
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
          code: (props: ComponentProps<"code">) => {
            const { children, className } = props;
            const match = /language-(\w+)/.exec(className || "");
            const isBlock = match || (typeof children === "string" && children.includes("\n"));

            if (isBlock) {
              const lang = match?.[1] || "";
              return (
                <div className="my-2.5 rounded-xl overflow-hidden border border-[var(--color-border,#e0dbd4)] shadow-[0_2px_8px_rgba(0,0,0,0.04)]">
                  {lang && (
                    <div className="px-3 py-1.5 bg-gray-900 border-b border-[var(--color-border,#e0dbd4)] flex items-center gap-2">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 rounded-full bg-gray-600" />
                        <span className="w-2 h-2 rounded-full bg-gray-600" />
                        <span className="w-2 h-2 rounded-full bg-gray-600" />
                      </div>
                      <span className="text-[10px] text-gray-400 font-mono uppercase tracking-wider">
                        {lang}
                      </span>
                    </div>
                  )}
                  <pre className="px-3 sm:px-4 py-2.5 sm:py-3 bg-gray-900 text-gray-100 text-[12px] sm:text-[13px] font-mono leading-relaxed overflow-x-auto">
                    <code>{children}</code>
                  </pre>
                </div>
              );
            }

            return (
              <code className="px-1.5 py-0.5 rounded-md bg-[var(--color-muted-bg,#ede8e1)] text-[12.5px] font-mono text-gray-800 border border-[var(--color-border,#e0dbd4)]/40">
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>,
          table: ({ children }) => (
            <div className="overflow-x-auto my-2 max-w-full">
              <table className="min-w-full text-sm border border-[var(--color-border,#e0dbd4)] rounded-lg overflow-hidden">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-[var(--color-muted-bg,#ede8e1)]">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="px-3 py-1.5 text-left text-xs font-semibold text-gray-900 border-b border-[var(--color-border,#e0dbd4)]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-1.5 text-xs text-gray-900 border-b border-[var(--color-border,#e0dbd4)]">
              {children}
            </td>
          ),
        }}
      >
        {text}
      </Markdown>
      {showCursor && (
        <span
          data-testid="assistant-stream-cursor"
          className="inline-block w-[3px] h-[16px] bg-[var(--color-primary,#6b5e56)] rounded-full ml-0.5 align-middle animate-pulse"
        />
      )}
    </div>
  );
}
