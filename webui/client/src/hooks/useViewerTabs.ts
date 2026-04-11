import { useState, useCallback, useMemo } from 'react';
import type { ViewerTab } from '../types/viewer';
import { resolveFileType } from '../types/viewer';

function fileLabel(filePath: string): string {
  const parts = filePath.split('/');
  return parts[parts.length - 1] || filePath;
}

export function useViewerTabs() {
  const [tabs, setTabs] = useState<ViewerTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  const openTab = useCallback((filePath: string, projectId: string) => {
    const id = filePath;
    setTabs((prev) => {
      if (prev.some((t) => t.id === id)) return prev;
      return [...prev, {
        id,
        label: fileLabel(filePath),
        filePath,
        fileType: resolveFileType(filePath),
        projectId,
      }];
    });
    setActiveTabId(id);
  }, []);

  const closeTab = useCallback((tabId: string) => {
    setTabs((prev) => {
      const idx = prev.findIndex((t) => t.id === tabId);
      const next = prev.filter((t) => t.id !== tabId);
      // Activate neighbor if closing active tab
      setActiveTabId((currentActive) => {
        if (currentActive !== tabId) return currentActive;
        if (next.length === 0) return null;
        const newIdx = Math.min(idx, next.length - 1);
        return next[newIdx].id;
      });
      return next;
    });
  }, []);

  const activateTab = useCallback((tabId: string) => {
    setActiveTabId(tabId);
  }, []);

  const openUrl = useCallback((url: string, label: string, projectId: string) => {
    const id = url;
    setTabs((prev) => {
      if (prev.some((t) => t.id === id)) return prev;
      return [...prev, { id, label, filePath: url, fileType: 'url' as const, projectId }];
    });
    setActiveTabId(id);
  }, []);

  const activeTab = useMemo(
    () => tabs.find((t) => t.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );

  return { tabs, activeTab, openTab, closeTab, activateTab, openUrl };
}
