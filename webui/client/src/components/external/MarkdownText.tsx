/*
 * Markdown renderer for assistant text.
 *
 * Stack: react-markdown@10 + remark-gfm@4 + rehype-highlight@7. No raw
 * HTML passthrough (XSS-safe default — `react-markdown` escapes by
 * design unless `rehype-raw` is wired). Code fences over MAX_CODE_LINES
 * are truncated with a "Show more" affordance to keep the transcript
 * scannable; full content is one click away.
 *
 * User-message text is rendered plain (whitespace-pre-wrap) — not as
 * markdown — to avoid surprising users whose `*emphasis*` or `_under_`
 * gets re-rendered. Only assistant text goes through markdown.
 */

import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

const MAX_CODE_LINES = 200;
const MAX_LINE_LENGTH = 2000;

interface Props {
  text: string;
}

export function MarkdownText({ text }: Props) {
  return (
    <div className="markdown-body text-sm leading-relaxed" data-testid="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          code(props) {
            const { className, children, node: _node, ...rest } = props as {
              className?: string;
              children?: ReactNode;
              node?: unknown;
            };
            // Inline code: react-markdown@10 drops the legacy `inline` prop.
            // We detect block-level fences by the language-* className that
            // rehype-highlight relies on and the absence of a parent <pre>
            // collapse marker.
            const isFenced = typeof className === "string" && /\blanguage-/.test(className);
            if (!isFenced) {
              return (
                <code
                  className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[0.85em]"
                  {...rest}
                >
                  {children}
                </code>
              );
            }
            const text = childrenToString(children);
            return (
              <FencedCodeBlock className={className} {...rest}>
                {text}
              </FencedCodeBlock>
            );
          },
          // Long single-line content (think 5 KB log dumps) — wrap + horizontal
          // scroll instead of breaking the layout.
          p(props) {
            return <p className="my-1.5 break-words">{props.children}</p>;
          },
          a(props) {
            return (
              <a
                {...props}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-700 underline decoration-blue-400 hover:decoration-blue-700"
              />
            );
          },
        }}
      >
        {capLineLengths(text)}
      </ReactMarkdown>
    </div>
  );
}

function FencedCodeBlock({
  className,
  children,
}: {
  className?: string;
  children: string;
}) {
  // ReactMarkdown's renderer always appends a trailing newline to fenced
  // code; ignore that for counting purposes so a 200-line fence reads as
  // 200, not 201.
  const stripped = children.endsWith("\n") ? children.slice(0, -1) : children;
  const lines = stripped.split("\n");
  const truncated = lines.length > MAX_CODE_LINES;
  const [expanded, setExpanded] = useState(false);
  const visible = truncated && !expanded ? lines.slice(0, MAX_CODE_LINES).join("\n") : stripped;
  return (
    <div className="my-2 overflow-hidden rounded border border-neutral-200">
      <pre className="overflow-x-auto bg-neutral-900 p-3 text-xs leading-snug text-neutral-100">
        <code className={className} data-testid="fenced-code">
          {visible}
        </code>
      </pre>
      {truncated && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="block w-full bg-neutral-100 px-3 py-1 text-left text-xs text-neutral-600 hover:bg-neutral-200"
          data-testid="show-more-code"
        >
          {expanded
            ? `Show less (${lines.length} lines)`
            : `Show more (${lines.length - MAX_CODE_LINES} more lines)`}
        </button>
      )}
    </div>
  );
}

function childrenToString(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(childrenToString).join("");
  if (children == null || typeof children === "boolean") return "";
  if (typeof children === "object" && "props" in children) {
    return childrenToString((children as { props: { children?: ReactNode } }).props.children);
  }
  return String(children);
}

/**
 * Soft-wrap any line longer than MAX_LINE_LENGTH at MAX_LINE_LENGTH-char
 * boundaries with zero-width spaces so the renderer can break inside.
 * Without this, a 5 KB single-line log dump pushes the whole transcript
 * column wider than the viewport.
 */
function capLineLengths(text: string): string {
  if (!text.includes("\n") && text.length <= MAX_LINE_LENGTH) return text;
  return text
    .split("\n")
    .map((line) => {
      if (line.length <= MAX_LINE_LENGTH) return line;
      const chunks: string[] = [];
      for (let i = 0; i < line.length; i += MAX_LINE_LENGTH) {
        chunks.push(line.slice(i, i + MAX_LINE_LENGTH));
      }
      return chunks.join("\u200B");
    })
    .join("\n");
}
