import { useState, useRef, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import type { Task } from '../../types';

interface EditTaskModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: Task;
}

export function EditTaskModal({ open, onOpenChange, task }: EditTaskModalProps) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description);
  const titleRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const updateTask = useMutation({
    mutationFn: (data: { title?: string; description?: string }) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}/description`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
      onOpenChange(false);
    },
  });

  // Sync state when task changes or modal opens
  useEffect(() => {
    if (open) {
      setTitle(task.title);
      setDescription(task.description);
      setTimeout(() => titleRef.current?.focus(), 50);
    }
  }, [open, task.title, task.description]);

  function handleSubmit() {
    const t = title.trim();
    if (!t) return;

    const patch: { title?: string; description?: string } = {};
    if (t !== task.title) patch.title = t;
    if (description.trim() !== task.description) patch.description = description.trim();

    if (Object.keys(patch).length > 0) {
      updateTask.mutate(patch);
    } else {
      onOpenChange(false);
    }
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
              Edit Task
            </Dialog.Title>
            <Dialog.Description className="sr-only">Edit task title and description</Dialog.Description>
            <Dialog.Close asChild>
              <button className="p-1 rounded hover:bg-gray-100" aria-label="Close">
                <X size={18} className="text-gray-400" />
              </button>
            </Dialog.Close>
          </div>

          <div className="mb-3">
            <label htmlFor="edit-title" className="block text-sm font-medium text-gray-700 mb-1">
              Title
            </label>
            <input
              ref={titleRef}
              id="edit-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What needs to be done?"
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
                  e.preventDefault();
                  document.getElementById('edit-description')?.focus();
                }
              }}
            />
          </div>

          <div className="mb-4">
            <label htmlFor="edit-description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              id="edit-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add details, context, or acceptance criteria..."
              rows={4}
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
            />
          </div>

          <div className="flex justify-end gap-2">
            <Dialog.Close asChild>
              <button className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg">
                Cancel
              </button>
            </Dialog.Close>
            <button
              disabled={!title.trim() || updateTask.isPending}
              onClick={handleSubmit}
              className="px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {updateTask.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
