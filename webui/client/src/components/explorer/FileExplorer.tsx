import { useState } from 'react';
import { X, Search, FolderTree } from 'lucide-react';
import { useFileTree } from '../../hooks/useFileTree';
import { DirectoryTree } from './DirectoryTree';

interface FileExplorerProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
  onFileSelect: (filePath: string) => void;
}

export function FileExplorer({ projectId, open, onClose, onFileSelect }: FileExplorerProps) {
  const [filter, setFilter] = useState('');
  const { data: tree = [], isLoading } = useFileTree(projectId);

  if (!open) return null;

  return (
    <div className="absolute right-0 top-0 bottom-0 w-72 bg-white border-l border-gray-200 shadow-lg z-30 flex flex-col" data-testid="file-explorer">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <FolderTree size={16} />
          Files
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-gray-100" aria-label="Close explorer">
          <X size={16} className="text-gray-400" />
        </button>
      </div>

      {/* Filter */}
      <div className="px-3 py-2 border-b border-gray-100">
        <div className="flex items-center gap-2 px-2 py-1 bg-gray-50 rounded">
          <Search size={12} className="text-gray-400" />
          <input
            type="text"
            placeholder="Filter files..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="flex-1 bg-transparent text-xs outline-none"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-xs text-gray-400">Loading...</div>
        ) : (
          <DirectoryTree nodes={tree} onFileClick={onFileSelect} />
        )}
      </div>
    </div>
  );
}
