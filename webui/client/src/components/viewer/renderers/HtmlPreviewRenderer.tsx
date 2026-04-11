import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import type { RendererProps } from '../../../types/viewer';

export function HtmlPreviewRenderer({ tab, content }: RendererProps) {
  const [key, setKey] = useState(0);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 bg-gray-50">
        <span className="text-xs text-gray-500 flex-1 truncate">{tab.label}</span>
        <button
          className="p-1 rounded hover:bg-gray-200 text-gray-400"
          onClick={() => setKey((k) => k + 1)}
          aria-label="Refresh preview"
        >
          <RefreshCw size={14} />
        </button>
      </div>
      <iframe
        key={key}
        srcDoc={content}
        sandbox="allow-scripts allow-same-origin"
        className="flex-1 w-full border-none"
        title={`Preview: ${tab.label}`}
      />
    </div>
  );
}
