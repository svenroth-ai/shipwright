import { LayoutGrid, List } from 'lucide-react';
import type { ViewMode } from '../../hooks/useBoardFilters';

interface ViewToggleProps {
  viewMode: ViewMode;
  onChange: (mode: ViewMode) => void;
}

export function ViewToggle({ viewMode, onChange }: ViewToggleProps) {
  return (
    <div className="flex border border-gray-200 rounded-lg overflow-hidden">
      <button
        aria-label="Board view"
        className={`flex items-center gap-1 px-3 py-1.5 text-[13px] font-medium transition-colors ${
          viewMode === 'board'
            ? 'bg-[var(--color-muted-bg,#ede8e1)] text-[var(--color-primary)]'
            : 'bg-white text-gray-500 hover:bg-gray-50'
        }`}
        onClick={() => onChange('board')}
      >
        <LayoutGrid size={14} /> Board
      </button>
      <button
        aria-label="List view"
        className={`flex items-center gap-1 px-3 py-1.5 text-[13px] font-medium border-l border-gray-200 transition-colors ${
          viewMode === 'list'
            ? 'bg-[var(--color-muted-bg,#ede8e1)] text-[var(--color-primary)]'
            : 'bg-white text-gray-500 hover:bg-gray-50'
        }`}
        onClick={() => onChange('list')}
      >
        <List size={14} /> List
      </button>
    </div>
  );
}
