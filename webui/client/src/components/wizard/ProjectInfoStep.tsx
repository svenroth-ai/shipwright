import { useState } from 'react';
import { ClipboardPaste } from 'lucide-react';
import { pasteFromClipboard, looksLikePath } from '../../lib/filePicker';

interface ProjectInfoStepProps {
  name: string;
  path: string;
  onNameChange: (name: string) => void;
  onPathChange: (path: string) => void;
}

export function ProjectInfoStep({ name, path, onNameChange, onPathChange }: ProjectInfoStepProps) {
  // Iterate 14.7.1 — the old "Browse" button tried `showDirectoryPicker`
  // and got a sandboxed half-path back. Replaced with a clipboard-paste
  // helper (see lib/filePicker.ts for the design rationale). The field
  // itself stays freely editable as the primary input path.
  const [pasteHint, setPasteHint] = useState<string | null>(null);

  async function handlePaste() {
    setPasteHint(null);
    const raw = await pasteFromClipboard();
    if (raw && looksLikePath(raw)) {
      onPathChange(raw.trim());
      return;
    }
    setPasteHint("Clipboard doesn't look like a path — paste manually with Ctrl+V.");
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
            onClick={handlePaste}
            data-testid="project-path-paste"
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-600 border border-[#e0dbd4] rounded-lg hover:bg-gray-50 transition-colors shrink-0"
          >
            <ClipboardPaste size={14} />
            Paste
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1">
          {pasteHint ?? 'Copy the full path from Explorer/Finder, then click Paste.'}
        </p>
      </div>
    </div>
  );
}
