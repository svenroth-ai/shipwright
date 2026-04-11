import type { RendererProps } from '../../../types/viewer';

export function ExternalUrlRenderer({ tab }: RendererProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-3 py-2 border-b border-gray-200 bg-gray-50">
        <a
          href={tab.filePath}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:underline truncate"
        >
          {tab.filePath}
        </a>
      </div>
      <iframe
        src={tab.filePath}
        className="flex-1 w-full border-none"
        sandbox="allow-scripts allow-same-origin"
        title={`External: ${tab.label}`}
      />
    </div>
  );
}
