import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { RendererProps } from '../../../types/viewer';

export const PlanOverlayRenderer = memo(function PlanOverlayRenderer({ content }: RendererProps) {
  // Future: parse section headers and overlay progress bars from build config
  return (
    <div className="p-4 overflow-y-auto h-full">
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
});
