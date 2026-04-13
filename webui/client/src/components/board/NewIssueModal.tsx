import { useState, useRef, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Sparkles } from 'lucide-react';
import type { Project } from '../../types';
import { useCreateTask } from '../../hooks/useCreateTask';
import { apiPost } from '../../lib/api';

const PHASE_OPTIONS = [
  { value: 'project', label: 'Project' },
  { value: 'design', label: 'Design' },
  { value: 'plan', label: 'Plan' },
  { value: 'build', label: 'Build' },
  { value: 'test', label: 'Test' },
  { value: 'deploy', label: 'Deploy' },
  { value: 'changelog', label: 'Changelog' },
  { value: 'compliance', label: 'Compliance' },
] as const;

const DEFAULT_PHASE = 'project';
const CLASSIFY_DEBOUNCE_MS = 400;

interface ClassifyResponse {
  intent?: string;
  complexity?: string;
  phase?: string;
  phase_confidence?: number;
}

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
  const [phase, setPhase] = useState<string>(DEFAULT_PHASE);
  const [phaseIsAuto, setPhaseIsAuto] = useState(true);
  const phaseIsAutoRef = useRef(true);
  const titleRef = useRef<HTMLInputElement>(null);
  const { createTask, isCreating } = useCreateTask();

  useEffect(() => {
    phaseIsAutoRef.current = phaseIsAuto;
  }, [phaseIsAuto]);

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

  // Reset auto-phase state when modal closes
  useEffect(() => {
    if (!open) {
      setPhase(DEFAULT_PHASE);
      setPhaseIsAuto(true);
    }
  }, [open]);

  // Debounced phase auto-classification
  useEffect(() => {
    if (!open || !phaseIsAuto || !projectId) return;

    const combined = `${title} ${description}`.trim();
    if (!combined) {
      setPhase(DEFAULT_PHASE);
      return;
    }

    let aborted = false;
    const timer = setTimeout(() => {
      apiPost<ClassifyResponse>(`/projects/${projectId}/classify`, { description: combined })
        .then((data) => {
          // Two guards: effect was aborted, OR user has since picked manually
          if (aborted || !phaseIsAutoRef.current) return;
          const suggested = data?.phase;
          if (suggested && PHASE_OPTIONS.some((p) => p.value === suggested)) {
            setPhase(suggested);
          }
        })
        .catch(() => {
          // Silent: keep current default
        });
    }, CLASSIFY_DEBOUNCE_MS);

    return () => {
      aborted = true;
      clearTimeout(timer);
    };
  }, [open, phaseIsAuto, projectId, title, description]);

  function handleSubmit() {
    if (!title.trim() || !projectId) return;

    createTask({
      projectId,
      title: title.trim(),
      description: description.trim(),
      startImmediately,
      phase,
    });
    setTitle('');
    setDescription('');
    setPhase(DEFAULT_PHASE);
    setPhaseIsAuto(true);
    onOpenChange(false);
  }

  function handlePhaseChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setPhase(e.target.value);
    setPhaseIsAuto(false);
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
              New Task
            </Dialog.Title>
            <Dialog.Description className="sr-only">Create a new task</Dialog.Description>
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

          {/* Phase selector */}
          <div className="mb-3">
            <label htmlFor="issue-phase" className="flex items-center gap-1.5 text-sm font-medium text-gray-700 mb-1">
              <span>Phase</span>
              {phaseIsAuto && (
                <span className="inline-flex items-center gap-1 text-xs text-[var(--color-primary)]" title="Auto-suggested">
                  <Sparkles size={12} aria-label="Auto-suggested" />
                  <span>auto</span>
                </span>
              )}
            </label>
            <select
              id="issue-phase"
              value={phase}
              onChange={handlePhaseChange}
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
            >
              {PHASE_OPTIONS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
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
              {isCreating ? 'Creating...' : 'Create Task'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
