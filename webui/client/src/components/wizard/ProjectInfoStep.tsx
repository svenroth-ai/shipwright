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
    <div className="space-y-5">
      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5 tracking-tight">
          Project Name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="My Awesome App"
          className="w-full h-12 px-3.5 border-[1.5px] border-[var(--color-border)] rounded-[var(--radius-button)] text-sm text-[var(--color-text)] bg-[var(--color-surface)] placeholder:text-[#b0a99f] hover:border-[var(--color-accent)] focus:outline-none focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary)]/10 transition-colors"
        />
      </div>
      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5 tracking-tight">
          Project Directory
        </label>
        <div className="flex gap-2.5">
          <input
            type="text"
            value={path}
            onChange={(e) => onPathChange(e.target.value)}
            placeholder="C:\Users\...\my-app"
            className="flex-1 h-12 px-3.5 border-[1.5px] border-[var(--color-border)] rounded-[var(--radius-button)] text-[13px] font-mono text-[var(--color-text)] bg-[var(--color-surface)] placeholder:text-[#b0a99f] hover:border-[var(--color-accent)] focus:outline-none focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary)]/10 transition-colors"
          />
          <button
            type="button"
            onClick={handlePaste}
            data-testid="project-path-paste"
            className="h-12 px-4 flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-text)] bg-[var(--color-muted-bg)] border-[1.5px] border-[var(--color-border)] rounded-[var(--radius-button)] hover:border-[var(--color-accent)] transition-colors shrink-0"
          >
            <ClipboardPaste size={14} className="text-[var(--color-muted)]" />
            Paste
          </button>
        </div>
        <p className="text-xs text-[var(--color-muted)] mt-1.5">
          {pasteHint ?? 'Copy the full path from Explorer/Finder, then click Paste.'}
        </p>
      </div>
    </div>
  );
}
