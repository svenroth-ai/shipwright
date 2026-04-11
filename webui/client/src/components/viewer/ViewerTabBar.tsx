import { X } from 'lucide-react';
import type { ViewerTab } from '../../types/viewer';

interface ViewerTabBarProps {
  tabs: ViewerTab[];
  activeTabId: string | null;
  onActivate: (tabId: string) => void;
  onClose: (tabId: string) => void;
}

export function ViewerTabBar({ tabs, activeTabId, onActivate, onClose }: ViewerTabBarProps) {
  return (
    <div role="tablist" className="flex items-center border-b border-gray-100 bg-gray-50 overflow-x-auto">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs cursor-pointer whitespace-nowrap border-b-2 transition-colors ${
              isActive
                ? 'border-[var(--color-primary)] text-gray-900 font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => onActivate(tab.id)}
          >
            {tab.label}
            <span
              role="button"
              aria-label={`Close ${tab.label}`}
              className="hover:text-gray-900 p-0.5"
              onClick={(e) => { e.stopPropagation(); onClose(tab.id); }}
            >
              <X size={12} />
            </span>
          </button>
        );
      })}
    </div>
  );
}
