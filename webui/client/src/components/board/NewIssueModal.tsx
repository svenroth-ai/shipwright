import { useState, useRef, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { Project } from '../../types';
import { useCreateTask } from '../../hooks/useCreateTask';

interface NewIssueModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeProjectId: string | null;
  projects: Project[];
}

export function NewIssueModal({ open, onOpenChange, activeProjectId, projects }: NewIssueModalProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [projectId, setProjectId] = useState(activeProjectId ?? '');
  const [startImmediately, setStartImmediately] = useState(true);
  const titleRef = useRef<HTMLInputElement>(null);
  const { createTask, isCreating } = useCreateTask();

  // Sync projectId when activeProjectId changes
  useEffect(() => {
    if (activeProjectId) setProjectId(activeProjectId);
  }, [activeProjectId]);

  // Focus title on open
  useEffect(() => {
    if (open) {
      setTimeout(() => titleRef.current?.focus(), 50);
    }
  }, [open]);

  function handleSubmit() {
    if (!title.trim() || !projectId) return;

    createTask({ projectId, description: `${title.trim()}${description.trim() ? `\n\n${description.trim()}` : ''}`, startImmediately });
    setTitle('');
    setDescription('');
    onOpenChange(false);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-xl p-6 w-full max-w-[480px] z-50"
          onKeyDown={handleKeyDown}
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold text-gray-900">
              New Issue
            </Dialog.Title>
            <Dialog.Description className="sr-only">Create a new task issue</Dialog.Description>
            <Dialog.Close asChild>
              <button className="p-1 rounded hover:bg-gray-100" aria-label="Close">
                <X size={18} className="text-gray-400" />
              </button>
            </Dialog.Close>
          </div>

          {/* Project selector (when All tab active) */}
          {!activeProjectId && (
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">Project</label>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              >
                <option value="">Select a project...</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="mb-3">
            <label htmlFor="issue-title" className="block text-sm font-medium text-gray-700 mb-1">
              Title
            </label>
            <input
              ref={titleRef}
              id="issue-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What needs to be done?"
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
                  e.preventDefault();
                  document.getElementById('issue-description')?.focus();
                }
              }}
            />
          </div>

          <div className="mb-4">
            <label htmlFor="issue-description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              id="issue-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add details, context, or acceptance criteria..."
              rows={4}
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
            />
          </div>

          {/* Start immediately checkbox */}
          <label className="flex items-start gap-2 mb-4 cursor-pointer">
            <input
              type="checkbox"
              checked={startImmediately}
              onChange={(e) => setStartImmediately(e.target.checked)}
              className="mt-0.5 rounded border-gray-300 text-[var(--color-primary)] focus:ring-[var(--color-primary)]"
            />
            <div>
              <span className="text-sm font-medium text-gray-700">Start immediately</span>
              <p className="text-xs text-gray-400">Launch Claude CLI right after creation</p>
            </div>
          </label>

          <div className="flex justify-end gap-2">
            <Dialog.Close asChild>
              <button className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg">
                Cancel
              </button>
            </Dialog.Close>
            <button
              disabled={!title.trim() || !projectId || isCreating}
              onClick={handleSubmit}
              className="px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCreating ? 'Creating...' : 'Create Issue'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
