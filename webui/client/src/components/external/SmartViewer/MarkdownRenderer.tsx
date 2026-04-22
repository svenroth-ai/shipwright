/*
 * MarkdownRenderer — thin wrapper around the iterate-2 <MarkdownText>
 * so SmartViewer can render .md / .markdown files reusing the same XSS
 * guarded stack (react-markdown + remark-gfm + rehype-highlight).
 */

import { MarkdownText } from "../MarkdownText";

interface Props {
  text: string;
}

export function MarkdownRenderer({ text }: Props) {
  return (
    <div
      className="smart-viewer-markdown h-full overflow-auto p-5"
      style={{ background: "var(--color-surface, #ffffff)" }}
      data-testid="smart-viewer-markdown"
    >
      <MarkdownText text={text} />
    </div>
  );
}
