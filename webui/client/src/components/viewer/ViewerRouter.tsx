import type { ViewerTab } from '../../types/viewer';
import { useFileContent } from '../../hooks/useFileContent';
import { MarkdownRenderer } from './renderers/MarkdownRenderer';

interface ViewerRouterProps {
  tab: ViewerTab;
  projectId: string;
}

export function ViewerRouter({ tab, projectId }: ViewerRouterProps) {
  const isUrl = tab.fileType === 'url';
  const { data: content, isLoading, error } = useFileContent(projectId, tab.filePath, !isUrl);

  if (!isUrl && isLoading) {
    return <div className="flex items-center justify-center h-full text-sm text-gray-400">Loading...</div>;
  }

  if (!isUrl && error) {
    return <div className="flex items-center justify-center h-full text-sm text-red-500">Failed to load file</div>;
  }

  const rendererContent = typeof content === 'string' ? content : '';
  const rendererProps = { tab, content: rendererContent, projectId };

  switch (tab.fileType) {
    case 'markdown':
    case 'compliance':
      return <MarkdownRenderer {...rendererProps} />;
    case 'code':
      return <div className="p-4 text-sm text-gray-500">Code renderer — Section 02</div>;
    case 'html':
      return <div className="p-4 text-sm text-gray-500">HTML preview — Section 02</div>;
    case 'json':
      return <div className="p-4 text-sm text-gray-500">JSON tree — Section 02</div>;
    case 'spec':
      return <div className="p-4 text-sm text-gray-500">Spec overlay — Section 02</div>;
    case 'plan':
      return <div className="p-4 text-sm text-gray-500">Plan overlay — Section 02</div>;
    case 'consistency':
      return <div className="p-4 text-sm text-gray-500">Consistency dashboard — Section 02</div>;
    case 'url':
      return (
        <div className="p-4 text-sm">
          <a href={tab.filePath} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
            {tab.filePath}
          </a>
        </div>
      );
    default:
      return <div className="flex items-center justify-center h-full text-sm text-gray-400">Unsupported file type</div>;
  }
}
