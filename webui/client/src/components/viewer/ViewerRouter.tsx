import type { ViewerTab } from '../../types/viewer';
import { useFileContent } from '../../hooks/useFileContent';
import { MarkdownRenderer } from './renderers/MarkdownRenderer';
import { CodeRenderer } from './renderers/CodeRenderer';
import { HtmlPreviewRenderer } from './renderers/HtmlPreviewRenderer';
import { JsonTreeRenderer } from './renderers/JsonTreeRenderer';
import { SpecOverlayRenderer } from './renderers/SpecOverlayRenderer';
import { PlanOverlayRenderer } from './renderers/PlanOverlayRenderer';
import { ConsistencyDashboard } from './renderers/ConsistencyDashboard';
import { ExternalUrlRenderer } from './renderers/ExternalUrlRenderer';

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
      return <CodeRenderer {...rendererProps} />;
    case 'html':
      return <HtmlPreviewRenderer {...rendererProps} />;
    case 'json':
      return <JsonTreeRenderer {...rendererProps} />;
    case 'spec':
      return <SpecOverlayRenderer {...rendererProps} />;
    case 'plan':
      return <PlanOverlayRenderer {...rendererProps} />;
    case 'consistency':
      return <ConsistencyDashboard {...rendererProps} />;
    case 'url':
      return <ExternalUrlRenderer {...rendererProps} />;
    default:
      return <div className="flex items-center justify-center h-full text-sm text-gray-400">Unsupported file type</div>;
  }
}
