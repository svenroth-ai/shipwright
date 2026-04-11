import { FolderOpen } from 'lucide-react';

interface ProjectInfoStepProps {
  name: string;
  path: string;
  onNameChange: (name: string) => void;
  onPathChange: (path: string) => void;
}

export function ProjectInfoStep({ name, path, onNameChange, onPathChange }: ProjectInfoStepProps) {
  async function handleBrowse() {
    // Use File System Access API if available (Chromium)
    if ('showDirectoryPicker' in window) {
      try {
        const handle = await (window as unknown as { showDirectoryPicker: () => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker();
        onPathChange(handle.name);
      } catch {
        // User cancelled
      }
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Project Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="My Awesome App"
          className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Project Directory</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={path}
            onChange={(e) => onPathChange(e.target.value)}
            placeholder="C:\Users\...\my-app"
            className="flex-1 px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
          />
          <button
            type="button"
            onClick={handleBrowse}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-600 border border-[#e0dbd4] rounded-lg hover:bg-gray-50 transition-colors shrink-0"
          >
            <FolderOpen size={14} />
            Browse
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1">Directory must exist. Existing project files are fine.</p>
      </div>
    </div>
  );
}
