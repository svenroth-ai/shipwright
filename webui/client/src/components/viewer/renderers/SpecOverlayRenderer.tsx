import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { RendererProps } from '../../../types/viewer';

export const SpecOverlayRenderer = memo(function SpecOverlayRenderer({ content }: RendererProps) {
  // FR badges injected inline — future: fetch real FR status from events
  const enriched = content.replace(
    /\bFR-(\d+\.\d+)\b/g,
    (match) => `**${match}** 🔵`,
  );

  return (
    <div className="p-4 overflow-y-auto h-full">
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {enriched}
        </ReactMarkdown>
      </div>
    </div>
  );
});
