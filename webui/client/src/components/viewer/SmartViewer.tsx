import { createContext, useContext } from 'react';
import { FileSearch } from 'lucide-react';
import { useViewerTabs } from '../../hooks/useViewerTabs';
import { ViewerTabBar } from './ViewerTabBar';
import { ViewerRouter } from './ViewerRouter';

interface ViewerContextAPI {
  openTab: (filePath: string, projectId: string) => void;
  openUrl: (url: string, label: string, projectId: string) => void;
}

const ViewerContext = createContext<ViewerContextAPI | null>(null);

export function useViewerContext() {
  return useContext(ViewerContext);
}

interface SmartViewerProps {
  projectId: string;
}

export function SmartViewer({ projectId }: SmartViewerProps) {
  const { tabs, activeTab, openTab, closeTab, activateTab, openUrl } = useViewerTabs();

  return (
    <ViewerContext.Provider value={{ openTab, openUrl }}>
      <div className="h-full flex flex-col bg-white border-l border-gray-200" data-testid="smart-viewer">
        {tabs.length > 0 && (
          <ViewerTabBar
            tabs={tabs}
            activeTabId={activeTab?.id ?? null}
            onActivate={activateTab}
            onClose={closeTab}
          />
        )}

        <div className="flex-1 overflow-hidden">
          {activeTab ? (
            <ViewerRouter tab={activeTab} projectId={projectId} />
          ) : (
            <div className="flex items-center justify-center h-full text-center text-gray-400">
              <div>
                <FileSearch size={40} className="mx-auto mb-3 opacity-50" />
                <p className="text-sm">Open a file from the explorer or click a file link</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </ViewerContext.Provider>
  );
}

export { ViewerContext };
