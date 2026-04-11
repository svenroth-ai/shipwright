import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { FileSearch, X } from 'lucide-react';

export interface ViewerTab {
  id: string;
  filePath: string;
  label: string;
}

export interface ViewerSlotAPI {
  openTab: (file: { path: string; label: string }) => void;
  closeTab: (id: string) => void;
  activeTab: ViewerTab | null;
  tabs: ViewerTab[];
}

const ViewerSlotContext = createContext<ViewerSlotAPI | null>(null);

export function useViewerSlot() {
  const ctx = useContext(ViewerSlotContext);
  if (!ctx) throw new Error('useViewerSlot must be used within ViewerSlotProvider');
  return ctx;
}

export function ViewerSlot() {
  const [tabs, setTabs] = useState<ViewerTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  const openTab = useCallback((file: { path: string; label: string }) => {
    const id = file.path;
    setTabs((prev) => {
      if (prev.some((t) => t.id === id)) return prev;
      return [...prev, { id, filePath: file.path, label: file.label }];
    });
    setActiveTabId(id);
  }, []);

  const closeTab = useCallback((id: string) => {
    setTabs((prev) => {
      const next = prev.filter((t) => t.id !== id);
      return next;
    });
    setActiveTabId((prev) => (prev === id ? null : prev));
  }, []);

  const activeTab = useMemo(
    () => tabs.find((t) => t.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );

  const api = useMemo(() => ({ openTab, closeTab, activeTab, tabs }), [openTab, closeTab, activeTab, tabs]);

  return (
    <ViewerSlotContext.Provider value={api}>
      <div className="h-full flex flex-col bg-white border-l border-gray-200" data-testid="viewer-slot">
        {/* Tab bar */}
        {tabs.length > 0 && (
          <div className="flex items-center border-b border-gray-100 px-2 bg-gray-50 overflow-x-auto">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs cursor-pointer whitespace-nowrap border-b-2 ${
                  tab.id === activeTabId
                    ? 'border-[var(--color-primary)] text-gray-900 font-medium'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setActiveTabId(tab.id)}
              >
                {tab.label}
                <button
                  className="hover:text-gray-900 p-0.5"
                  onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
                  aria-label={`Close ${tab.label}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 flex items-center justify-center">
          {activeTab ? (
            <div className="p-4 text-sm text-gray-500">
              {/* Renderer placeholder — Split 03 plugs in here */}
              <p className="font-mono text-xs">{activeTab.filePath}</p>
            </div>
          ) : (
            <div className="text-center text-gray-400">
              <FileSearch size={40} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm">Select a file to view here</p>
            </div>
          )}
        </div>
      </div>
    </ViewerSlotContext.Provider>
  );
}

export { ViewerSlotContext };
